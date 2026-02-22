from __future__ import annotations

from sqlalchemy import Date, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    __table_args__ = (
        UniqueConstraint("feed_id", "agency_id", name="uq_agency_feed_agency_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agency_id: Mapped[int] = mapped_column(Integer, nullable=False)
    agency_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency_timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    agency_lang: Mapped[str | None] = mapped_column(String, nullable=True)
    agency_phone: Mapped[str | None] = mapped_column(String, nullable=True)


class Calendar(Base):
    __tablename__ = "calendar"
    __table_args__ = (
        UniqueConstraint("feed_id", "service_id", name="uq_calendar_feed_service_id"),
        {"schema": "gtfs"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(Integer, nullable=False)
    monday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tuesday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wednesday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thursday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    friday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saturday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sunday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[object | None] = mapped_column(Date, nullable=True)


class CalendarDate(Base):
    __tablename__ = "calendar_dates"
    __table_args__ = (
        UniqueConstraint(
            "feed_id", "service_id", "date", name="uq_calendar_date_feed_service_date"
        ),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    service_id: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[object | None] = mapped_column(Date, nullable=True)
    exception_type: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeedInfo(Base):
    __tablename__ = "feed_info"
    __table_args__ = (
        UniqueConstraint("feed_id", name="uq_feed_info_feed_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    feed_publisher_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    feed_publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    feed_lang: Mapped[str | None] = mapped_column(String, nullable=True)
    feed_start_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    feed_end_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    feed_version: Mapped[str | None] = mapped_column(String, nullable=True)
    feed_contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    feed_contact_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Frequency(Base):
    __tablename__ = "frequencies"
    __table_args__ = {"schema": "gtfs"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    end_time: Mapped[str | None] = mapped_column(String, nullable=True)
    headway_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exact_times: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("feed_id", "route_id", name="uq_route_feed_route_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    route_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agency_id: Mapped[str | None] = mapped_column(String, nullable=True)
    route_short_name: Mapped[str | None] = mapped_column(String, nullable=True)
    route_long_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    route_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_color: Mapped[str | None] = mapped_column(String, nullable=True)
    route_text_color: Mapped[str | None] = mapped_column(String, nullable=True)
    route_sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuous_pickup: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuous_drop_off: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Shape(Base):
    __tablename__ = "shapes"
    __table_args__ = (
        UniqueConstraint(
            "feed_id",
            "shape_id",
            "shape_pt_sequence",
            name="uq_shape_feed_shape_sequence",
        ),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    shape_id: Mapped[str | None] = mapped_column(String, nullable=True)
    shape_pt_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    shape_pt_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    shape_pt_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float, nullable=True)


class Stop(Base):
    __tablename__ = "stops"
    __table_args__ = (
        UniqueConstraint("feed_id", "stop_id", name="uq_stop_feed_stop_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    stop_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_code: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    zone_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_station: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    wheelchair_boarding: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level_id: Mapped[str | None] = mapped_column(String, nullable=True)
    platform_code: Mapped[str | None] = mapped_column(String, nullable=True)


class StopTime(Base):
    __tablename__ = "stop_times"
    __table_args__ = (
        UniqueConstraint(
            "feed_id",
            "trip_id",
            "stop_id",
            "stop_sequence",
            name="uq_stop_time_feed_trip_stop_sequence",
        ),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True)
    arrival_time: Mapped[str | None] = mapped_column(String, nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_headsign: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drop_off_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuous_pickup: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuous_drop_off: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float, nullable=True)
    timepoint: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint(
            "feed_id",
            "from_stop_id",
            "to_stop_id",
            "from_route_id",
            "to_route_id",
            name="uq_transfer_feed_from_to_stop",
        ),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    from_stop_id: Mapped[str | None] = mapped_column(String, nullable=True)
    to_stop_id: Mapped[str | None] = mapped_column(String, nullable=True)
    transfer_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_transfer_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_route_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_route_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_trip_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_trip_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("feed_id", "trip_id", name="uq_trip_feed_trip_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    route_id: Mapped[str | None] = mapped_column(String, nullable=True)
    service_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trip_headsign: Mapped[str | None] = mapped_column(Text, nullable=True)
    trip_short_name: Mapped[str | None] = mapped_column(String, nullable=True)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_id: Mapped[str | None] = mapped_column(String, nullable=True)
    shape_id: Mapped[str | None] = mapped_column(String, nullable=True)
    wheelchair_accessible: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bikes_allowed: Mapped[int | None] = mapped_column(Integer, nullable=True)
