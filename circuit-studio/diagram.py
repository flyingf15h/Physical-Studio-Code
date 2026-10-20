# IKEA-style picture of one build step, drawn as SVG (no extra packages): the breadboard and the
# Arduino Uno to scale (the Uno's outline, headers and pin positions come from parts/arduino-uno.json),
# everything placed in earlier steps faded, this step's parts in colour with a cyan halo, resistor
# values written on the resistor, and a numbered marker on every hole or pin this step uses.
# Works on a builder.py plan dict: plan['scene'] (app.py's Spec) and plan['steps'].
import html, math, re

S=12/2.54  # px per mm, so one breadboard pitch (2.54 mm) is 12 px
HOLE=re.compile(r'([a-j])([1-9]|[1-5][0-9]|6[0-3])')
RAIL=re.compile(r'rail_(-?1)_(21\.6|24\.14)_([1-9]|[1-5][0-9]|6[0-3])')
PIN=re.compile(r'pin:([a-z0-9_~]+)')
COL_MM=dict(zip('abcdefghij',(13.97,11.43,8.89,6.35,3.81,-3.81,-6.35,-8.89,-11.43,-13.97)))  # same offsets as app.py
HALO='#26c6da'  # the 3D viewer's highlight colour
UX,UY=36,24  # Arduino top-left (room on the left for the USB-B jack)
BX,BY=380,30  # breadboard top-left; app.py's 165 x 55 mm template
BW,BH=165*S,55*S
WIDTH,HEIGHT=round(BX+BW+16),330
BAND=['#111','#8b4513','#d32f2f','#f57c00','#fbc02d','#388e3c','#1976d2','#7b1fa2','#888','#fff']

def esc(t):return html.escape(str(t),quote=True)
def row_x(row):return BX+(82.5-78.74+(row-1)*2.54)*S
def mm_y(y):return BY+BH/2-y*S

def hole_xy(key):
    key=key.strip().lower()
    m=HOLE.fullmatch(key)
    if m:return row_x(int(m[2])),mm_y(COL_MM[m[1]])
    m=RAIL.fullmatch(key)
    if m:return row_x(int(m[3])),mm_y(int(m[1])*float(m[2]))
    return None

class Board:
    """Where each board pin is drawn. Uno pins use the library's real positions; any pin the library
    doesn't know (another board, a made-up name) gets its own slot down the board's right edge."""
    def __init__(self,uno):
        self.uno=uno;self.w,self.h=(uno['body']['size'][:2] if uno else (68.6,53.4))
        self.pins={p['id']:p for p in uno['pins']} if uno else {};self.extra={}
    def resolve(self,name):
        n=name.strip().lower().replace(' ','').replace('~','').removeprefix('pin:')
        if n in self.pins:return n
        if n.isdigit() and 'd'+n in self.pins:return 'd'+n
        if n.startswith('gnd'):return next((p for p in self.pins if p.startswith('gnd')),None)
        return None
    def xy(self,name):
        pid=self.resolve(name)
        if pid:
            x,y=self.pins[pid]['position'][:2];return UX+x*S,UY+(self.h-y)*S
        slot=self.extra.setdefault(name.strip().lower(),len(self.extra))
        return UX+self.w*S-12,UY+40+slot*18
    def label(self,name):
        pid=self.resolve(name)
        return self.pins[pid]['label'] if pid else name.strip().upper().removeprefix('PIN:')

def draw_board(board,used):
    W,H=board.w*S,board.h*S;out=[f'<rect x="{UX}" y="{UY}" width="{W:.1f}" height="{H:.1f}" rx="7" fill="#1d7a8c" stroke="#0f4c57" stroke-width="2"/>']
    for c in (board.uno or {}).get('connectors',[]):  # USB-B and barrel jack poke out of the -x edge
        cy=UY+(board.h-c['center'][1])*S;h=c['size'][0]*S;x0=UX-c.get('protrusion',0)*S
        fill='#c9ccd1' if 'usb' in c['type'] else '#222'
        out.append(f'<rect x="{x0:.1f}" y="{cy-h/2:.1f}" width="{(c.get("protrusion",0)+14)*S:.1f}" height="{h:.1f}" rx="2" fill="{fill}" stroke="#555"/>')
    for k in (board.uno or {}).get('keep_out',[]):
        if 'header' not in k['id']:continue
        (x0,y0),(x1,y1)=k['min'][:2],k['max'][:2]
        out.append(f'<rect x="{UX+x0*S:.1f}" y="{UY+(board.h-y1)*S:.1f}" width="{(x1-x0)*S:.1f}" height="{(y1-y0)*S:.1f}" fill="#202020"/>')
    for pid in board.pins:
        x,y=board.xy(pid);out.append(f'<rect x="{x-2:.1f}" y="{y-2:.1f}" width="4" height="4" fill="#9a9a9a"/>')
    out.append(f'<text x="{UX+W/2:.1f}" y="{UY+H/2+6:.1f}" text-anchor="middle" font-size="17" font-weight="700" fill="#ffffff" opacity=".55">ARDUINO UNO</text>')
    for name in sorted(used):  # labels only for the pins this build uses
        x,y=board.xy(name);top=y<UY+H/2;ty=y+16 if top else y-9
        out.append(f'<text x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#fff">{esc(board.label(name))}</text>')
    dy=UY+H+18  # dimension line: the size comes from the parts library, not from the model
    out.append(f'<path d="M{UX} {dy-5}v10M{UX+W:.1f} {dy-5}v10M{UX} {dy}H{UX+W:.1f}" stroke="#666" fill="none"/>')
    out.append(f'<text x="{UX+W/2:.1f}" y="{dy+14}" text-anchor="middle" font-size="10" fill="#555">{board.w:g} mm × {board.h:g} mm (parts library)</text>')
    return ''.join(out)

def draw_breadboard(rails):
    o=[f'<rect x="{BX}" y="{BY}" width="{BW:.1f}" height="{BH:.1f}" rx="8" fill="#f4f0e6" stroke="#cfc6b4" stroke-width="1.5"/>',
       f'<rect x="{BX}" y="{mm_y(2.4):.1f}" width="{BW:.1f}" height="{4.8*S:.1f}" fill="#e3dccd"/>',
       f'<pattern id="holes" x="{row_x(1)-6:.2f}" y="{mm_y(13.97)-6:.2f}" width="12" height="12" patternUnits="userSpaceOnUse"><rect x="4.4" y="4.4" width="3.2" height="3.2" fill="#8c8477"/></pattern>']
    x0,w=row_x(1)-6,63*12
    for top in (13.97,-3.81):o.append(f'<rect x="{x0:.1f}" y="{mm_y(top)-6:.1f}" width="{w}" height="60" fill="url(#holes)"/>')
    for side in (1,-1):
        for y in (21.6,24.14):
            o.append(f'<rect x="{x0:.1f}" y="{mm_y(side*y)-6:.1f}" width="{w}" height="12" fill="url(#holes)"/>')
            sign,color=rails.get((str(side),str(y)),('','#b9b2a5'))
            ly=mm_y(side*(y+1.6 if y>22 else y-1.6))
            o.append(f'<line x1="{x0:.1f}" y1="{ly:.1f}" x2="{x0+w:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="2"/>')
            if sign:o.append(f'<text x="{BX+7}" y="{mm_y(side*y)+4:.1f}" font-size="12" font-weight="700" fill="{color}">{sign}</text>')
    for r in (1,*range(5,61,5),63):o.append(f'<text x="{row_x(r):.1f}" y="{mm_y(0)+3:.1f}" text-anchor="middle" font-size="8" fill="#7a7266">{r}</text>')
    for c,y in COL_MM.items():o.append(f'<text x="{BX+7}" y="{mm_y(y)+3:.1f}" font-size="8" fill="#7a7266">{c}</text>')
    return ''.join(o)

def ohms(name):
    m=re.search(r'(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:ohm|Ω)',name)
    if not m:return None,''
    v=float(m[1])*{'':1,'k':1e3,'m':1e6}[m[2].lower()]
    return v,f"{m[1]}{m[2].lower() if m[2].lower()=='k' else m[2].upper()} Ω"

def draw_led(p,holes,new):
    (ax,ay),(cx,cy)=holes;bx,by=(ax+cx)/2,min(ay,cy)-18
    o=[f'<path d="M{ax:.1f} {ay:.1f}L{bx+3:.1f} {by+7:.1f}M{cx:.1f} {cy:.1f}L{bx-3:.1f} {by+7:.1f}" stroke="#8a8a8a" stroke-width="2" fill="none"/>']
    if new:o.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="14" fill="none" stroke="{HALO}" stroke-width="4" opacity=".8"/>')
    o.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8.5" fill="{p["color"]}" stroke="#333" stroke-width="1.2"/><circle cx="{bx-3:.1f}" cy="{by-3:.1f}" r="2.5" fill="#fff" opacity=".6"/>')
    o.append(f'<text x="{ax+5:.1f}" y="{ay-5:.1f}" font-size="11" font-weight="700" fill="#c62828">+</text>')
    return ''.join(o)

def draw_resistor(p,holes,new):
    (x1,y1),(x2,y2)=holes;mx,my=(x1+x2)/2,(y1+y2)/2;ang=math.degrees(math.atan2(y2-y1,x2-x1));L=min(math.hypot(x2-x1,y2-y1)*.62,34)
    v,label=ohms(p['name']);o=[]
    if new:o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{HALO}" stroke-width="9" stroke-linecap="round" opacity=".55"/>')
    o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#9e9e9e" stroke-width="2"/>')
    g=[f'<rect x="{-L/2:.1f}" y="-4.5" width="{L:.1f}" height="9" rx="4" fill="#dcc29a" stroke="#8d6e4a"/>']
    if v and v>=10:
        d=f'{int(round(v))}';colors=[BAND[int(d[0])],BAND[int(d[1])],BAND[min(len(d)-2,9)],'#c9a227']
        for k,c in enumerate(colors):g.append(f'<rect x="{-L/2+4+k*(L-8)/4:.1f}" y="-4.5" width="2.6" height="9" fill="{c}"/>')
    o.append(f'<g transform="translate({mx:.1f} {my:.1f}) rotate({ang:.1f})">{"".join(g)}</g>')
    if label:o.append(f'<text x="{mx:.1f}" y="{my-9:.1f}" text-anchor="middle" font-size="10" font-weight="700" fill="#5d4037" paint-order="stroke" stroke="#fff" stroke-width="3">{esc(label)}</text>')
    return ''.join(o)

def draw_generic(p,holes,new):
    xs=[h[0] for h in holes];ys=[h[1] for h in holes];x0,y0,x1,y1=min(xs)-8,min(ys)-8,max(xs)+8,max(ys)+8
    o=[f'<rect x="{x0-4:.1f}" y="{y0-4:.1f}" width="{x1-x0+8:.1f}" height="{y1-y0+8:.1f}" rx="5" fill="none" stroke="{HALO}" stroke-width="4" opacity=".8"/>'] if new else []
    o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1-x0:.1f}" height="{y1-y0:.1f}" rx="3" fill="#e9e9e9" stroke="#444" stroke-width="1.2"/>')
    if re.search(r'button|switch',p['name'],re.I):o.append(f'<circle cx="{(x0+x1)/2:.1f}" cy="{(y0+y1)/2:.1f}" r="{min(x1-x0,y1-y0)/3.2:.1f}" fill="#333"/>')
    return ''.join(o)

def draw_wire(w,a,b,new):
    lift=min(70,24+abs(b[0]-a[0])*.12);c1y=max(4,a[1]-lift);c2y=max(4,b[1]-lift)
    d=f'M{a[0]:.1f} {a[1]:.1f}C{a[0]:.1f} {c1y:.1f} {b[0]:.1f} {c2y:.1f} {b[0]:.1f} {b[1]:.1f}'
    o=[f'<path d="{d}" stroke="{HALO}" stroke-width="10" fill="none" stroke-linecap="round" opacity=".5"/>'] if new else []
    o.append(f'<path d="{d}" stroke="#0005" stroke-width="5.5" fill="none" stroke-linecap="round"/><path d="{d}" stroke="{w["color"]}" stroke-width="3.6" fill="none" stroke-linecap="round"/>')
    return ''.join(o)

def step_svg(plan,i,uno=None):
    """SVG page for step i (0-based) and the numbered markers [(n, what, where, hole)] it shows."""
    scene,steps=plan['scene'],plan['steps'];parts={p['id']:p for p in scene['parts']}
    boards=[p for p in scene['parts'] if p['kind']=='development_board'];board=Board(uno)
    def end(pid,term):
        p=parts.get(pid);t=term.strip().lower()
        if not p:return None
        if p['kind']=='breadboard':return hole_xy(t)
        if p['kind']=='development_board':return board.xy(t)
        holes=[hole_xy(h) for h in p['mount_holes']];k={'anode':0,'cathode':1,'1':0,'2':1,'a':0,'b':1}.get(t,0)
        return holes[k] if k<len(holes) else None
    def keys(item):  # the holes/pins an item occupies, in the same spelling as step placements
        if 'from_part' in item:
            out=set()
            for pid,t in ((item['from_part'],item['from_terminal']),(item['to_part'],item['to_terminal'])):
                kind=parts.get(pid,{}).get('kind')
                if kind=='breadboard':out.add(t.strip().lower())
                elif kind=='development_board':out.add('pin:'+(board.resolve(t) or t.strip().lower()))
            return out
        return {h.strip().lower() for h in item['mount_holes']}
    def placed(s):return {('pin:'+(board.resolve(m[1]) or m[1])) if (m:=PIN.fullmatch(pl['hole'].strip().lower())) else pl['hole'].strip().lower() for pl in s['placements']}
    # The step that puts each item down: the one listing its id, else the first one using its holes.
    first={}
    for n,s in enumerate(steps):
        for pid in s['part_ids']:first.setdefault(pid,n)
    items=[p for p in scene['parts'] if p['kind'] not in ('breadboard','development_board')]+list(scene['wires'])
    for it in items:
        if it['id'] not in first:
            first[it['id']]=next((n for n,s in enumerate(steps) if keys(it)&placed(s)),len(steps))
    rails={}
    for w in scene['wires']:
        for (p1,t1),(p2,t2) in ((( w['from_part'],w['from_terminal']),(w['to_part'],w['to_terminal'])),((w['to_part'],w['to_terminal']),(w['from_part'],w['from_terminal']))):
            m=RAIL.fullmatch(t1.strip().lower())
            if m and parts.get(p1,{}).get('kind')=='breadboard' and parts.get(p2,{}).get('kind')=='development_board':
                pin=t2.lower()
                if 'gnd' in pin:rails[(m[1],m[2])]=('−','#1e63c6')
                elif re.search(r'5v|3v3|3\.3|vin|vcc',pin):rails[(m[1],m[2])]=('+','#d32f2f')
    old,new,used=[],[],set()
    for it in items:
        n=first[it['id']]
        if n>i:continue
        is_new=n==i;out=new if is_new else old
        if 'from_part' in it:
            a,b=end(it['from_part'],it['from_terminal']),end(it['to_part'],it['to_terminal'])
            for pid,t in ((it['from_part'],it['from_terminal']),(it['to_part'],it['to_terminal'])):
                if parts.get(pid,{}).get('kind')=='development_board':used.add(t)
            if a and b:out.append(('w',draw_wire(it,a,b,is_new)))
            continue
        holes=[h for h in (hole_xy(x) for x in it['mount_holes']) if h]
        if not holes and is_new:  # no mount holes in the model: use this step's breadboard holes
            holes=[h for h in (hole_xy(pl['hole']) for pl in steps[i]['placements']) if h]
        if it['kind']=='led' and len(holes)>=2:out.append(('p',draw_led(it,holes[:2],is_new)))
        elif it['kind']=='resistor' and len(holes)>=2:out.append(('p',draw_resistor(it,holes[:2],is_new)))
        elif holes:out.append(('p',draw_generic(it,holes,is_new)))
    markers=[];marks=[]
    for n,pl in enumerate(steps[i]['placements'] if i<len(steps) else [],1):
        h=pl['hole'].strip().lower();m=PIN.fullmatch(h)
        if m:used.add(m[1])
        xy=board.xy(m[1]) if m else hole_xy(h)
        markers.append((n,pl['what'],pl['where'],pl['hole']))
        if xy:
            x,y=xy;mx,my=x+11,y-13
            marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="none" stroke="{HALO}" stroke-width="2.5"/><line x1="{x+3:.1f}" y1="{y-4:.1f}" x2="{mx:.1f}" y2="{my:.1f}" stroke="{HALO}" stroke-width="2"/><circle cx="{mx:.1f}" cy="{my:.1f}" r="8" fill="{HALO}" stroke="#fff" stroke-width="1.5"/><text x="{mx:.1f}" y="{my+3.5:.1f}" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">{n}</text>')
    layer=lambda xs,kind:''.join(s for k,s in xs if k==kind)
    body=(draw_board(board,used) if boards else '')+draw_breadboard(rails)+f'<g opacity=".35">{layer(old,"p")}{layer(old,"w")}</g>'+layer(new,'p')+layer(new,'w')+''.join(marks)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" font-family="system-ui,-apple-system,Segoe UI,sans-serif">{body}</svg>'
    page=f'<!doctype html><html><head><style>html,body{{margin:0;background:#fff}}svg{{display:block;width:100%;height:auto}}</style></head><body>{svg}</body></html>'
    return page,markers
