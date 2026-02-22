from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Column,
    Date,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)

from .calendar import parse_gtfs_date
from .shapes import coerce_shape_columns
from .validate import GTFS_OPTIONAL_FILES, GTFS_REQUIRED_FILES, find_gtfs_files


GTFS_TYPE_MAP: dict[str, dict[str, object]] = {
    "agency.txt": {
        "agency_id": String,
        "agency_name": Text,
        "agency_url": Text,
        "agency_timezone": String,
        "agency_lang": String,
        "agency_phone": String,
        "agency_fare_url": Text,
        "agency_email": String,
    },
    "calendar.txt": {
        "service_id": String,
        "monday": Integer,
        "tuesday": Integer,
        "wednesday": Integer,
        "thursday": Integer,
        "friday": Integer,
        "saturday": Integer,
        "sunday": Integer,
        "start_date": Date,
        "end_date": Date,
    },
    "calendar_dates.txt": {
        "service_id": String,
        "date": Date,
        "exception_type": Integer,
    },
    "feed_info.txt": {
        "feed_publisher_name": Text,
        "feed_publisher_url": Text,
        "feed_lang": String,
        "feed_start_date": Date,
        "feed_end_date": Date,
        "feed_version": String,
        "feed_contact_email": String,
        "feed_contact_url": Text,
    },
    "frequencies.txt": {
        "trip_id": String,
        "start_time": String,
        "end_time": String,
        "headway_secs": Integer,
        "exact_times": Integer,
    },
    "routes.txt": {
        "route_id": String,
        "agency_id": String,
        "route_short_name": String,
        "route_long_name": Text,
        "route_desc": Text,
        "route_type": Integer,
        "route_url": Text,
        "route_color": String,
        "route_text_color": String,
        "route_sort_order": Integer,
        "continuous_pickup": Integer,
        "continuous_drop_off": Integer,
    },
    "shapes.txt": {
        "shape_id": String,
        "shape_pt_lat": Float,
        "shape_pt_lon": Float,
        "shape_pt_sequence": Integer,
        "shape_dist_traveled": Float,
    },
    "stops.txt": {
        "stop_id": String,
        "stop_code": String,
        "stop_name": Text,
        "stop_desc": Text,
        "stop_lat": Float,
        "stop_lon": Float,
        "zone_id": String,
        "stop_url": Text,
        "location_type": Integer,
        "parent_station": String,
        "stop_timezone": String,
        "wheelchair_boarding": Integer,
        "level_id": String,
        "platform_code": String,
    },
    "stop_times.txt": {
        "trip_id": String,
        "arrival_time": String,
        "departure_time": String,
        "stop_id": String,
        "stop_sequence": Integer,
        "stop_headsign": Text,
        "pickup_type": Integer,
        "drop_off_type": Integer,
        "continuous_pickup": Integer,
        "continuous_drop_off": Integer,
        "shape_dist_traveled": Float,
        "timepoint": Integer,
    },
    "transfers.txt": {
        "from_stop_id": String,
        "to_stop_id": String,
        "transfer_type": Integer,
        "min_transfer_time": Integer,
    },
    "trips.txt": {
        "route_id": String,
        "service_id": String,
        "trip_id": String,
        "trip_headsign": Text,
        "trip_short_name": String,
        "direction_id": Integer,
        "block_id": String,
        "shape_id": String,
        "wheelchair_accessible": Integer,
        "bikes_allowed": Integer,
    },
}


INT_COLUMNS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "exception_type",
    "headway_secs",
    "exact_times",
    "route_type",
    "route_sort_order",
    "continuous_pickup",
    "continuous_drop_off",
    "location_type",
    "wheelchair_boarding",
    "stop_sequence",
    "pickup_type",
    "drop_off_type",
    "timepoint",
    "direction_id",
    "wheelchair_accessible",
    "bikes_allowed",
    "transfer_type",
    "min_transfer_time",
}


FLOAT_COLUMNS = {
    "shape_pt_lat",
    "shape_pt_lon",
    "shape_dist_traveled",
    "stop_lat",
    "stop_lon",
}


DATE_COLUMNS = {
    "start_date",
    "end_date",
    "date",
    "feed_start_date",
    "feed_end_date",
}


def create_schema(engine, schema: str) -> None:
    if not schema:
        return
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def _read_header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def _make_table(
    metadata: MetaData,
    schema: str,
    table_name: str,
    columns: list[str],
    type_map: dict[str, object],
) -> Table:
    sql_columns = [Column("feed_id", String, nullable=True)]
    for name in columns:
        col_type = type_map.get(name, Text)
        sql_columns.append(Column(name, col_type, nullable=True))
    return Table(table_name, metadata, *sql_columns, schema=schema)


def _coerce_types(frame: pd.DataFrame) -> pd.DataFrame:
    for name in frame.columns:
        if name in DATE_COLUMNS:
            frame[name] = parse_gtfs_date(frame[name])
        elif name in FLOAT_COLUMNS:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        elif name in INT_COLUMNS:
            frame[name] = pd.to_numeric(frame[name], errors="coerce").astype("Int64")
    return frame


def _ingest_file(
    engine,
    schema: str,
    table_name: str,
    path: Path,
    feed_id: str,
    chunksize: int,
    type_map: dict[str, object],
    progress: bool = False,
    progress_every: int = 10,
    drop_existing: bool = False,
) -> None:
    header = _read_header(path)
    metadata = MetaData()
    table = _make_table(metadata, schema, table_name, header, type_map)
    if drop_existing:
        table.drop(engine, checkfirst=True)
    table.create(engine, checkfirst=True)

    # Postgres has a 65535 parameter limit per statement.
    # Ensure chunks stay under that limit.
    columns_per_row = len(header) + 1  # +1 for feed_id
    if columns_per_row > 0:
        max_rows = max(1, 65000 // columns_per_row)
        if chunksize > max_rows:
            if progress:
                print(
                    f"[{feed_id}] {table_name}: reducing chunksize to {max_rows} "
                    f"(param limit)"
                )
            chunksize = max_rows

    total_rows = 0
    chunk_index = 0
    for chunk in pd.read_csv(path, dtype=str, chunksize=chunksize):
        chunk_index += 1
        chunk = _coerce_types(chunk)
        if table_name == "shapes":
            chunk = coerce_shape_columns(chunk)
        chunk["feed_id"] = feed_id
        total_rows += len(chunk)
        chunk.to_sql(
            table_name,
            engine,
            schema=schema,
            if_exists="append",
            index=False,
            method="multi",
        )
        if progress and (chunk_index == 1 or chunk_index % progress_every == 0):
            print(
                f"[{feed_id}] {table_name}: loaded {total_rows} rows "
                f"(chunk {chunk_index})"
            )
    if progress:
        print(f"[{feed_id}] {table_name}: complete ({total_rows} rows)")


def ingest_gtfs_folder(
    folder: Path,
    database_url: str,
    schema: str = "gtfs",
    feed_id: str | None = None,
    chunksize: int = 100_000,
    dry_run: bool = False,
    progress: bool = False,
    progress_every: int = 10,
    skip_tables: set[str] | None = None,
    drop_existing: bool = False,
) -> None:
    folder = Path(folder)
    feed_id = feed_id or folder.name
    files = find_gtfs_files(folder)

    missing = {name for name in GTFS_REQUIRED_FILES if name not in files}
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise FileNotFoundError(f"Missing GTFS files: {missing_list}")

    skip_tables = skip_tables or set()
    if dry_run:
        available = [
            filename.replace(".txt", "")
            for filename in sorted(GTFS_REQUIRED_FILES | GTFS_OPTIONAL_FILES)
            if filename in files and filename.replace(".txt", "") not in skip_tables
        ]
        print(
            "Dry run: would create schema "
            f"'{schema}' and load tables: {', '.join(available)} "
            f"(feed_id={feed_id})"
        )
        return

    engine = create_engine(database_url)
    create_schema(engine, schema)

    for filename in sorted(GTFS_REQUIRED_FILES | GTFS_OPTIONAL_FILES):
        path = files.get(filename)
        if not path:
            continue
        table_name = filename.replace(".txt", "")
        if table_name in skip_tables:
            if progress:
                print(f"[{feed_id}] {table_name}: skipped")
            continue
        type_map = GTFS_TYPE_MAP.get(filename, {})
        _ingest_file(
            engine=engine,
            schema=schema,
            table_name=table_name,
            path=path,
            feed_id=feed_id,
            chunksize=chunksize,
            type_map=type_map,
            progress=progress,
            progress_every=progress_every,
            drop_existing=drop_existing,
        )


def ingest_all_gtfs(
    root_dir: Path,
    database_url: str,
    schema: str = "gtfs",
    chunksize: int = 100_000,
    dry_run: bool = False,
    progress: bool = False,
    progress_every: int = 10,
    skip_tables: set[str] | None = None,
    drop_existing: bool = False,
) -> None:
    root_dir = Path(root_dir)
    for folder in sorted(p for p in root_dir.iterdir() if p.is_dir()):
        ingest_gtfs_folder(
            folder=folder,
            database_url=database_url,
            schema=schema,
            feed_id=folder.name,
            chunksize=chunksize,
            dry_run=dry_run,
            progress=progress,
            progress_every=progress_every,
            skip_tables=skip_tables,
            drop_existing=drop_existing,
        )
