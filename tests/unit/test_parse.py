from __future__ import annotations

from pathlib import Path

from memento import parse


def test_migration_notes_structure(roam_dir: Path):
    pf = parse.load(roam_dir / "migration-notes.org")
    assert pf.file_uuid == "73f8e2a0-1234-5678-90ab-cdef12345678"
    assert pf.file_title == "Migration Notes"
    assert [(e.id_p, e.title) for e in pf.entries] == [
        (None, "Migration Notes"),
        (1, "Goals"),
        (2, "Constraints"),
        (3, "Risks"),
        (4, "Next steps"),
    ]


def test_id_p_enumerates_at_all_depths(roam_dir: Path):
    pf = parse.load(roam_dir / "architecture.org")
    assert [(e.id_p, e.title) for e in pf.entries] == [
        (None, "Architecture"),
        (1, "Components"),
        (2, "Boundaries"),
        (3, "Resolver internals"),
    ]


def test_descendants_excluded_from_parent_body(roam_dir: Path):
    pf = parse.load(roam_dir / "migration-notes.org")
    # "Goals" is followed by "** Constraints" -- its body must stop before the child.
    goals = next(e for e in pf.entries if e.title == "Goals")
    assert "Constraints" not in goals.body
    assert goals.body == "Halve inference latency per image and keep top-1 accuracy within one point."


def test_heading_with_property_drawer_body_starts_after_drawer(roam_dir: Path):
    pf = parse.load(roam_dir / "architecture.org")
    components = next(e for e in pf.entries if e.title == "Components")
    assert ":CREATED:" not in components.body
    assert ":PROPERTIES:" not in components.body
    assert components.body.startswith("The resolver")


def test_file_level_body_excludes_keywords(roam_dir: Path):
    pf = parse.load(roam_dir / "migration-notes.org")
    file_entry = pf.entries[0]
    assert "#+title" not in file_entry.body
    assert "#+filetags" not in file_entry.body
    assert ":PROPERTIES:" not in file_entry.body
    assert file_entry.body.startswith("We're distilling the large image classifier")


def test_body_byte_range_round_trips(roam_dir: Path):
    pf = parse.load(roam_dir / "migration-notes.org")
    for entry in pf.entries[1:]:
        sliced = pf.raw[entry.body_start : entry.body_end].decode("utf-8")
        assert entry.body == sliced.strip()
