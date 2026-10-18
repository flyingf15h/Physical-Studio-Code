import pytest

from physical_studio.boms import parse_bom, parse_part
from physical_studio.looks import LookError
from physical_studio.users import Users

FEI_BOM = """Name    Link    Price (CAD)
    12V DC Motor    https://www.aliexpress.com/item/1005009213371004.html    6.40
    2x VL53L0X TOF Sensor    https://www.aliexpress.com/item/1005012456139246.html    7.30
    Teensy 4.1    https://ca.robotshop.com/products/teensy-41    60.13
    12v to 3v3 Regulator    https://www.aliexpress.com/item/1005005691344779.html
"""


def test_parse_bom_reads_a_pasted_shop_table():
    rows = parse_bom(FEI_BOM)
    assert [r["name"] for r in rows] == ["12V DC Motor", "VL53L0X TOF Sensor", "Teensy 4.1", "12v to 3v3 Regulator"]
    assert rows[1]["quantity"] == 2 and rows[1]["price"] == "7.30" and rows[1]["link"].endswith("246.html")
    assert rows[3]["price"] == "" and rows[3]["link"]


def test_parse_bom_reads_csv_and_tsv():
    assert parse_bom("Part,Link,Price\nTeensy 4.1,https://pjrc.com/t41,29.95\n")[0]["name"] == "Teensy 4.1"
    assert parse_bom("Teensy 4.1\thttps://pjrc.com/t41\t29.95\nAS5600\t\t2.00")[1] == {"name": "AS5600", "link": "", "price": "2.00", "quantity": 1}


def test_parse_part_needs_real_dimensions():
    row = {"name": "Teensy 4.1", "link": "https://pjrc.com/t41", "price": "29.95", "quantity": 1}
    part = parse_part('{"name": "Teensy 4.1", "category": "board", "size_mm": [61, 18, 4.5], "pins": [{"id": "13", "label": "LED"}], "source": "https://pjrc.com"}', row)
    assert part["body"]["size"] == [61.0, 18.0, 4.5] and part["category"] == "board" and not part["verified"]
    assert part["source"].startswith("From your BOM: https://pjrc.com/t41")
    with pytest.raises(LookError):
        parse_part('{"name": "x", "size_mm": [0, 0, 0]}', row)


def test_signup_login_sessions_and_saved_projects(tmp_path):
    users = Users(tmp_path)
    token, user = users.signup("Fei@Example.com", "correct horse", "Fei")
    assert user["email"] == "fei@example.com" and users.user_for(token)["id"] == user["id"]
    assert "correct horse" not in (tmp_path / ".accounts" / "users.json").read_text()
    with pytest.raises(ValueError):
        users.signup("fei@example.com", "another one")
    with pytest.raises(ValueError):
        users.login("fei@example.com", "wrong password")
    token2, _ = users.login("fei@example.com", "correct horse")
    users.logout(token)
    assert users.user_for(token) is None and users.user_for(token2)
    users.save_project(user["id"], {"design": "build/abc123", "title": "Traffic light", "steps": 15})
    users.save_project(user["id"], {"design": "double-pendulum", "title": "Pendulum"})
    assert [p["design"] for p in users.projects(user["id"])] == ["double-pendulum", "build/abc123"]
    with pytest.raises(ValueError):
        users.save_project(user["id"], {"design": "../../etc/passwd"})
    users.forget_project(user["id"], "double-pendulum")
    assert [p["design"] for p in users.projects(user["id"])] == ["build/abc123"]
