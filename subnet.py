"""Subnet calculator: inspect a network, plan VLSM, or practice with a quiz.

Uses the stdlib ipaddress module as a correctness check, but works out every
answer with explicit binary math so you can see how subnetting actually works.
"""
from __future__ import annotations

import argparse
import ipaddress
import random
import sys
from dataclasses import dataclass
from enum import Enum


def to_int(dotted: str) -> int:
    parts = [int(p) for p in dotted.split(".")]
    if len(parts) != 4 or any(not 0 <= p <= 255 for p in parts):
        raise ValueError(f"invalid IPv4 address: {dotted}")
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def to_dotted(value: int) -> str:
    return ".".join(str((value >> s) & 0xFF) for s in (24, 16, 8, 0))


def to_binary(value: int) -> str:
    bits = f"{value:032b}"
    return ".".join(bits[i:i + 8] for i in range(0, 32, 8))


class AddressClass(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D (multicast)"
    E = "E (reserved)"

    @classmethod
    def of(cls, address: int) -> AddressClass:
        first = address >> 24
        if first < 128:
            return cls.A
        if first < 192:
            return cls.B
        if first < 224:
            return cls.C
        if first < 240:
            return cls.D
        return cls.E


PRIVATE_RANGES: tuple[tuple[int, int], ...] = (
    (to_int("10.0.0.0"), 8),
    (to_int("172.16.0.0"), 12),
    (to_int("192.168.0.0"), 16),
)


@dataclass(frozen=True)
class Subnet:
    """One IPv4 network, with every value derived from bitwise math."""

    address: int  # the address as given (may be a host inside the network)
    prefix: int

    def __post_init__(self) -> None:
        if not 0 <= self.prefix <= 32:
            raise ValueError(f"prefix must be 0-32, got /{self.prefix}")

    @classmethod
    def parse(cls, text: str) -> Subnet:
        ip, _, prefix = text.strip().partition("/")
        return cls(to_int(ip), int(prefix) if prefix else 32)

    @property
    def host_bits(self) -> int:
        return 32 - self.prefix

    @property
    def mask(self) -> int:
        return (0xFFFFFFFF << self.host_bits) & 0xFFFFFFFF

    @property
    def wildcard(self) -> int:
        return ~self.mask & 0xFFFFFFFF

    @property
    def network(self) -> int:
        return self.address & self.mask

    @property
    def broadcast(self) -> int:
        return self.network | self.wildcard

    @property
    def total_addresses(self) -> int:
        return 2 ** self.host_bits

    @property
    def usable_hosts(self) -> int:
        if self.prefix == 32:
            return 1
        if self.prefix == 31:  # RFC 3021 point-to-point
            return 2
        return self.total_addresses - 2

    @property
    def first_usable(self) -> int:
        return self.network if self.prefix >= 31 else self.network + 1

    @property
    def last_usable(self) -> int:
        return self.broadcast if self.prefix >= 31 else self.broadcast - 1

    @property
    def magic_number(self) -> int:
        """Block size in the octet where the mask stops being 255."""
        octet = min(self.prefix // 8, 3) if self.prefix < 32 else 3
        bits_in_octet = self.prefix - octet * 8
        return 2 ** (8 - bits_in_octet) if bits_in_octet <= 8 else 1

    @property
    def interesting_octet(self) -> int:
        return min(self.prefix // 8, 3) + 1

    @property
    def address_class(self) -> AddressClass:
        return AddressClass.of(self.address)

    @property
    def is_private(self) -> bool:
        return any(Subnet(self.address, p).network == net for net, p in PRIVATE_RANGES)

    def cidr(self) -> str:
        return f"{to_dotted(self.network)}/{self.prefix}"

    @staticmethod
    def prefix_for_hosts(hosts: int) -> int:
        """Smallest subnet whose usable hosts (2^h - 2) cover the need."""
        if hosts < 1:
            raise ValueError("host count must be at least 1")
        h = 2
        while 2 ** h - 2 < hosts:
            h += 1
        if h > 32:
            raise ValueError("too many hosts for IPv4")
        return 32 - h


class SubnetReport:
    """Prints an inspection with the binary math visible."""

    def render(self, s: Subnet) -> str:
        lines = [
            f"Input            {to_dotted(s.address)}/{s.prefix}",
            "",
            f"  IP       {to_binary(s.address)}",
            f"  Mask AND {to_binary(s.mask)}",
            f"  Network  {to_binary(s.network)}  = {to_dotted(s.network)}",
            f"  Bcast    {to_binary(s.broadcast)}  = {to_dotted(s.broadcast)}"
            "  (host bits set to 1)",
            "",
            f"Network          {s.cidr()}",
            f"Subnet mask      {to_dotted(s.mask)}",
            f"Wildcard mask    {to_dotted(s.wildcard)}",
            f"Broadcast        {to_dotted(s.broadcast)}",
            f"First usable     {to_dotted(s.first_usable)}",
            f"Last usable      {to_dotted(s.last_usable)}",
            f"Host bits        {s.host_bits}  -> 2^{s.host_bits} = {s.total_addresses}"
            f" addresses, {s.usable_hosts} usable",
            f"Block size       {s.magic_number} (octet {s.interesting_octet})",
            f"Class            {s.address_class.value}",
            f"Private          {'yes (RFC 1918)' if s.is_private else 'no'}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class Requirement:
    name: str
    hosts: int


@dataclass(frozen=True)
class Allocation:
    requirement: Requirement
    subnet: Subnet

    @property
    def wasted(self) -> int:
        return self.subnet.usable_hosts - self.requirement.hosts


@dataclass(frozen=True)
class VLSMPlan:
    base: Subnet
    allocations: list[Allocation]

    @property
    def used(self) -> int:
        return sum(a.subnet.total_addresses for a in self.allocations)

    @property
    def leftover(self) -> int:
        return self.base.total_addresses - self.used

    @property
    def next_free(self) -> int:
        if not self.allocations:
            return self.base.network
        return self.allocations[-1].subnet.broadcast + 1


class DoesNotFitError(ValueError):
    pass


class VLSMPlanner:
    """Allocates subnets largest-first so every block lands on its boundary."""

    def plan(self, base: Subnet, requirements: list[Requirement]) -> VLSMPlan:
        ordered = sorted(requirements, key=lambda r: r.hosts, reverse=True)
        cursor = base.network
        end = base.broadcast
        allocations: list[Allocation] = []
        for req in ordered:
            prefix = Subnet.prefix_for_hosts(req.hosts)
            if prefix < base.prefix:
                raise DoesNotFitError(
                    f"{req.name} needs {req.hosts} hosts (/{prefix}), "
                    f"bigger than {base.cidr()}")
            size = 2 ** (32 - prefix)
            cursor = (cursor + size - 1) // size * size  # align to block
            if cursor + size - 1 > end:
                needed = sum(2 ** (32 - Subnet.prefix_for_hosts(r.hosts)) for r in ordered)
                raise DoesNotFitError(
                    f"{req.name} ({req.hosts} hosts, /{prefix}) does not fit: "
                    f"requirements need {needed} addresses, "
                    f"{base.cidr()} has {base.total_addresses}")
            allocations.append(Allocation(req, Subnet(cursor, prefix)))
            cursor += size
        return VLSMPlan(base, allocations)

    def render(self, plan: VLSMPlan) -> str:
        head = f"{'Name':<10}{'Need':>5}  {'Subnet':<19}{'Mask':<17}{"Usable range":<34}{'Bcast':<16}{"Spare":>6}"
        rows = [f"VLSM plan for {plan.base.cidr()}  (largest first)", "", head, "-" * len(head)]
        for a in plan.allocations:
            s = a.subnet
            rng = f"{to_dotted(s.first_usable)} - {to_dotted(s.last_usable)}"
            rows.append(f"{a.requirement.name:<10}{a.requirement.hosts:>5}  {s.cidr():<19}"
                        f"{to_dotted(s.mask):<17}{rng:<34}{to_dotted(s.broadcast):<16}{a.wasted:>6}")
        rows += ["", f"Used {plan.used} of {plan.base.total_addresses} addresses. "
                 f"Leftover {plan.leftover}, starting at {to_dotted(plan.next_free)}."]
        return "\n".join(rows)


class QuestionType(Enum):
    NETWORK = "network address"
    BROADCAST = "broadcast address"
    USABLE = "number of usable hosts"
    MASK = "subnet mask"
    RANGE = "usable host range"
    PREFIX_FOR_HOSTS = "smallest prefix"


@dataclass(frozen=True)
class Question:
    prompt: str
    answer: str


class QuizGenerator:
    """Random practice questions in Network+/Security+ style."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def random_subnet(self) -> Subnet:
        first = self.rng.choice([10, 172, 192])
        second = {10: self.rng.randint(0, 255), 172: self.rng.randint(16, 31), 192: 168}[first]
        addr = (first << 24) | (second << 16) | (self.rng.randint(0, 255) << 8) | self.rng.randint(1, 254)
        return Subnet(addr, self.rng.randint(17, 30))

    def question(self) -> Question:
        kind = self.rng.choice(list(QuestionType))
        s = self.random_subnet()
        host = f"{to_dotted(s.address)}/{s.prefix}"
        if kind is QuestionType.NETWORK:
            return Question(f"What is the network address of {host}?", to_dotted(s.network))
        if kind is QuestionType.BROADCAST:
            return Question(f"What is the broadcast address of {host}?", to_dotted(s.broadcast))
        if kind is QuestionType.USABLE:
            return Question(f"How many usable hosts are in a /{s.prefix}?", str(s.usable_hosts))
        if kind is QuestionType.MASK:
            return Question(f"What is the dotted subnet mask for /{s.prefix}?", to_dotted(s.mask))
        if kind is QuestionType.RANGE:
            return Question(f"What is the usable host range of {host}?",
                            f"{to_dotted(s.first_usable)} - {to_dotted(s.last_usable)}")
        hosts = self.rng.randint(3, 2000)
        return Question(f"What is the smallest prefix that fits {hosts} hosts?",
                        f"/{Subnet.prefix_for_hosts(hosts)}")


def cross_check(s: Subnet) -> None:
    """Fail loudly if the binary math ever disagrees with ipaddress."""
    ref = ipaddress.ip_network(f"{to_dotted(s.address)}/{s.prefix}", strict=False)
    assert s.network == int(ref.network_address)
    assert s.broadcast == int(ref.broadcast_address)


def parse_requirements(items: list[str]) -> list[Requirement]:
    reqs = []
    for item in items:
        name, _, hosts = item.rpartition("=")
        reqs.append(Requirement(name or f"Net{len(reqs) + 1}", int(hosts)))
    return reqs


def run_quiz(count: int, show: bool) -> None:
    gen = QuizGenerator()
    score = 0
    for i in range(1, count + 1):
        q = gen.question()
        print(f"Q{i}. {q.prompt}")
        if show:
            print(f"    Answer: {q.answer}\n")
            continue
        guess = input("    > ").strip()
        if guess.replace(" ", "") == q.answer.replace(" ", ""):
            score += 1
            print("    Correct\n")
        else:
            print(f"    Answer: {q.answer}\n")
    if not show:
        print(f"Score: {score}/{count}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="IPv4 subnet calculator")
    p.add_argument("network", nargs="?", help="CIDR, e.g. 192.168.10.37/27")
    p.add_argument("--vlsm", nargs="+", metavar="NAME=HOSTS",
                   help="host requirements, e.g. Sales=60 IT=28")
    p.add_argument("--quiz", type=int, nargs="?", const=5, metavar="N")
    p.add_argument("--answers", action="store_true", help="quiz: just print answers")
    args = p.parse_args(argv)

    if args.quiz:
        run_quiz(args.quiz, args.answers)
        return 0
    if not args.network:
        p.error("give a network, or use --quiz")
    try:
        subnet = Subnet.parse(args.network)
        cross_check(subnet)
        if args.vlsm:
            planner = VLSMPlanner()
            print(planner.render(planner.plan(Subnet(subnet.network, subnet.prefix),
                                              parse_requirements(args.vlsm))))
        else:
            print(SubnetReport().render(subnet))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
