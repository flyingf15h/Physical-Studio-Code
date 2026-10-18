# Ported from circuit-studio/geometry.py at 21a4f23 (unchanged): scene -> GLB + labels; mesh
# nodes are named <id>__..., so a viewer can map a click back to a part or wire.
import re
import numpy as np
import trimesh


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
    '#79644c':PALETTE['slate'], '#8c7561':PALETTE['brown'], '#b7a16b':PALETTE['yellow']
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
    scene=trimesh.Scene();groups={};anchors={};labels=[];centers={};partmap={p.id:p for p in spec.parts}
    def add(m,pid,col):
        col=muted_color(col)
        m.visual.vertex_colors=list(bytes.fromhex(col[1:]))+[255];groups.setdefault(pid,[]).append(m)
    def box(pid,c,s,col):
        m=trimesh.creation.box(extents=s);m.apply_translation(c);add(m,pid,col)
    def rod(pid,a,b,r,col,n=12):
        a,b=np.array(a,float),np.array(b,float);d=b-a
        if np.linalg.norm(d)<1e-7:return
        m=trimesh.creation.cylinder(radius=r,height=np.linalg.norm(d),sections=n)
        m.apply_transform(trimesh.geometry.align_vectors([0,0,1],d));m.apply_translation((a+b)/2);add(m,pid,col)
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
        groups.setdefault(pid,[]).append(m)
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
            for ch,dy in zip('abcdefghij',[16.51,13.97,11.43,8.89,6.35,-6.35,-8.89,-11.43,-13.97,-16.51]):hm[ch+str(row)]=np.array([x-78.74+(row-1)*2.54,y+dy,8.])
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
    for p in spec.parts:
        pid=p.id;x,y,z=centers[pid];anchors[pid]={};labels.append({'id':pid,'name':p.name,'kind':p.kind})
        if p.kind=='breadboard':
            box(pid,[x,y,3],[165,55,6],'#e2e2d9')
            box(pid,[x,y,6.1],[160,2.6,.15],'#60676b')
            recessed_panel(pid,list(holes[pid].values()))
            for xx in [-81.25,81.25]:box(pid,[x+xx,y,7],[2.5,55,2],'#efefe8')
            for yy in [-26.75,26.75]:box(pid,[x,y+yy,7],[165,1.5,2],'#efefe8')
            for yy in [-3.55,3.55]:box(pid,[x,y+yy,7],[160,4.25,2],'#efefe8')
            for yy in [-19.05,19.05]:box(pid,[x,y+yy,7],[160,2.54,2],'#efefe8')
            for yy,col in [(-25.8,'#d94b4b'),(-20.12,'#4b87c8'),(20.12,'#4b87c8'),(25.8,'#d94b4b')]:box(pid,[x,y+yy,8.04],[157,.28,.06],col)
            anchors[pid]=holes[pid]
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
            rod(pid,[x,y,z],[x,y,z+3.5],2.5,p.color,24);rod(pid,[x,y,z-.3],[x,y,z+.25],2.8,p.color,24)
            dome=trimesh.creation.uv_sphere(radius=2.5,count=[12,20]);dome.apply_translation([x,y,z+3.5]);add(dome,pid,p.color)
        elif p.kind=='resistor':
            a=np.array([x-5.08,y,8]);b=np.array([x+5.08,y,8])
            if p.mount_board in holes and len(p.mount_holes)>=2:
                hm=holes[p.mount_board]
                if all(h.lower() in hm for h in p.mount_holes[:2]):a,b=[hm[h.lower()].copy() for h in p.mount_holes[:2]];x,y=((a+b)/2)[:2]
            direction=b-a;direction[2]=0;length=np.linalg.norm(direction)
            direction=direction/length if length>.1 else np.array([1.,0,0])
            mid=np.array([x,y,z]);u=mid-direction*2.8;v=mid+direction*2.8
            rod(pid,a,u,.19,'#bbc1c5');rod(pid,v,b,.19,'#bbc1c5');rod(pid,u,v,1.15,'#cbb78b')
            for off,col in [(-1.7,'#79644c'),(-.6,'#8c7561'),(.5,'#79644c'),(2.,'#b7a16b')]:rod(pid,mid+direction*off,mid+direction*(off+.3),1.18,col)
            anchors[pid]={'1':a,'2':b,'input':a,'output':b}
        else:
            s=np.array(p.size_mm,float);box(pid,[x,y,z],s,p.color)
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
        for u,v in zip(pts,pts[1:]):rod(w.id,u,v,.48,w.color)
        for p,pos in [(w.from_part,a),(w.to_part,b)]:
            if partmap[p].kind=='development_board':box(w.id,pos+[0,0,1.5],[1.8,1.8,3.],'#323a40')
    for pid,items in groups.items():
        scene.add_geometry(trimesh.util.concatenate(items),geom_name=pid+'__mesh',node_name=pid+'__mesh')
    scene.apply_transform(np.array([[.001,0,0,0],[0,0,.001,0],[0,-.001,0,0],[0,0,0,1]]))
    return scene.export(file_type='glb'),labels
