# Ported from circuit-studio/app.py at 21a4f23: the scene format (Spec) and validate(), without the
# Streamlit page. A scene is the breadboard, a board, parts in holes and wires, in mm.
import re
import numpy as np
from pydantic import BaseModel, Field

class Terminal(BaseModel):
    name:str=Field(description="Terminal label such as gpio25 or gnd. Lowercase without spaces.")
    pin_index:int=Field(ge=1,le=38,description="Visible physical anchor index; symbolic unless known from board documentation. Pins 1..19 run along negative Y, 20..38 along positive Y.")
class Part(BaseModel):
    id:str
    name:str
    kind:str=Field(description="breadboard, development_board, led, resistor, generic")
    color:str=Field(description="Hex RGB")
    center_mm:list[float]
    size_mm:list[float]
    mount_board:str=Field(description="Breadboard ID, or empty string")
    mount_holes:list[str]=Field(description="For LED: [anode hole, cathode hole]. Resistor: [terminal1 hole, terminal2 hole]. Empty if unknown. Holes a1..j63.")
    terminals:list[Terminal]=Field(description="For development_board only: named terminals to visible pin anchors. Empty for other kinds.")
    evidence:str
class Wire(BaseModel):
    id:str
    name:str
    from_part:str
    from_terminal:str
    to_part:str
    to_terminal:str
    color:str
    connection_note:str
class Spec(BaseModel):
    parts:list[Part]
    wires:list[Wire]
    assumptions:list[str]

def validate(s):
    if not 1<=len(s.parts)<=50 or len(s.wires)>100:raise ValueError('Scene too large for this prototype.')
    seen=set();pids={p.id for p in s.parts}
    for item in list(s.parts)+list(s.wires):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,59}',item.id) or item.id in seen:raise ValueError('Invalid or duplicate part ID.')
        seen.add(item.id)
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',item.color):raise ValueError('Invalid color.')
    for p in s.parts:
        if p.kind not in {'breadboard','development_board','led','resistor','generic'}:raise ValueError('Unknown part kind.')
        if len(p.center_mm)!=3 or len(p.size_mm)!=3 or not all(np.isfinite(v) and abs(v)<2000 for v in p.center_mm) or not all(np.isfinite(v) and .1<=v<=1000 for v in p.size_mm):raise ValueError('Invalid dimensions.')
        names=[t.name.lower().replace(' ','') for t in p.terminals]
        if len(names)!=len(set(names)):raise ValueError('Duplicate terminal name.')
        if p.mount_board and p.mount_board not in pids:raise ValueError('Missing mounting board.')
    for w in s.wires:
        if w.from_part not in pids or w.to_part not in pids:raise ValueError('Wire refers to missing component.')
    return s
