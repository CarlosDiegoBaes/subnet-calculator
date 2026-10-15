from PIL import Image, ImageDraw, ImageFont
G="/usr/share/fonts/truetype/sand-box/google/"
mono=lambda s: ImageFont.truetype(G+"JetBrains Mono/JetBrainsMono-VariableFont_wght.ttf" if False else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", s)
def sans(s,b=False):
    f=ImageFont.truetype(G+"IBM Plex Sans/IBMPlexSans-VariableFont_wdth,wght.ttf",s); f.set_variation_by_name("SemiBold" if b else "Regular"); return f
# 1 terminal
lines=["$ python subnet.py 192.168.10.0/24 --vlsm Sales=60 IT=28 Guest=12 P2P=2",""]+open("vlsm_output.txt").read().rstrip().split("\n")
f=mono(22); W,H=1600,90+len(lines)*34+50
im=Image.new("RGB",(W,H),"#1b1f24"); d=ImageDraw.Draw(im)
d.rectangle([0,0,W,46],fill="#2a3038")
for i,c in enumerate(["#e06c5f","#e5b84f","#6cbf6a"]): d.ellipse([24+i*30,15,40+i*30,31],fill=c)
y=80
for i,l in enumerate(lines):
    col="#7fd1a8" if l.startswith("$") else "#e6e6e6"
    if l.startswith(("Name","---")): col="#e5b84f"
    d.text((40,y),l,font=f,fill=col); y+=34
im.save("vlsm-demo.png")
# 2 diagram
W,H=1600,900; im=Image.new("RGB",(W,H),"#f4f1ea"); d=ImageDraw.Draw(im)
d.text((80,60),"192.168.10.0/24 split with VLSM",font=sans(44,True),fill="#1e3a34")
blocks=[("Sales","/26",0,64,"#1e3a34"),("IT","/27",64,32,"#3d6b5f"),("Guest","/28",96,16,"#b08d3c"),("P2P","/30",112,4,"#8a4b3a"),("Unused","",116,140,"#d9d4c7")]
x0,x1,y0,y1=80,1520,180,330; sc=(x1-x0)/256
for n,p,st,sz,c in blocks:
    a=x0+st*sc; b=x0+(st+sz)*sc; d.rectangle([a,y0,b,y1],fill=c,outline="#f4f1ea",width=2)
    tc="#1e3a34" if n=="Unused" else "#f4f1ea"
    if sz>=16: d.text((a+12,y0+16),n,font=sans(26,True),fill=tc); d.text((a+12,y0+52),p,font=sans(22),fill=tc)
for st in [0,64,96,112,256]:
    d.text((x0+st*sc-(8 if st else 0)-(30 if st==256 else 0)-(0 if st!=116 else -4),y1+12),f".{st}" if st<256 else ".255",font=mono(18),fill="#555")
d.text((x0+112*sc-14,y0-34),"P2P",font=sans(20,True),fill="#8a4b3a")
# binary
yb=470; d.text((80,yb),"Inside IT 192.168.10.64/27: host 192.168.10.77",font=sans(30,True),fill="#1e3a34")
rows=[("Address","11000000.10101000.00001010.010","01101"),("Mask /27","11111111.11111111.11111111.111","00000"),("Network","11000000.10101000.00001010.010","00000"),("Broadcast","11000000.10101000.00001010.010","11111")]
vals=["192.168.10.77","255.255.255.224","192.168.10.64","192.168.10.95"]
F=mono(30); y=550
for (lab,net,host),v in zip(rows,vals):
    d.text((80,y),lab,font=sans(26),fill="#333")
    d.text((300,y),net,font=F,fill="#1e3a34"); w=d.textlength(net,font=F)
    d.text((300+w,y),host,font=F,fill="#b08d3c"); d.text((1240,y),v,font=mono(26),fill="#333"); y+=62
bx=300+d.textlength(rows[0][1],font=F)
d.line([bx-3,535,bx-3,y],fill="#8a4b3a",width=3)
d.text((bx-140,y+10),"27 network bits",font=sans(20),fill="#1e3a34"); d.text((bx+10,y+10),"5 host bits",font=sans(20),fill="#b08d3c")
im.save("subnet-diagram.png")
