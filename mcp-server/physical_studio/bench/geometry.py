# Ported from circuit-studio/geometry.py at 21a4f23 (unchanged): scene -> GLB + labels; mesh
# nodes are named <id>__..., so a viewer can map a click back to a part or wire.
import re
import numpy as np
import trimesh
from .looks import material, uno_pins, uno_top


PALETTE = {
    'red':'#d98186', 'yellow':'#e0c875', 'green':'#83c6a2',
    'blue':'#83a8d0', 'purple':'#ae92c4', 'brown':'#b8a197',
    'cream':'#e7e5df', 'slate':'#5f6670', 'metal':'#bcc2c9',
    'well':'#6d747b', 'wall':'#b0b1ac'
}
_FIXED = {
    '#e2e2d9':PALETTE['cream'], '#efefe8':PALETTE['cream'], '#e9e9e2':PALETTE['cream'],
    '#60676b':PALETTE['well'], '#d94b4b':'#cb9295', '#4b87c8':'#8aa9c7',
    '#293139':PALETTE['slate'], '#20282c':PALETTE['slate'], '#151c22':PALETTE['slate'],
    '#30383d':PALETTE['slate'], '#333b41':PALETTE['slate'], '#1b2228':PALETTE['slate'],
    '#323a40':PALETTE['slate'], '#bca568':PALETTE['brown'], '#c2b58d':PALETTE['brown'],
    '#c2b888':PALETTE['metal'], '#bbc1c5':PALETTE['metal'], '#b3bbc1':PALETTE['metal'],
    '#bdc5cc':PALETTE['metal'], '#aab1b7':PALETTE['metal'], '#cbb78b':PALETTE['brown'],
    '#79644c':PALETTE['slate'], '#8c7561':PALETTE['brown'], '#b7a16b':PALETTE['yellow'],
    '#1f7f86':'#4f979d', '#d6d9dc':'#d6d9dc', '#b85a50':'#c4736b'
}
def muted_color(value):
    import colorsys
    value=value.lower()
    if value in _FIXED:return _FIXED[value]
    if value in PALETTE.values():return value
    rgb=np.array(list(bytes.fromhex(value[1:])),float)/255
    h,s,v=colorsys.rgb_to_hsv(*rgb)
    if s<.18:return PALETTE['cream'] if v>.83 else PALETTE['metal'] if v>.58 else PALETTE['slate']
    if h<.06 or h>=.94:return PALETTE['red']
    if h<.13:return PALETTE['brown'] if v<.8 else PALETTE['yellow']
    if h<.22:return PALETTE['yellow']
    if h<.48:return PALETTE['green']
    if h<.72:return PALETTE['blue']
    return PALETTE['purple']

def build(spec):
    scene=trimesh.Scene();groups={};finished={};textured={};anchors={};labels=[];centers={};partmap={p.id:p for p in spec.parts}
    def add(m,pid,col,kind=''):
        # real colours with a finish per colour (looks.py); meshes of one part and colour share a material
        finished.setdefault(pid,{}).setdefault((col.lower(),kind),[]).append(m)
    def box(pid,c,s,col,kind=''):
        m=trimesh.creation.box(extents=s);m.apply_translation(c);add(m,pid,col,kind)
    def rod(pid,a,b,r,col,n=12,kind=''):
        a,b=np.array(a,float),np.array(b,float);d=b-a
        if np.linalg.norm(d)<1e-7:return
        m=trimesh.creation.cylinder(radius=r,height=np.linalg.norm(d),sections=n)
        m.apply_transform(trimesh.geometry.align_vectors([0,0,1],d));m.apply_translation((a+b)/2);add(m,pid,col,kind)
    BANDS=['#1b1b1b','#7a4a26','#d23b2c','#e8822a','#efd23c','#3d9a4a','#2e5fb8','#8a52b8','#8d8d8d','#f4f4f4']
    def bands(name):
        """A resistor's colour bands from its value in the name (220 ohm: red red brown, gold)."""
        m=re.search(r'(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:ohm|Ω|r\b)',name) or re.search(r'(\d+(?:\.\d+)?)([kKmM])\b',name)
        if not m:return ['#7a4a26','#1b1b1b','#d23b2c','#c8a85a']
        v=float(m.group(1))*{'':1,'k':1e3,'m':1e6}[m.group(2).lower()]
        e=0
        while v>=100:v/=10;e+=1
        while v<10 and e>-1:v*=10;e-=1
        a,b=divmod(int(round(v)),10)
        return [BANDS[min(a,9)],BANDS[b],BANDS[max(0,e)] if e>=0 else '#c8a85a','#c8a85a']
    def recessed_panel(pid,holes):
        verts=[];faces=[];face_colors=[]
        top=list(bytes.fromhex(PALETTE['cream'][1:]))+[255]
        wall=list(bytes.fromhex(PALETTE['wall'][1:]))+[255]
        floor_color=list(bytes.fromhex(PALETTE['well'][1:]))+[255]
        def quad(points,color):
            i=len(verts);verts.extend(points)
            faces.extend([[i,i+1,i+2],[i,i+2,i+3]])
            face_colors.extend([color,color])
        for x,y,z in holes:
            o=1.27;h=.58;floor=z-1.8
            outer=[(x-o,y-o,z),(x+o,y-o,z),(x+o,y+o,z),(x-o,y+o,z)]
            inner=[(x-h,y-h,z),(x+h,y-h,z),(x+h,y+h,z),(x-h,y+h,z)]
            low=[(a,b,floor) for a,b,_ in inner]
            for j in range(4):
                k=(j+1)%4
                quad([outer[j],outer[k],inner[k],inner[j]],top)
                quad([inner[j],inner[k],low[k],low[j]],wall)
            quad(low,floor_color)
        m=trimesh.Trimesh(vertices=np.array(verts),faces=np.array(faces),process=False)
        m.visual.face_colors=np.array(face_colors,dtype=np.uint8)
        groups.setdefault(pid,[]).append(m)  # the hole grid keeps its per-face colours
    holes={}
    boards=[p for p in spec.parts if p.kind=='breadboard']
    for p in spec.parts:
        c=np.array(p.center_mm,float)
        if p.kind=='breadboard':c[2]=4
        elif p.kind=='development_board':c[2]=6
        centers[p.id]=c
    for p in spec.parts:
        if p.kind!='development_board':continue
        c=centers[p.id]
        for b in boards:
            bc=centers[b.id]
            if abs(c[0]-bc[0])<112 and abs(c[1]-bc[1])<43:c[1]=bc[1]+55
    for b in boards:
        x,y,z=centers[b.id];hm={}
        for row in range(1,64):
            for ch,dy in zip('abcdefghij',[13.97,11.43,8.89,6.35,3.81,-3.81,-6.35,-8.89,-11.43,-13.97]):hm[ch+str(row)]=np.array([x-78.74+(row-1)*2.54,y+dy,8.])
            for side in [-1,1]:
                for rail in [21.6,24.14]:hm[f'rail_{side}_{rail}_{row}']=np.array([x-78.74+(row-1)*2.54,y+side*rail,8.])
        holes[b.id]=hm
    def nearest_hole(pos):
        candidates=[v for hm in holes.values() for k,v in hm.items() if not k.startswith('rail')]
        return min(candidates,key=lambda v:np.linalg.norm(v[:2]-pos[:2])) if candidates else None
    for p in spec.parts:
        if p.kind not in {'led','resistor'}:continue
        c=centers[p.id];h=nearest_hole(c)
        if p.mount_board in holes and p.mount_holes and p.mount_holes[0].lower() in holes[p.mount_board]:h=holes[p.mount_board][p.mount_holes[0].lower()]
        if h is not None and (p.mount_board in holes or np.linalg.norm(h[:2]-c[:2])<25):
            if p.kind=='led':c[:2]=h[:2]+[1.27,0];c[2]=14.5
            else:c[:2]=h[:2]+[5.08,0];c[2]=10
    def legs(pid,p,top):
        hm=holes.get(p.mount_board) or {}
        pts=[hm[h.lower()] for h in p.mount_holes if h.lower() in hm]
        for v in pts:rod(pid,v,[v[0],v[1],top],.25,'#bbc1c5',6)
        return pts
    def generic(pid,p,x,y,z,s):
        """A recognisable shape for the common modules (by name), else a box of the part's size."""
        name=p.name.lower()
        if re.search(r'hc-?sr04|ultrasonic',name):  # stands upright on its 4 pins, the two transducers facing out
            pts=legs(pid,p,10.5);hx,hy=(np.mean(pts,0)[:2] if pts else (x,y))
            box(pid,[hx,hy,20.5],[45,1.6,20],p.color)
            for dx in (-13,13):
                rod(pid,[hx+dx,hy-.8,20.5],[hx+dx,hy-12.8,20.5],8,'#bdc5cc',32)
                rod(pid,[hx+dx,hy-12.8,20.5],[hx+dx,hy-13,20.5],6.5,'#5f6670',32)
            box(pid,[hx,hy+1.2,26],[6,1,3],'#bdc5cc')  # crystal on the back
        elif re.search(r'matrix|max7219',name):
            box(pid,[x,y,z],s,'#1f7f86' if re.search(r'#0*2[0-9a-f]{5}',p.color.lower()) else p.color)
            m=min(s[0],s[1])-1;top=z+s[2]/2
            box(pid,[x,y,top+3],[m,m,6],'#1b2228')
            for i in range(8):
                for j in range(8):
                    cx=x-m/2+m/16+i*m/8;cy=y-m/2+m/16+j*m/8
                    rod(pid,[cx,cy,top+6],[cx,cy,top+6.15],m/20,'#b85a50',10)
        elif re.search(r'joystick|ky-?023',name):
            box(pid,[x,y,z],s,p.color);top=z+s[2]/2
            box(pid,[x+3,y,top+5],[16,16,10],'#1b2228')
            rod(pid,[x+3,y,top+10],[x+3,y,top+17],2,'#1b2228',16)
            rod(pid,[x+3,y,top+17],[x+3,y,top+22],7,'#30383d',32)
        elif re.search(r'buzzer|piezo',name):
            pts=legs(pid,p,8.5);hx,hy=(np.mean(pts,0)[:2] if pts else (x,y))
            rod(pid,[hx,hy,8.5],[hx,hy,8.5+s[2]],s[0]/2,'#1b2228',40)
            rod(pid,[hx,hy,8.5+s[2]],[hx,hy,8.6+s[2]],1.2,'#5f6670',16)
        elif re.search(r'button|switch',name):
            pts=legs(pid,p,8.5);hx,hy=(np.mean(pts,0)[:2] if pts else (x,y))
            box(pid,[hx,hy,10.3],[s[0],s[1],3.6],'#1b2228');box(pid,[hx,hy,12.25],[s[0]-.4,s[1]-.4,.3],'#bdc5cc')
            rod(pid,[hx,hy,12.4],[hx,hy,8.5+s[2]],3.5,'#30383d',32)
        elif re.search(r'photo|ldr|light.dependent',name):
            pts=legs(pid,p,12);hx,hy=(np.mean(pts,0)[:2] if pts else (x,y))
            rod(pid,[hx,hy,12],[hx,hy,14],2.6,'#d6d9dc',32);rod(pid,[hx,hy,14],[hx,hy,14.05],2.2,'#b85a50',32)
        elif re.search(r'thermistor|ntc',name):
            pts=legs(pid,p,13);hx,hy=(np.mean(pts,0)[:2] if pts else (x,y))
            bead=trimesh.creation.uv_sphere(radius=1.6,count=[10,14]);bead.apply_translation([hx,hy,14]);add(bead,pid,'#1b2228')
        else:box(pid,[x,y,z],s,p.color)
    for p in spec.parts:
        pid=p.id;x,y,z=centers[pid];anchors[pid]={};labels.append({'id':pid,'name':p.name,'kind':p.kind})
        if p.kind=='breadboard':
            box(pid,[x,y,3],[165,55,6],'#e2e2d9')
            box(pid,[x,y,6.1],[160,2.6,.15],'#60676b')
            recessed_panel(pid,list(holes[pid].values()))
            for xx in [-81.25,81.25]:box(pid,[x+xx,y,7],[2.5,55,2],'#efefe8')
            for yy in [-26.75,26.75]:box(pid,[x,y+yy,7],[165,1.5,2],'#efefe8')
            for yy in [-2.2,2.2]:box(pid,[x,y+yy,7],[160,1.6,2],'#efefe8')  # a real board's e-f gap is 0.3"
            for yy in [-17.8,17.8]:box(pid,[x,y+yy,7],[160,5.0,2],'#efefe8')
            # rail lines like a real board turned so column a is on top: blue (-) on the outer edge above column a (the
            # planner's ground rail, rail_1_24.14), red (+) inside it; the far edge the other way round
            for yy,col in [(-25.8,'#d94b4b'),(-20.12,'#4b87c8'),(20.12,'#d94b4b'),(25.8,'#4b87c8')]:box(pid,[x,y+yy,8.04],[157,.28,.06],col)
            anchors[pid]=holes[pid]
        elif p.kind=='development_board' and re.search(r'\buno\b',p.name,re.I):
            # parts/arduino-uno.json's layout (origin at the board's bottom-left corner, USB and power jack on -x)
            x0,y0=x-34.3,y-26.7;L=lambda u,v,w=0:[x0+u,y0+v,w]
            box(pid,[x,y,5],[68.6,53.4,1.6],'#00737a');textured[pid]=uno_top(x0,y0,5.82)
            box(pid,L(1.8,38.1,11.25),[16,12,10.9],'#c9cdd2')  # USB-B socket, out 6.2 mm past the edge
            box(pid,L(-1.8,38.1,8.5),[.4,8,5],'#111316')
            box(pid,L(5.2,7.6,11.3),[14,9,11],'#1b2228')  # power jack
            rod(pid,L(-1.9,7.6,12),L(-1.7,7.6,12),3.2,'#111316',24)
            box(pid,L(46,17,7.45),[35.6,7.4,3.3],'#151c22')  # ATmega328P (DIP-28) in its socket
            box(pid,L(46,17,6.1),[37,10,.6],'#1b2228')
            rod(pid,L(29.2,17,9.12),L(29.2,17,9.15),.7,'#30383d',16)  # pin-1 dimple
            for i in range(14):
                for side in (-1,1):box(pid,L(29.5+i*2.54,17+side*4.1,6.9),[.5,1,2.2],'#c9cdd2')
            box(pid,L(19,36,6.3),[5,5,1],'#151c22')  # ATmega16U2
            box(pid,L(24,23,6.6),[4.6,1.9,1.6],'#c9cdd2')  # 16 MHz crystal
            for u in (16.5,21.5):  # electrolytic caps by the jack
                rod(pid,L(u,5.5,5.8),L(u,5.5,11.3),2.6,'#c9cdd2',28);rod(pid,L(u,5.5,11.3),L(u,5.5,11.35),2.2,'#9aa1a8',28)
            box(pid,L(6.5,49,6.6),[6,6,1.6],'#c9cdd2');rod(pid,L(6.5,49,7.4),L(6.5,49,8.6),1.6,'#b8433a',20)  # reset button
            for (u,v),col in zip([(12.5,45),(12.5,42.5),(12.5,40.5),(60,28)],['#f2b233','#f2b233','#f2b233','#5fd16b']):box(pid,L(u,v,6.1),[1.6,.8,.6],col,'led')
            box(pid,L(64,27,7.1),[5.1,7.6,2.5],'#1b2228')  # ICSP header
            for i in range(2):
                for j in range(3):rod(pid,L(62.73+i*2.54,24.46+j*2.54,8.3),L(62.73+i*2.54,24.46+j*2.54,14),.32,'#c8a85a',6)
            pins=uno_pins();rows={}
            for q in pins:rows.setdefault(q['position'][1],[]).append(q)
            for v,row in rows.items():  # one black header per run of pins 2.54 mm apart, with a dark socket per pin
                row=sorted(row,key=lambda q:q['position'][0]);run=[row[0]]
                for q in row[1:]+[None]:
                    if q and abs(q['position'][0]-run[-1]['position'][0]-2.54)<.1:run.append(q);continue
                    u0,u1=run[0]['position'][0],run[-1]['position'][0]
                    box(pid,L((u0+u1)/2,v,10.05),[u1-u0+2.54,2.54,8.5],'#1b2228')
                    for r in run:box(pid,L(r['position'][0],v,14.31),[1,1,.04],'#050607')
                    if q:run=[q]
            pinpoints=[np.array(L(q['position'][0],q['position'][1],14.4)) for q in pins]
            anchors[pid]={f'pin{i+1}':pinpoints[i%len(pinpoints)] for i in range(38)}
            by={}
            for q,pos in zip(pins,pinpoints):
                for k in {q['id'].lower(),q['label'].lower().replace('~','')}:by.setdefault(re.sub(r'\d+$','',k) if k.startswith('gnd') else k,[]).append(pos)
            seen={}
            for t in p.terminals:
                k=t.name.lower().replace(' ','').replace('~','');k='gnd' if k.startswith('gnd') else re.sub(r'^pin(?=\d)','d',k)
                if k in by:anchors[pid][t.name.lower()]=by[k][seen.get(k,0)%len(by[k])];seen[k]=seen.get(k,0)+1
                else:anchors[pid][t.name.lower()]=pinpoints[(t.pin_index-1)%len(pinpoints)]
        elif p.kind=='development_board':
            box(pid,[x,y,5],[55,28,1.6],'#293139')
            box(pid,[x-7,y,7.3],[22,17,3],'#b3bbc1')
            box(pid,[x-23,y,6.05],[8,22,.35],'#20282c')
            for i in range(5):box(pid,[x-25+i*1.1,y,6.3],[.35,17,.12],'#bca568')
            box(pid,[x+25.5,y,7],[8,8,4],'#bdc5cc');box(pid,[x+29.6,y,7],[.15,6,2],'#30383d')
            box(pid,[x+9,y,6.6],[8,7,1.4],'#151c22')
            for yy in [-8.7,8.7]:
                box(pid,[x+21,y+yy,6.6],[4,3,1.5],'#aab1b7');box(pid,[x+21,y+yy,7.5],[2,1.8,.5],'#333b41')
            for i in range(5):box(pid,[x+3+i*2.3,y-6,6.4],[1.4,1.1,.8],'#c2b58d')
            # Named terminals are assigned explicit visible anchor positions by scene data,
            # not guessed electrical connectivity or an asserted manufacturer pinout.
            pinpoints=[]
            for side in [-1,1]:
                box(pid,[x,y+side*12.5,4],[49,2.3,2.4],'#1b2228')
                for i in range(19):
                    xx=x-22.86+i*2.54;yy=y+side*12.5;pos=np.array([xx,yy,8.5]);pinpoints.append(pos)
                    rod(pid,[xx,yy,.8],pos,.25,'#c2b888',6)
            anchors[pid]={f'pin{i+1}':v for i,v in enumerate(pinpoints)}
            for t in p.terminals:
                anchors[pid][t.name.lower()]=pinpoints[t.pin_index-1]
        elif p.kind=='led':
            a=np.array([x-1.27,y,z-6.5]);b=np.array([x+1.27,y,z-6.5])
            if p.mount_board in holes and len(p.mount_holes)>=2:
                hm=holes[p.mount_board]
                if all(h.lower() in hm for h in p.mount_holes[:2]):a,b=[hm[h.lower()].copy() for h in p.mount_holes[:2]];x,y=((a+b)/2)[:2]
            anchors[pid]={'anode':a,'cathode':b,'1':a,'2':b}
            for v in [a,b]:rod(pid,v,[v[0],v[1],z+1],.21,'#bbc1c5')
            rod(pid,[x,y,z],[x,y,z+3.5],2.5,p.color,32,'led');rod(pid,[x,y,z-.3],[x,y,z+.25],2.8,p.color,32,'led')
            dome=trimesh.creation.uv_sphere(radius=2.5,count=[16,32]);dome.apply_translation([x,y,z+3.5]);add(dome,pid,p.color,'led')
        elif p.kind=='resistor':
            a=np.array([x-5.08,y,8]);b=np.array([x+5.08,y,8])
            if p.mount_board in holes and len(p.mount_holes)>=2:
                hm=holes[p.mount_board]
                if all(h.lower() in hm for h in p.mount_holes[:2]):a,b=[hm[h.lower()].copy() for h in p.mount_holes[:2]];x,y=((a+b)/2)[:2]
            direction=b-a;direction[2]=0;length=np.linalg.norm(direction)
            direction=direction/length if length>.1 else np.array([1.,0,0])
            mid=np.array([x,y,z]);u=mid-direction*2.8;v=mid+direction*2.8
            rod(pid,a,u,.19,'#bbc1c5');rod(pid,v,b,.19,'#bbc1c5');rod(pid,u,v,1.15,'#d9c08a',20)
            for off,col in zip([-1.7,-.9,-.1,1.5],bands(p.name)):rod(pid,mid+direction*off,mid+direction*(off+.45),1.18,col,20)
            anchors[pid]={'1':a,'2':b,'input':a,'output':b}
        else:
            s=np.array(p.size_mm,float);generic(pid,p,x,y,z,s)
            anchors[pid]={'1':np.array([x-s[0]/2,y,z]),'2':np.array([x+s[0]/2,y,z])}
    for w in spec.wires:
        def endpoint(pid,name):
            aa=anchors[pid];key=name.lower().replace(' ','')
            if key not in aa:raise ValueError(f'Unknown terminal {name} on {pid}. Regenerate with explicit supported terminal names.')
            return aa[key].copy()
        a=endpoint(w.from_part,w.from_terminal);b=endpoint(w.to_part,w.to_terminal)
        labels.append({'id':w.id,'name':w.name,'kind':'wire'})
        height=max(a[2],b[2])+max(8,min(35,np.linalg.norm(b[:2]-a[:2])*.35))
        ctrl=(a+b)/2;ctrl[2]=2*height-(a[2]+b[2])/2
        pts=[(1-t)**2*a+2*t*(1-t)*ctrl+t*t*b for t in np.linspace(0,1,41)]
        for u,v in zip(pts,pts[1:]):rod(w.id,u,v,.48,w.color,12,'wire')
        for p,pos in [(w.from_part,a),(w.to_part,b)]:
            if partmap[p].kind=='development_board':box(w.id,pos+[0,0,1.5],[1.8,1.8,3.],'#323a40')
    for pid,items in groups.items():
        scene.add_geometry(trimesh.util.concatenate(items),geom_name=pid+'__mesh',node_name=pid+'__mesh')
    for pid,byfinish in finished.items():
        for k,((col,kind),items) in enumerate(byfinish.items()):
            m=trimesh.util.concatenate(items);m.visual=trimesh.visual.TextureVisuals(material=material(col,kind))
            scene.add_geometry(m,geom_name=f'{pid}__m{k}',node_name=f'{pid}__m{k}')
    for pid,m in textured.items():scene.add_geometry(m,geom_name=pid+'__top',node_name=pid+'__top')
    scene.apply_transform(np.array([[.001,0,0,0],[0,0,.001,0],[0,-.001,0,0],[0,0,0,1]]))
    return scene.export(file_type='glb'),labels
