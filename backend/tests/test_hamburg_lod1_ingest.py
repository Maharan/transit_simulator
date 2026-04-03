from __future__ import annotations

from pathlib import Path

from core.built_environment.ingest import (
    find_hamburg_lod1_dataset_dir,
    infer_hamburg_lod1_dataset_release,
    ingest_hamburg_lod1_directory,
    load_hamburg_lod1_file_records,
    project_hamburg_building_point_to_wgs84,
)


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "hamburg_lod1"
DATASET_DIR = FIXTURES_ROOT / "LoD1-DE_HH_2023-04-01"
TILE_PATH = DATASET_DIR / "LoD1_32_550_5937_1_HH.xml"


def test_infer_hamburg_lod1_dataset_release_reads_directory_name() -> None:
    assert (
        infer_hamburg_lod1_dataset_release(Path("LoD1-DE_HH_2023-04-01"))
        == "2023-04-01"
    )


def test_find_hamburg_lod1_dataset_dir_selects_requested_release() -> None:
    assert (
        find_hamburg_lod1_dataset_dir(FIXTURES_ROOT, dataset_release="2023-04-01")
        == DATASET_DIR
    )


def test_load_hamburg_lod1_file_records_extracts_building_fields() -> None:
    records = load_hamburg_lod1_file_records(TILE_PATH, dataset_release="2023-04-01")

    assert records == [
        {
            "dataset_release": "2023-04-01",
            "tile_id": "LoD1_32_550_5937_1_HH",
            "gml_id": "DEHHTEST0001",
            "building_name": "Test Building",
            "function_code": "31001_1000",
            "municipality_code": "02100000",
            "street_name": "Example Street",
            "street_number": "5",
            "postal_code": "20095",
            "locality_name": "Hamburg",
            "country_name": "Germany",
            "measured_height_m": 12.5,
            "storeys_above_ground": 4,
            "ground_elevation_m": 4.0,
            "roof_elevation_m": 16.5,
            "representative_lat": records[0]["representative_lat"],
            "representative_lon": records[0]["representative_lon"],
            "raw_attributes": {
                "Gemeindeschluessel": "02100000",
                "Grundrissaktualitaet": "2023-01-26",
            },
            "source_srs_name": "urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH",
            "source_path": str(TILE_PATH),
            "footprint_geom": "MULTIPOLYGON (((550000 5937000, 550010 5937000, 550010 5937010, 550000 5937010, 550000 5937000)))",
        }
    ]
    assert 53.0 < records[0]["representative_lat"] < 54.0
    assert 9.0 < records[0]["representative_lon"] < 11.0


def test_project_hamburg_building_point_to_wgs84_returns_hamburg_like_point() -> None:
    lat, lon = project_hamburg_building_point_to_wgs84(550005, 5937005)

    assert 53.0 < lat < 54.0
    assert 9.0 < lon < 11.0


def test_ingest_hamburg_lod1_directory_dry_run_counts_buildings() -> None:
    row_count = ingest_hamburg_lod1_directory(
        DATASET_DIR,
        database_url="postgresql://example",
        dataset_release="2023-04-01",
        dry_run=True,
    )

    assert row_count == 1
