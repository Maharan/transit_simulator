from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from sqlalchemy import create_engine, delete, insert, text

from .models import HamburgLod1Building


DEFAULT_HAMBURG_LOD1_DATASET_RELEASE = "2023-04-01"
DATASET_DIR_PATTERN = re.compile(r"^LoD1-DE_HH_(?P<dataset_release>\d{4}-\d{2}-\d{2})$")
SOURCE_CRS_EPSG = 25832
WGS84_CRS_EPSG = 4326
EXPECTED_SOURCE_SRS_NAME = "urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH"
LOD1_TO_WGS84 = Transformer.from_crs(
    f"EPSG:{SOURCE_CRS_EPSG}",
    f"EPSG:{WGS84_CRS_EPSG}",
    always_xy=True,
)
NAMESPACES = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "core": "http://www.opengis.net/citygml/1.0",
    "gen": "http://www.opengis.net/citygml/generics/1.0",
    "gml": "http://www.opengis.net/gml",
    "xAL": "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
}
GML_ID_ATTRIBUTE = f"{{{NAMESPACES['gml']}}}id"


def _normalize_optional_str(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def infer_hamburg_lod1_dataset_release(dataset_dir: Path) -> str:
    match = DATASET_DIR_PATTERN.search(Path(dataset_dir).name)
    if not match:
        raise ValueError(
            f"Unsupported Hamburg LoD1 dataset directory name: {Path(dataset_dir).name}"
        )
    return match.group("dataset_release")


def find_hamburg_lod1_dataset_dir(
    root_dir: Path,
    dataset_release: str = DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
) -> Path:
    root_dir = Path(root_dir)
    if not root_dir.exists():
        raise FileNotFoundError(f"Hamburg LoD1 root folder not found: {root_dir}")

    candidates: list[Path] = []
    try:
        if infer_hamburg_lod1_dataset_release(root_dir) == dataset_release:
            return root_dir
    except ValueError:
        pass

    for path in sorted(root_dir.iterdir()):
        if not path.is_dir():
            continue
        try:
            release = infer_hamburg_lod1_dataset_release(path)
        except ValueError:
            continue
        if release == dataset_release:
            candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"No Hamburg LoD1 dataset directory found for release {dataset_release} in {root_dir}."
        )
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise ValueError(
            "Multiple Hamburg LoD1 dataset directories found for "
            f"release {dataset_release}: {joined}"
        )
    return candidates[0]


def project_hamburg_building_point_to_wgs84(
    easting_m: float, northing_m: float
) -> tuple[float, float]:
    lon, lat = LOD1_TO_WGS84.transform(easting_m, northing_m)
    return lat, lon


def _parse_optional_float(value: str | None) -> float | None:
    normalized = _normalize_optional_str(value)
    if normalized is None:
        return None
    return float(normalized)


def _parse_optional_int(value: str | None) -> int | None:
    normalized = _normalize_optional_str(value)
    if normalized is None:
        return None
    return int(normalized)


def _parse_pos_list(pos_list_text: str) -> list[tuple[float, float, float]]:
    values = [float(value) for value in pos_list_text.split()]
    if len(values) % 3 != 0:
        raise ValueError("Expected CityGML posList coordinates to be 3-dimensional.")
    return [
        (values[index], values[index + 1], values[index + 2])
        for index in range(0, len(values), 3)
    ]


def _geometry_from_xyz_coords(
    coords: list[tuple[float, float, float]],
) -> BaseGeometry | None:
    xy_coords = [(x, y) for x, y, _z in coords]
    if len(set(xy_coords)) < 3:
        return None
    if xy_coords[0] != xy_coords[-1]:
        xy_coords.append(xy_coords[0])

    geometry: BaseGeometry = Polygon(xy_coords)
    if geometry.is_empty or geometry.area <= 0:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        return None
    return geometry


def _coerce_multipolygon(geometry: BaseGeometry | None) -> MultiPolygon | None:
    if geometry is None or geometry.is_empty:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    polygons = [
        candidate
        for candidate in getattr(geometry, "geoms", [])
        if isinstance(candidate, Polygon) and not candidate.is_empty
    ]
    if not polygons:
        return None
    return MultiPolygon(polygons)


def _extract_terrain_footprint_and_ground_elevation(
    building: ET.Element,
) -> tuple[MultiPolygon | None, float | None]:
    polygons: list[BaseGeometry] = []
    z_values: list[float] = []
    for pos_list in building.findall(
        ".//bldg:lod1TerrainIntersection//gml:posList",
        NAMESPACES,
    ):
        pos_list_text = _normalize_optional_str(pos_list.text)
        if pos_list_text is None:
            continue
        coords = _parse_pos_list(pos_list_text)
        z_values.extend(z for _x, _y, z in coords)
        geometry = _geometry_from_xyz_coords(coords)
        if geometry is not None:
            polygons.append(geometry)

    footprint = _coerce_multipolygon(unary_union(polygons)) if polygons else None
    ground_elevation = min(z_values) if z_values else None
    return footprint, ground_elevation


def _extract_solid_footprint_ground_and_roof_elevations(
    building: ET.Element,
) -> tuple[MultiPolygon | None, float | None, float | None]:
    horizontal_surfaces: list[tuple[float, BaseGeometry]] = []
    z_values: list[float] = []

    for polygon in building.findall(".//bldg:lod1Solid//gml:Polygon", NAMESPACES):
        pos_list_text = _normalize_optional_str(
            polygon.findtext(
                ".//gml:exterior//gml:LinearRing//gml:posList",
                namespaces=NAMESPACES,
            )
        )
        if pos_list_text is None:
            continue

        coords = _parse_pos_list(pos_list_text)
        polygon_z_values = [z for _x, _y, z in coords]
        z_values.extend(polygon_z_values)
        geometry = _geometry_from_xyz_coords(coords)
        if geometry is None:
            continue
        if max(polygon_z_values) - min(polygon_z_values) <= 0.01:
            average_z = sum(polygon_z_values) / len(polygon_z_values)
            horizontal_surfaces.append((average_z, geometry))

    base_footprint = None
    ground_elevation = None
    if horizontal_surfaces:
        ground_elevation = min(level for level, _geometry in horizontal_surfaces)
        base_surfaces = [
            geometry
            for level, geometry in horizontal_surfaces
            if abs(level - ground_elevation) <= 0.01
        ]
        base_footprint = _coerce_multipolygon(unary_union(base_surfaces))

    roof_elevation = max(z_values) if z_values else None
    return base_footprint, ground_elevation, roof_elevation


def _extract_string_attributes(building: ET.Element) -> dict[str, str | None]:
    attributes: dict[str, str | None] = {}
    for attribute in building.findall("gen:stringAttribute", NAMESPACES):
        name = _normalize_optional_str(attribute.attrib.get("name"))
        if name is None:
            continue
        attributes[name] = _normalize_optional_str(
            attribute.findtext("gen:value", namespaces=NAMESPACES)
        )
    return attributes


def _extract_address_fields(building: ET.Element) -> dict[str, str | None]:
    return {
        "country_name": _normalize_optional_str(
            building.findtext(".//xAL:CountryName", namespaces=NAMESPACES)
        ),
        "locality_name": _normalize_optional_str(
            building.findtext(".//xAL:LocalityName", namespaces=NAMESPACES)
        ),
        "street_name": _normalize_optional_str(
            building.findtext(".//xAL:ThoroughfareName", namespaces=NAMESPACES)
        ),
        "street_number": _normalize_optional_str(
            building.findtext(".//xAL:ThoroughfareNumber", namespaces=NAMESPACES)
        ),
        "postal_code": _normalize_optional_str(
            building.findtext(".//xAL:PostalCodeNumber", namespaces=NAMESPACES)
        ),
    }


def load_hamburg_lod1_file_records(
    file_path: Path,
    *,
    dataset_release: str | None = None,
) -> list[dict[str, object]]:
    file_path = Path(file_path)
    if dataset_release is None:
        dataset_release = infer_hamburg_lod1_dataset_release(file_path.parent)

    root = ET.parse(file_path).getroot()
    envelope = root.find(".//gml:Envelope", NAMESPACES)
    source_srs_name = None
    if envelope is not None:
        source_srs_name = _normalize_optional_str(envelope.attrib.get("srsName"))

    tile_id = _normalize_optional_str(root.findtext("gml:name", namespaces=NAMESPACES))
    if tile_id is None:
        tile_id = file_path.stem

    records: list[dict[str, object]] = []
    for building in root.findall(".//bldg:Building", NAMESPACES):
        gml_id = _normalize_optional_str(building.attrib.get(GML_ID_ATTRIBUTE))
        if gml_id is None:
            raise ValueError(f"Building in {file_path} is missing a gml:id")

        terrain_footprint, terrain_ground_elevation = (
            _extract_terrain_footprint_and_ground_elevation(building)
        )
        (
            solid_footprint,
            solid_ground_elevation,
            roof_elevation,
        ) = _extract_solid_footprint_ground_and_roof_elevations(building)

        footprint = (
            terrain_footprint if terrain_footprint is not None else solid_footprint
        )
        if footprint is None:
            raise ValueError(
                f"Could not derive a footprint geometry for building {gml_id} in {file_path}"
            )

        representative_point = footprint.representative_point()
        representative_lat, representative_lon = (
            project_hamburg_building_point_to_wgs84(
                representative_point.x,
                representative_point.y,
            )
        )
        measured_height_m = _parse_optional_float(
            building.findtext("bldg:measuredHeight", namespaces=NAMESPACES)
        )
        ground_elevation_m = (
            terrain_ground_elevation
            if terrain_ground_elevation is not None
            else solid_ground_elevation
        )
        if roof_elevation is None and (
            ground_elevation_m is not None and measured_height_m is not None
        ):
            roof_elevation = ground_elevation_m + measured_height_m

        raw_attributes = _extract_string_attributes(building)
        address_fields = _extract_address_fields(building)
        records.append(
            {
                "dataset_release": dataset_release,
                "tile_id": tile_id,
                "gml_id": gml_id,
                "building_name": _normalize_optional_str(
                    building.findtext("gml:name", namespaces=NAMESPACES)
                ),
                "function_code": _normalize_optional_str(
                    building.findtext("bldg:function", namespaces=NAMESPACES)
                ),
                "municipality_code": raw_attributes.get("Gemeindeschluessel"),
                "street_name": address_fields["street_name"],
                "street_number": address_fields["street_number"],
                "postal_code": address_fields["postal_code"],
                "locality_name": address_fields["locality_name"],
                "country_name": address_fields["country_name"],
                "measured_height_m": measured_height_m,
                "storeys_above_ground": _parse_optional_int(
                    building.findtext(
                        "bldg:storeysAboveGround",
                        namespaces=NAMESPACES,
                    )
                ),
                "ground_elevation_m": ground_elevation_m,
                "roof_elevation_m": roof_elevation,
                "representative_lat": representative_lat,
                "representative_lon": representative_lon,
                "raw_attributes": raw_attributes or None,
                "source_srs_name": source_srs_name or EXPECTED_SOURCE_SRS_NAME,
                "source_path": str(file_path),
                "footprint_geom": footprint.wkt,
            }
        )

    return records


def _iter_chunks(
    records: list[dict[str, object]],
    chunk_size: int,
) -> Iterable[list[dict[str, object]]]:
    for start in range(0, len(records), chunk_size):
        yield records[start : start + chunk_size]


def _ensure_postgis_and_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS built_environment"))


def ingest_hamburg_lod1_directory(
    dataset_dir: Path,
    *,
    database_url: str,
    dataset_release: str = DEFAULT_HAMBURG_LOD1_DATASET_RELEASE,
    chunk_size: int = 1_000,
    replace_existing: bool = False,
    dry_run: bool = False,
    progress: bool = False,
    progress_every: int = 25,
) -> int:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    dataset_dir = Path(dataset_dir)
    xml_files = sorted(dataset_dir.glob("*.xml"))
    if not xml_files:
        raise FileNotFoundError(f"No Hamburg LoD1 XML files found in {dataset_dir}.")

    total_rows = 0
    if dry_run:
        for file_index, file_path in enumerate(xml_files, start=1):
            total_rows += len(
                load_hamburg_lod1_file_records(
                    file_path,
                    dataset_release=dataset_release,
                )
            )
            if progress and (
                file_index == 1
                or file_index % progress_every == 0
                or file_index == len(xml_files)
            ):
                print(
                    f"[hh-buildings:{dataset_release}] dry run scanned "
                    f"{file_index} / {len(xml_files)} files ({total_rows} rows)"
                )
        return total_rows

    engine = create_engine(database_url)
    _ensure_postgis_and_schema(engine)
    HamburgLod1Building.__table__.create(engine, checkfirst=True)

    pending_records: list[dict[str, object]] = []
    with engine.begin() as connection:
        if replace_existing:
            connection.execute(
                delete(HamburgLod1Building).where(
                    HamburgLod1Building.dataset_release == dataset_release
                )
            )

        for file_index, file_path in enumerate(xml_files, start=1):
            file_records = load_hamburg_lod1_file_records(
                file_path,
                dataset_release=dataset_release,
            )
            total_rows += len(file_records)
            pending_records.extend(file_records)

            while len(pending_records) >= chunk_size:
                chunk = pending_records[:chunk_size]
                connection.execute(insert(HamburgLod1Building), chunk)
                del pending_records[:chunk_size]

            if progress and (
                file_index == 1
                or file_index % progress_every == 0
                or file_index == len(xml_files)
            ):
                print(
                    f"[hh-buildings:{dataset_release}] parsed "
                    f"{file_index} / {len(xml_files)} files ({total_rows} rows)"
                )

        for chunk in _iter_chunks(pending_records, chunk_size):
            connection.execute(insert(HamburgLod1Building), chunk)

    if progress:
        print(f"[hh-buildings:{dataset_release}] complete ({total_rows} rows)")
    return total_rows
