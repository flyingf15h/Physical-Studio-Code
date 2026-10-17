import json

import pytest

from physical_studio.library import PartError, get_part, load_library, search_parts


def test_repo_parts_load():
    library = load_library()
    assert "arduino-uno" in library
    assert library["arduino-uno"]["body"]["size"] == [68.6, 53.4, 1.6]


def test_search_and_get():
    library = load_library()
    assert [p["id"] for p in search_parts(library, "uno")] == ["arduino-uno"]
    assert search_parts(library, "uno", category="fastener") == []
    with pytest.raises(KeyError, match="did you mean arduino-uno"):
        get_part(library, "arduino-uno-r3")


def test_bad_part_names_the_file(tmp_path):
    (tmp_path / "broken.json").write_text(json.dumps({"id": "broken", "name": "x", "category": "board"}))
    with pytest.raises(PartError, match="broken.json: missing body"):
        load_library(tmp_path)


def test_id_must_match_file_name(tmp_path):
    part = {"id": "other", "name": "x", "category": "misc", "body": {"size": [1, 1, 1]}}
    (tmp_path / "thing.json").write_text(json.dumps(part))
    with pytest.raises(PartError, match="must match the file name"):
        load_library(tmp_path)
