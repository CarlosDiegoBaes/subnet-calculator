import ipaddress
import random

import pytest

from subnet import (DoesNotFitError, QuizGenerator, Requirement, Subnet, VLSMPlanner,
                    main, to_dotted, to_int)

rng = random.Random(42)
CASES = [(rng.getrandbits(32), rng.randint(0, 32)) for _ in range(2000)]
CASES += [(to_int("192.168.10.37"), 27), (to_int("10.0.0.1"), 8), (to_int("0.0.0.0"), 0),
          (to_int("255.255.255.255"), 32), (to_int("172.16.5.4"), 31)]


@pytest.mark.parametrize("addr,prefix", CASES)
def test_matches_ipaddress(addr, prefix):
    s = Subnet(addr, prefix)
    ref = ipaddress.ip_network(f"{to_dotted(addr)}/{prefix}", strict=False)
    assert s.network == int(ref.network_address)
    assert s.broadcast == int(ref.broadcast_address)
    assert s.mask == int(ref.netmask)
    assert s.wildcard == int(ref.hostmask)
    assert s.total_addresses == ref.num_addresses
    hosts = list(ref.hosts()) if prefix >= 24 else None
    if hosts:
        assert s.first_usable == int(hosts[0]) and s.last_usable == int(hosts[-1])
        assert s.usable_hosts == len(hosts)
    ip = ipaddress.ip_address(addr)
    assert s.is_private == any(ip in ipaddress.ip_network(n)
                               for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def test_example_27():
    s = Subnet.parse("192.168.10.37/27")
    assert to_dotted(s.network) == "192.168.10.32"
    assert to_dotted(s.broadcast) == "192.168.10.63"
    assert to_dotted(s.mask) == "255.255.255.224"
    assert s.usable_hosts == 30 and s.magic_number == 32


@pytest.mark.parametrize("hosts,prefix", [(1, 30), (2, 30), (3, 29), (6, 29), (7, 28),
                                          (30, 27), (31, 26), (62, 26), (63, 25), (254, 24), (255, 23)])
def test_prefix_for_hosts(hosts, prefix):
    assert Subnet.prefix_for_hosts(hosts) == prefix


def test_vlsm_example():
    plan = VLSMPlanner().plan(Subnet.parse("192.168.10.0/24"), [
        Requirement("IT", 28), Requirement("Sales", 60), Requirement("P2P", 2), Requirement("Guest", 12)])
    got = [(a.requirement.name, a.subnet.cidr()) for a in plan.allocations]
    assert got == [("Sales", "192.168.10.0/26"), ("IT", "192.168.10.64/27"),
                   ("Guest", "192.168.10.96/28"), ("P2P", "192.168.10.112/30")]
    assert plan.leftover == 140


@pytest.mark.parametrize("seed", range(200))
def test_vlsm_random_no_overlap(seed):
    r = random.Random(seed)
    base = Subnet(to_int("10.0.0.0"), r.randint(20, 26))
    reqs = [Requirement(f"N{i}", r.randint(1, 120)) for i in range(r.randint(1, 8))]
    try:
        plan = VLSMPlanner().plan(base, reqs)
    except DoesNotFitError:
        return
    basenet = ipaddress.ip_network(base.cidr())
    nets = [ipaddress.ip_network(a.subnet.cidr()) for a in plan.allocations]
    for i, n in enumerate(nets):
        assert n.subnet_of(basenet)
        assert n.num_addresses - 2 >= plan.allocations[i].requirement.hosts
        for m in nets[i + 1:]:
            assert not n.overlaps(m)


def test_vlsm_does_not_fit():
    with pytest.raises(DoesNotFitError):
        VLSMPlanner().plan(Subnet.parse("192.168.10.0/26"),
                           [Requirement("A", 30), Requirement("B", 30), Requirement("C", 2)])
    with pytest.raises(DoesNotFitError):
        VLSMPlanner().plan(Subnet.parse("192.168.10.0/26"), [Requirement("A", 100)])


def test_quiz_answers_correct():
    gen = QuizGenerator(random.Random(1))
    for _ in range(300):
        s = gen.random_subnet()
        ref = ipaddress.ip_network(f"{to_dotted(s.address)}/{s.prefix}", strict=False)
        assert to_dotted(s.network) == str(ref.network_address)
        assert gen.question().answer


def test_invalid_input():
    with pytest.raises(ValueError):
        Subnet.parse("300.1.1.1/24")
    with pytest.raises(ValueError):
        Subnet.parse("1.1.1.1/33")
    assert main(["192.168.1.0/33"]) == 1
