from __future__ import annotations

from dataclasses import dataclass

from core.user_facing.itinerary import create_itinerary


@dataclass(frozen=True)
class _Edge:
    to_stop_id: str
    weight_sec: int | None
    kind: str
    route_id: str | None = None
    trip_id: str | None = None
    dep_time: str | None = None
    arr_time: str | None = None
    dep_time_sec: int | None = None
    arr_time_sec: int | None = None
    transfer_type: int | None = None
    apply_penalty: bool = True
    label: str | None = None


@dataclass(frozen=True)
class _Result:
    arrival_time_sec: int | None
    stop_path: list[str]
    edge_path: list[_Edge]


def test_itinerary_formats_walk_and_trip_legs() -> None:
    result = _Result(
        arrival_time_sec=9 * 3600 + 10 * 60,
        stop_path=["A", "B", "C"],
        edge_path=[
            _Edge(
                to_stop_id="B",
                weight_sec=120,
                kind="transfer",
                apply_penalty=False,
                label="walk",
            ),
            _Edge(
                to_stop_id="C",
                weight_sec=300,
                kind="trip",
                route_id="R1",
                trip_id="T1",
                dep_time="09:02:00",
                arr_time="09:07:00",
            ),
        ],
    )

    itinerary = create_itinerary(
        result=result,
        from_stop_name="Start",
        to_stop_name="End",
        depart_time_str="09:00:00",
        stop_names={"A": "Start", "B": "Mid", "C": "End"},
        stop_coords={
            "A": (53.551, 9.993),
            "B": (53.556, 10.002),
            "C": (53.562, 10.014),
        },
        route_short_names={"R1": "S1"},
        transfer_penalty_sec=300,
    )
    lines = itinerary.lines()

    assert any("Walk from Start to Mid" in line for line in lines)
    assert any("Ride S1 from Mid to End" in line for line in lines)
    assert [stop.stop_id for stop in itinerary.stops] == ["A", "B", "C"]
    assert [stop.stop_name for stop in itinerary.stops] == ["Start", "Mid", "End"]
    assert itinerary.stops[0].stop_lat == 53.551
    assert itinerary.stops[0].stop_lon == 9.993
    assert len(itinerary.path_segments) == 2
    assert itinerary.path_segments[0].from_stop.stop_id == "A"
    assert itinerary.path_segments[0].to_stop.stop_id == "B"
    assert itinerary.path_segments[0].edge.kind == "transfer"
    assert itinerary.path_segments[1].edge.kind == "trip"
    assert itinerary.path_segments[1].edge.route == "S1"
    assert itinerary.legs[0].mode == "walk"
    assert itinerary.legs[0].from_stop == "Start"
    assert itinerary.legs[0].to_stop == "Mid"
    assert itinerary.legs[0].duration_sec == 120
    assert itinerary.legs[1].mode == "ride"
    assert itinerary.legs[1].route == "S1"
    assert itinerary.legs[1].from_stop == "Mid"
    assert itinerary.legs[1].to_stop == "End"


def test_itinerary_hides_zero_duration_station_link_steps() -> None:
    result = _Result(
        arrival_time_sec=9 * 3600 + 7 * 60,
        stop_path=["A", "A_PARENT", "B"],
        edge_path=[
            _Edge(
                to_stop_id="A_PARENT",
                weight_sec=0,
                kind="transfer",
                transfer_type=2,
                apply_penalty=False,
                label="station_link",
            ),
            _Edge(
                to_stop_id="B",
                weight_sec=300,
                kind="trip",
                route_id="R1",
                trip_id="T1",
                dep_time="09:02:00",
                arr_time="09:07:00",
            ),
        ],
    )

    itinerary = create_itinerary(
        result=result,
        from_stop_name="Start",
        to_stop_name="End",
        depart_time_str="09:00:00",
        stop_names={"A": "Start", "A_PARENT": "Start Station", "B": "End"},
        stop_coords={
            "A": (53.551, 9.993),
            "A_PARENT": (53.551, 9.993),
            "B": (53.562, 10.014),
        },
        route_short_names={"R1": "S1"},
        transfer_penalty_sec=0,
    )

    assert [segment.edge.label for segment in itinerary.path_segments] == [None]
    assert [leg.mode for leg in itinerary.legs] == ["ride"]
    assert all("Station Link" not in line for line in itinerary.leg_lines)


def test_itinerary_merges_consecutive_transfer_steps_into_one_walk_leg() -> None:
    result = _Result(
        arrival_time_sec=9 * 3600 + 11 * 60,
        stop_path=["ORIGIN", "A", "B", "C"],
        edge_path=[
            _Edge(
                to_stop_id="A",
                weight_sec=120,
                kind="transfer",
                apply_penalty=False,
                label="walk",
            ),
            _Edge(
                to_stop_id="B",
                weight_sec=60,
                kind="transfer",
                transfer_type=2,
                apply_penalty=False,
                label="station_link",
            ),
            _Edge(
                to_stop_id="C",
                weight_sec=420,
                kind="trip",
                route_id="R1",
                trip_id="T1",
                dep_time="09:03:00",
                arr_time="09:10:00",
            ),
        ],
    )

    itinerary = create_itinerary(
        result=result,
        from_stop_name="Origin",
        to_stop_name="Destination",
        depart_time_str="09:00:00",
        stop_names={
            "ORIGIN": "Origin",
            "A": "Street Corner",
            "B": "Station Concourse",
            "C": "Destination",
        },
        stop_coords={
            "ORIGIN": (53.551, 9.993),
            "A": (53.552, 9.995),
            "B": (53.553, 9.997),
            "C": (53.562, 10.014),
        },
        route_short_names={"R1": "S1"},
        transfer_penalty_sec=0,
    )

    assert len(itinerary.path_segments) == 2
    assert itinerary.path_segments[0].from_stop.stop_id == "ORIGIN"
    assert itinerary.path_segments[0].to_stop.stop_id == "B"
    assert itinerary.path_segments[0].edge.kind == "transfer"
    assert itinerary.path_segments[0].edge.label == "walk"
    assert itinerary.path_segments[0].edge.weight_sec == 180
    assert [leg.mode for leg in itinerary.legs] == ["walk", "ride"]
    assert itinerary.legs[0].from_stop == "Origin"
    assert itinerary.legs[0].to_stop == "Station Concourse"
    assert itinerary.legs[0].duration_sec == 180


def test_itinerary_extends_walk_leg_across_hidden_station_link() -> None:
    result = _Result(
        arrival_time_sec=9 * 3600 + 7 * 60,
        stop_path=["ORIGIN", "A", "A_PARENT", "B"],
        edge_path=[
            _Edge(
                to_stop_id="A",
                weight_sec=120,
                kind="transfer",
                apply_penalty=False,
                label="walk",
            ),
            _Edge(
                to_stop_id="A_PARENT",
                weight_sec=0,
                kind="transfer",
                transfer_type=2,
                apply_penalty=False,
                label="station_link",
            ),
            _Edge(
                to_stop_id="B",
                weight_sec=300,
                kind="trip",
                route_id="R1",
                trip_id="T1",
                dep_time="09:02:00",
                arr_time="09:07:00",
            ),
        ],
    )

    itinerary = create_itinerary(
        result=result,
        from_stop_name="Origin",
        to_stop_name="End",
        depart_time_str="09:00:00",
        stop_names={
            "ORIGIN": "Origin",
            "A": "Street",
            "A_PARENT": "Station",
            "B": "End",
        },
        stop_coords={
            "ORIGIN": (53.551, 9.993),
            "A": (53.5515, 9.994),
            "A_PARENT": (53.552, 9.995),
            "B": (53.562, 10.014),
        },
        route_short_names={"R1": "S1"},
        transfer_penalty_sec=0,
    )

    assert len(itinerary.path_segments) == 2
    assert itinerary.path_segments[0].from_stop.stop_id == "ORIGIN"
    assert itinerary.path_segments[0].to_stop.stop_id == "A_PARENT"
    assert itinerary.path_segments[0].edge.label == "walk"
    assert itinerary.path_segments[0].edge.weight_sec == 120
    assert [leg.mode for leg in itinerary.legs] == ["walk", "ride"]
    assert itinerary.legs[0].to_stop == "Station"
