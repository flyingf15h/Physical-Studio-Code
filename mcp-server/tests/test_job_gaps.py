from types import SimpleNamespace

from physical_studio.jobs import DesignJob as Job
from physical_studio.server import PARTS_DIR, Studio


def gaps(prompt, build):
    s = Studio(PARTS_DIR)
    s.new_design("t")
    build(s)
    return Job.gaps(SimpleNamespace(studio=s, prompt=prompt))


def test_parts_named_in_the_request_must_be_placed():
    out = gaps("Teensy 4.1 reads an AS5600 encoder; M3x6 screws, 12 V supply, 2020 frame",
               lambda s: (s.place_part("teensy-41", (0, 0, 0)), s.place_part("led-5mm", (60, 0, 0))))
    assert any("AS5600" in p for p in out)
    assert not any("Teensy" in p or "M3x6" in p or "2020" in p for p in out)
    assert any("no wires" in p for p in out)  # a board with nothing wired


def test_a_complete_request_has_no_gaps():
    assert gaps("A Teensy 4.1 in a case", lambda s: s.place_part("teensy-41", (0, 0, 0))) == []
