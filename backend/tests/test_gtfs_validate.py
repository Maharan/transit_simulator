from __future__ import annotations

from core.gtfs.validate import missing_required_files


def test_missing_required_files_detects_absent_inputs(tmp_path) -> None:
    (tmp_path / "agency.txt").write_text("id,name\n1,Agency\n", encoding="utf-8")
    (tmp_path / "routes.txt").write_text("route_id\nr1\n", encoding="utf-8")

    missing = missing_required_files(tmp_path)

    assert "agency.txt" not in missing
    assert "routes.txt" not in missing
    assert "stops.txt" in missing
    assert "trips.txt" in missing
