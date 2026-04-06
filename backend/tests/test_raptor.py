from __future__ import annotations

from core.routing.raptor import (
    RaptorFootpath,
    RaptorQuery,
    RaptorRoute,
    RaptorSourceCandidate,
    RaptorTargetCandidate,
    RaptorTimetable,
    RaptorTrip,
    run_raptor,
)


def _sec(hours: int, minutes: int, seconds: int = 0) -> int:
    return hours * 3600 + minutes * 60 + seconds


def _make_route(
    *,
    route_key: str,
    public_route_id: str,
    stop_ids: tuple[str, ...],
    trips: list[tuple[str, tuple[int, ...], tuple[int, ...]]],
) -> RaptorRoute:
    route_trips = tuple(
        RaptorTrip(
            trip_id=trip_id,
            route_id=public_route_id,
            service_id="service-1",
            arrivals=arrivals,
            departures=departures,
        )
        for trip_id, arrivals, departures in trips
    )
    departures_by_stop: list[tuple[int, ...]] = []
    trip_indices_by_stop: list[tuple[int, ...]] = []
    for stop_index in range(len(stop_ids)):
        ordered_departures = sorted(
            (trip.departures[stop_index], trip_index)
            for trip_index, trip in enumerate(route_trips)
        )
        departures_by_stop.append(
            tuple(departure for departure, _trip_index in ordered_departures)
        )
        trip_indices_by_stop.append(
            tuple(trip_index for _departure, trip_index in ordered_departures)
        )
    return RaptorRoute(
        route_key=route_key,
        public_route_id=public_route_id,
        stop_ids=stop_ids,
        trips=route_trips,
        departures_by_stop=tuple(departures_by_stop),
        trip_indices_by_stop=tuple(trip_indices_by_stop),
    )


def _make_timetable(
    *,
    routes: list[RaptorRoute],
    footpaths_from: dict[str, tuple[RaptorFootpath, ...]] | None = None,
    extra_stops: tuple[str, ...] = (),
) -> RaptorTimetable:
    stop_to_routes: dict[str, set[str]] = {}
    route_stop_indices: dict[tuple[str, str], list[int]] = {}
    all_stops = set(extra_stops)
    for route in routes:
        for stop_index, stop_id in enumerate(route.stop_ids):
            all_stops.add(stop_id)
            stop_to_routes.setdefault(stop_id, set()).add(route.route_key)
            route_stop_indices.setdefault((route.route_key, stop_id), []).append(
                stop_index
            )

    for from_stop_id, footpaths in (footpaths_from or {}).items():
        all_stops.add(from_stop_id)
        for footpath in footpaths:
            all_stops.add(footpath.to_stop_id)

    return RaptorTimetable(
        routes={route.route_key: route for route in routes},
        stop_to_routes={
            stop_id: tuple(sorted(route_keys))
            for stop_id, route_keys in stop_to_routes.items()
        },
        route_stop_indices={
            key: tuple(indices) for key, indices in route_stop_indices.items()
        },
        footpaths_from=footpaths_from or {},
        stops=tuple(sorted(all_stops)),
    )


def test_run_raptor_finds_direct_trip() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "B", "C"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 0), _sec(9, 10), _sec(9, 20)),
                        (_sec(9, 0), _sec(9, 10), _sec(9, 20)),
                    )
                ],
            )
        ]
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="C", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=1,
        ),
    )

    assert result.path_result.arrival_time_sec == _sec(9, 20)
    assert result.path_result.stop_path == ["A", "C"]
    assert len(result.path_result.edge_path) == 1
    edge = result.path_result.edge_path[0]
    assert edge.kind == "trip"
    assert edge.trip_id == "trip-1"
    assert edge.route_id == "R1"
    assert edge.dep_time_sec == _sec(9, 0)
    assert edge.arr_time_sec == _sec(9, 20)


def test_run_raptor_supports_one_transfer() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "B"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 0), _sec(9, 5)),
                        (_sec(9, 0), _sec(9, 5)),
                    )
                ],
            ),
            _make_route(
                route_key="route-2",
                public_route_id="R2",
                stop_ids=("B", "D"),
                trips=[
                    (
                        "trip-2",
                        (_sec(9, 6), _sec(9, 12)),
                        (_sec(9, 6), _sec(9, 12)),
                    )
                ],
            ),
        ]
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="D", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=2,
        ),
    )

    assert result.path_result.arrival_time_sec == _sec(9, 12)
    assert result.path_result.stop_path == ["A", "B", "D"]
    assert [edge.trip_id for edge in result.path_result.edge_path] == [
        "trip-1",
        "trip-2",
    ]


def test_run_raptor_chooses_best_source_candidate() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("S1", "T"),
                trips=[
                    (
                        "trip-s1",
                        (_sec(9, 5), _sec(9, 20)),
                        (_sec(9, 5), _sec(9, 20)),
                    )
                ],
            ),
            _make_route(
                route_key="route-2",
                public_route_id="R2",
                stop_ids=("S2", "T"),
                trips=[
                    (
                        "trip-s2",
                        (_sec(9, 3), _sec(9, 8)),
                        (_sec(9, 3), _sec(9, 8)),
                    )
                ],
            ),
        ]
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(
                RaptorSourceCandidate(stop_id="S1", access_time_sec=0),
                RaptorSourceCandidate(stop_id="S2", access_time_sec=120),
            ),
            target_candidates=(RaptorTargetCandidate(stop_id="T", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=1,
        ),
    )

    assert result.path_result.arrival_time_sec == _sec(9, 8)
    assert result.path_result.stop_path == ["S2", "T"]


def test_run_raptor_chooses_best_target_candidate_with_egress() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "T1"),
                trips=[
                    (
                        "trip-t1",
                        (_sec(9, 0), _sec(9, 10)),
                        (_sec(9, 0), _sec(9, 10)),
                    )
                ],
            ),
            _make_route(
                route_key="route-2",
                public_route_id="R2",
                stop_ids=("A", "T2"),
                trips=[
                    (
                        "trip-t2",
                        (_sec(9, 0), _sec(9, 12)),
                        (_sec(9, 0), _sec(9, 12)),
                    )
                ],
            ),
        ]
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(
                RaptorTargetCandidate(stop_id="T1", egress_time_sec=300),
                RaptorTargetCandidate(stop_id="T2", egress_time_sec=0),
            ),
            departure_time_sec=_sec(9, 0),
            max_rounds=1,
        ),
    )

    assert result.best_target_stop_id == "T2"
    assert result.path_result.arrival_time_sec == _sec(9, 12)
    assert result.path_result.stop_path == ["A", "T2"]


def test_run_raptor_relaxes_transfer_footpaths() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "B"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 0), _sec(9, 5)),
                        (_sec(9, 0), _sec(9, 5)),
                    )
                ],
            ),
            _make_route(
                route_key="route-2",
                public_route_id="R2",
                stop_ids=("C", "D"),
                trips=[
                    (
                        "trip-2",
                        (_sec(9, 7), _sec(9, 10)),
                        (_sec(9, 7), _sec(9, 10)),
                    )
                ],
            ),
        ],
        footpaths_from={
            "B": (
                RaptorFootpath(
                    to_stop_id="C",
                    duration_sec=60,
                    transfer_type=None,
                    label="walk",
                ),
            )
        },
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="D", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=2,
        ),
    )

    assert result.path_result.arrival_time_sec == _sec(9, 10)
    assert result.path_result.stop_path == ["A", "B", "C", "D"]
    assert [edge.kind for edge in result.path_result.edge_path] == [
        "trip",
        "transfer",
        "trip",
    ]
    assert result.path_result.edge_path[1].label == "walk"


def test_run_raptor_allows_initial_footpath_before_first_trip() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("B", "C"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 2), _sec(9, 10)),
                        (_sec(9, 2), _sec(9, 10)),
                    )
                ],
            )
        ],
        footpaths_from={
            "A": (
                RaptorFootpath(
                    to_stop_id="B",
                    duration_sec=60,
                    transfer_type=None,
                    label="walk",
                ),
            )
        },
        extra_stops=("A",),
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="C", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=1,
        ),
    )

    assert result.path_result.arrival_time_sec == _sec(9, 10)
    assert result.path_result.stop_path == ["A", "B", "C"]
    assert [edge.kind for edge in result.path_result.edge_path] == ["transfer", "trip"]


def test_run_raptor_returns_pareto_options_across_major_transfers() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-direct",
                public_route_id="R0",
                stop_ids=("A", "T"),
                trips=[
                    (
                        "trip-direct",
                        (_sec(9, 0), _sec(10, 0)),
                        (_sec(9, 0), _sec(10, 0)),
                    )
                ],
            ),
            _make_route(
                route_key="route-ab",
                public_route_id="R1",
                stop_ids=("A", "B"),
                trips=[
                    (
                        "trip-ab",
                        (_sec(9, 0), _sec(9, 10)),
                        (_sec(9, 0), _sec(9, 10)),
                    )
                ],
            ),
            _make_route(
                route_key="route-bt",
                public_route_id="R2",
                stop_ids=("B", "T"),
                trips=[
                    (
                        "trip-bt",
                        (_sec(9, 15), _sec(9, 45)),
                        (_sec(9, 15), _sec(9, 45)),
                    )
                ],
            ),
            _make_route(
                route_key="route-bc",
                public_route_id="R3",
                stop_ids=("B", "C"),
                trips=[
                    (
                        "trip-bc",
                        (_sec(9, 12), _sec(9, 20)),
                        (_sec(9, 12), _sec(9, 20)),
                    )
                ],
            ),
            _make_route(
                route_key="route-ct",
                public_route_id="R4",
                stop_ids=("C", "T"),
                trips=[
                    (
                        "trip-ct",
                        (_sec(9, 21), _sec(9, 30)),
                        (_sec(9, 21), _sec(9, 30)),
                    )
                ],
            ),
        ]
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="T", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=3,
        ),
    )

    assert [option.final_arrival_time_sec for option in result.options] == [
        _sec(10, 0),
        _sec(9, 45),
        _sec(9, 30),
    ]
    assert [option.major_trip_transfers for option in result.options] == [0, 1, 2]
    assert [option.path_result.stop_path for option in result.options] == [
        ["A", "T"],
        ["A", "B", "T"],
        ["A", "B", "C", "T"],
    ]
    assert result.path_result.arrival_time_sec == _sec(9, 30)
    assert result.best_round == 3


def test_run_raptor_returns_no_path_when_unreachable() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "B"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 0), _sec(9, 5)),
                        (_sec(9, 0), _sec(9, 5)),
                    )
                ],
            )
        ],
        extra_stops=("Z",),
    )

    result = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="Z", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=2,
        ),
    )

    assert result.path_result.arrival_time_sec is None
    assert result.path_result.stop_path == []
    assert result.path_result.edge_path == []


def test_run_raptor_requires_later_round_for_transfer_path() -> None:
    timetable = _make_timetable(
        routes=[
            _make_route(
                route_key="route-1",
                public_route_id="R1",
                stop_ids=("A", "B"),
                trips=[
                    (
                        "trip-1",
                        (_sec(9, 0), _sec(9, 5)),
                        (_sec(9, 0), _sec(9, 5)),
                    )
                ],
            ),
            _make_route(
                route_key="route-2",
                public_route_id="R2",
                stop_ids=("B", "D"),
                trips=[
                    (
                        "trip-2",
                        (_sec(9, 6), _sec(9, 8)),
                        (_sec(9, 6), _sec(9, 8)),
                    )
                ],
            ),
        ]
    )

    blocked = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="D", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=1,
        ),
    )
    allowed = run_raptor(
        timetable,
        RaptorQuery(
            source_candidates=(RaptorSourceCandidate(stop_id="A", access_time_sec=0),),
            target_candidates=(RaptorTargetCandidate(stop_id="D", egress_time_sec=0),),
            departure_time_sec=_sec(9, 0),
            max_rounds=2,
        ),
    )

    assert blocked.path_result.arrival_time_sec is None
    assert allowed.path_result.arrival_time_sec == _sec(9, 8)
    assert allowed.best_round == 2
