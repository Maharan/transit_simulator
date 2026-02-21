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
        route_short_names={"R1": "S1"},
        transfer_penalty_sec=300,
    )
    lines = itinerary.lines()

    assert any("Walk from Start to Mid" in line for line in lines)
    assert any("Ride S1 from Mid to End" in line for line in lines)
