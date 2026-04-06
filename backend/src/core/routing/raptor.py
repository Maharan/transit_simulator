from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.gtfs.models import StopTime, Transfer
from core.routing.td_dijkstra import ChosenEdge, PathResult
from core.routing.utils import parse_time_to_seconds, seconds_to_time_str

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


INF_TIME = 10**18


@dataclass(frozen=True, slots=True)
class RaptorTrip:
    trip_id: str
    route_id: str | None
    service_id: str | None
    arrivals: tuple[int, ...]
    departures: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RaptorRoute:
    route_key: str
    public_route_id: str | None
    stop_ids: tuple[str, ...]
    trips: tuple[RaptorTrip, ...]
    departures_by_stop: tuple[tuple[int, ...], ...]
    trip_indices_by_stop: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class RaptorFootpath:
    to_stop_id: str
    duration_sec: int
    transfer_type: int | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class RaptorTimetable:
    routes: dict[str, RaptorRoute]
    stop_to_routes: dict[str, tuple[str, ...]]
    route_stop_indices: dict[tuple[str, str], tuple[int, ...]]
    footpaths_from: dict[str, tuple[RaptorFootpath, ...]]
    stops: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RaptorSourceCandidate:
    stop_id: str
    access_time_sec: int


@dataclass(frozen=True, slots=True)
class RaptorTargetCandidate:
    stop_id: str
    egress_time_sec: int


@dataclass(frozen=True, slots=True)
class RaptorQuery:
    source_candidates: tuple[RaptorSourceCandidate, ...]
    target_candidates: tuple[RaptorTargetCandidate, ...]
    departure_time_sec: int
    max_rounds: int = 8
    transfer_penalty_sec: int = 0
    max_wait_sec: int | None = None
    time_horizon_sec: int | None = None


@dataclass(frozen=True, slots=True)
class RaptorWalkParent:
    from_stop_id: str
    duration_sec: int
    transfer_type: int | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class RaptorTripParent:
    from_stop_id: str
    trip_id: str
    route_id: str | None
    departure_time_sec: int


@dataclass(frozen=True, slots=True)
class RaptorLabel:
    arrival_time_sec: int
    parent: RaptorWalkParent | RaptorTripParent | None


@dataclass(frozen=True, slots=True)
class RaptorJourneyOption:
    path_result: PathResult
    target_stop_id: str
    round_k: int
    transit_arrival_time_sec: int
    final_arrival_time_sec: int
    transit_legs: int
    major_trip_transfers: int


@dataclass(frozen=True, slots=True)
class _RaptorTargetHit:
    stop_id: str
    transit_arrival_time_sec: int
    final_arrival_time_sec: int
    round_k: int


@dataclass(frozen=True, slots=True)
class RaptorResult:
    path_result: PathResult
    best_target_stop_id: str | None
    best_round: int | None
    transit_arrival_time_sec: int | None
    options: tuple[RaptorJourneyOption, ...] = ()


def build_raptor_timetable_from_gtfs(
    session: "Session",
    feed_id: str,
    *,
    symmetric_transfers: bool = False,
    enable_walking: bool = True,
    walk_max_distance_m: int = 500,
    walk_speed_mps: float = 1.4,
    walk_max_neighbors: int = 8,
    progress: bool = False,
    progress_every: int = 5000,
) -> RaptorTimetable:
    from core.graph.graph_methods.gtfs_support import (
        EMPTY_TRIP_BUILD_METADATA,
        load_stop_context,
        load_trip_metadata,
    )
    from core.graph.walk import WALK_EDGE_LABEL, build_walk_edges

    stop_context = load_stop_context(
        session,
        feed_id,
        progress=progress,
        progress_every=progress_every,
        progress_label="for RAPTOR",
    )
    parent_map = stop_context.canonical_stop_by_stop_id
    stop_coords = stop_context.coordinates_by_canonical_stop_id
    trip_meta = load_trip_metadata(session, feed_id)

    grouped_trips: dict[
        tuple[str | None, int | None, tuple[str, ...]], list[RaptorTrip]
    ] = defaultdict(list)
    scanned_rows = 0
    built_trips = 0
    skipped_trips = 0
    current_trip_id: str | None = None
    current_stop_ids: list[str] = []
    current_arrivals: list[int] = []
    current_departures: list[int] = []
    current_invalid = False

    def flush_current_trip() -> None:
        nonlocal built_trips, skipped_trips
        if current_trip_id is None:
            return
        if current_invalid or len(current_stop_ids) < 2:
            skipped_trips += 1
            return

        previous_departure: int | None = None
        for arrival_time_sec, departure_time_sec in zip(
            current_arrivals,
            current_departures,
            strict=False,
        ):
            if departure_time_sec < arrival_time_sec:
                skipped_trips += 1
                return
            if previous_departure is not None and arrival_time_sec < previous_departure:
                skipped_trips += 1
                return
            previous_departure = departure_time_sec

        trip = trip_meta.get(current_trip_id, EMPTY_TRIP_BUILD_METADATA)
        route_key = (
            trip.route_id,
            trip.direction_id,
            tuple(current_stop_ids),
        )
        grouped_trips[route_key].append(
            RaptorTrip(
                trip_id=current_trip_id,
                route_id=trip.route_id,
                service_id=trip.service_id,
                arrivals=tuple(current_arrivals),
                departures=tuple(current_departures),
            )
        )
        built_trips += 1

    stop_time_rows = (
        session.query(
            StopTime.trip_id,
            StopTime.stop_id,
            StopTime.stop_sequence,
            StopTime.arrival_time,
            StopTime.departure_time,
        )
        .filter(StopTime.feed_id == feed_id)
        .order_by(StopTime.trip_id.asc(), StopTime.stop_sequence.asc())
        .yield_per(5000)
    )

    for (
        trip_id,
        stop_id,
        _stop_sequence,
        arrival_time,
        departure_time,
    ) in stop_time_rows:
        if not trip_id or not stop_id:
            continue
        if trip_id != current_trip_id:
            flush_current_trip()
            current_trip_id = trip_id
            current_stop_ids = []
            current_arrivals = []
            current_departures = []
            current_invalid = False

        canonical_stop_id = parent_map.get(stop_id, stop_id)
        arrival_time_sec = parse_time_to_seconds(arrival_time or departure_time)
        departure_time_sec = parse_time_to_seconds(departure_time or arrival_time)
        if arrival_time_sec is None or departure_time_sec is None:
            current_invalid = True
            scanned_rows += 1
            continue

        if current_stop_ids and current_stop_ids[-1] == canonical_stop_id:
            current_arrivals[-1] = min(current_arrivals[-1], arrival_time_sec)
            current_departures[-1] = max(current_departures[-1], departure_time_sec)
        else:
            current_stop_ids.append(canonical_stop_id)
            current_arrivals.append(arrival_time_sec)
            current_departures.append(departure_time_sec)

        scanned_rows += 1
        if progress and scanned_rows % progress_every == 0:
            print(f"Scanned {scanned_rows} stop_times rows for RAPTOR...")

    flush_current_trip()

    if progress:
        print(f"Scanned {scanned_rows} stop_times rows for RAPTOR total.")
        print(
            f"Prepared {built_trips} RAPTOR trip(s); skipped {skipped_trips} invalid trip(s)."
        )

    routes: dict[str, RaptorRoute] = {}
    stop_to_routes_sets: dict[str, set[str]] = defaultdict(set)
    route_stop_indices_lists: dict[tuple[str, str], list[int]] = defaultdict(list)

    for route_number, (route_group_key, trips) in enumerate(
        grouped_trips.items(),
        start=1,
    ):
        public_route_id, _direction_id, stop_ids = route_group_key
        ordered_trips = sorted(
            trips,
            key=lambda trip: (
                trip.departures[0],
                trip.arrivals[-1],
                trip.trip_id,
            ),
        )
        route_key = f"raptor_route_{route_number}"
        departures_by_stop: list[tuple[int, ...]] = []
        trip_indices_by_stop: list[tuple[int, ...]] = []
        for stop_index in range(len(stop_ids)):
            ordered_departures = sorted(
                (
                    trip.departures[stop_index],
                    trip_index,
                )
                for trip_index, trip in enumerate(ordered_trips)
            )
            departures_by_stop.append(
                tuple(departure for departure, _trip_index in ordered_departures)
            )
            trip_indices_by_stop.append(
                tuple(trip_index for _departure, trip_index in ordered_departures)
            )

        routes[route_key] = RaptorRoute(
            route_key=route_key,
            public_route_id=public_route_id,
            stop_ids=stop_ids,
            trips=tuple(ordered_trips),
            departures_by_stop=tuple(departures_by_stop),
            trip_indices_by_stop=tuple(trip_indices_by_stop),
        )
        for stop_index, stop_id in enumerate(stop_ids):
            stop_to_routes_sets[stop_id].add(route_key)
            route_stop_indices_lists[(route_key, stop_id)].append(stop_index)

    footpaths_by_from_stop: dict[str, dict[str, RaptorFootpath]] = defaultdict(dict)
    explicit_stop_pairs: set[tuple[str, str]] = set()

    def add_footpath(
        *,
        from_stop_id: str,
        to_stop_id: str,
        duration_sec: int | None,
        transfer_type: int | None = None,
        label: str | None = None,
    ) -> None:
        if from_stop_id == to_stop_id:
            return
        normalized_duration = max(0, int(duration_sec or 0))
        candidate = RaptorFootpath(
            to_stop_id=to_stop_id,
            duration_sec=normalized_duration,
            transfer_type=transfer_type,
            label=label,
        )
        existing = footpaths_by_from_stop[from_stop_id].get(to_stop_id)
        if existing is None:
            footpaths_by_from_stop[from_stop_id][to_stop_id] = candidate
            return
        existing_is_walk = existing.label == WALK_EDGE_LABEL
        candidate_is_walk = candidate.label == WALK_EDGE_LABEL
        if existing_is_walk and not candidate_is_walk:
            footpaths_by_from_stop[from_stop_id][to_stop_id] = candidate
            return
        if candidate_is_walk and not existing_is_walk:
            return
        if candidate.duration_sec < existing.duration_sec:
            footpaths_by_from_stop[from_stop_id][to_stop_id] = candidate

    transfer_rows = (
        session.query(
            Transfer.from_stop_id,
            Transfer.to_stop_id,
            Transfer.min_transfer_time,
            Transfer.transfer_type,
        )
        .filter(Transfer.feed_id == feed_id)
        .yield_per(5000)
    )
    explicit_transfer_rows = 0
    explicit_transfer_count = 0
    for from_stop_id, to_stop_id, min_transfer_time, transfer_type in transfer_rows:
        explicit_transfer_rows += 1
        if progress and explicit_transfer_rows % progress_every == 0:
            print(
                "Scanned "
                f"{explicit_transfer_rows} transfer row(s) while building RAPTOR footpaths..."
            )
        if not from_stop_id or not to_stop_id:
            continue
        canonical_from_stop_id = parent_map.get(from_stop_id, from_stop_id)
        canonical_to_stop_id = parent_map.get(to_stop_id, to_stop_id)
        if canonical_from_stop_id == canonical_to_stop_id:
            continue
        explicit_stop_pairs.add((canonical_from_stop_id, canonical_to_stop_id))
        add_footpath(
            from_stop_id=canonical_from_stop_id,
            to_stop_id=canonical_to_stop_id,
            duration_sec=min_transfer_time,
            transfer_type=transfer_type,
            label="transfer",
        )
        explicit_transfer_count += 1
        if symmetric_transfers:
            explicit_stop_pairs.add((canonical_to_stop_id, canonical_from_stop_id))
            add_footpath(
                from_stop_id=canonical_to_stop_id,
                to_stop_id=canonical_from_stop_id,
                duration_sec=min_transfer_time,
                transfer_type=transfer_type,
                label="transfer",
            )
            explicit_transfer_count += 1

    if progress:
        print(f"Prepared {explicit_transfer_count} explicit RAPTOR footpath(s).")

    if enable_walking:
        walk_specs = build_walk_edges(
            stop_coords=stop_coords,
            max_distance_m=walk_max_distance_m,
            walking_speed_mps=walk_speed_mps,
            max_neighbors=walk_max_neighbors,
            existing_edges=explicit_stop_pairs,
        )
        for spec in walk_specs:
            add_footpath(
                from_stop_id=spec.from_stop_id,
                to_stop_id=spec.to_stop_id,
                duration_sec=spec.duration_sec,
                transfer_type=None,
                label=WALK_EDGE_LABEL,
            )
        if progress:
            print(f"Prepared {len(walk_specs)} synthetic RAPTOR walk footpath(s).")

    footpaths_from = {
        from_stop_id: tuple(
            sorted(
                footpaths.values(),
                key=lambda footpath: (
                    footpath.duration_sec,
                    footpath.to_stop_id,
                ),
            )
        )
        for from_stop_id, footpaths in footpaths_by_from_stop.items()
    }

    stops = tuple(sorted(set(parent_map.values())))
    stop_to_routes = {
        stop_id: tuple(sorted(route_keys))
        for stop_id, route_keys in stop_to_routes_sets.items()
    }
    route_stop_indices = {
        key: tuple(indices) for key, indices in route_stop_indices_lists.items()
    }
    return RaptorTimetable(
        routes=routes,
        stop_to_routes=stop_to_routes,
        route_stop_indices=route_stop_indices,
        footpaths_from=footpaths_from,
        stops=stops,
    )


def run_raptor(
    timetable: RaptorTimetable,
    query: RaptorQuery,
) -> RaptorResult:
    if query.max_rounds < 0:
        raise ValueError("max_rounds must be >= 0.")
    if query.max_wait_sec is not None and query.max_wait_sec < 0:
        raise ValueError("max_wait_sec must be >= 0 when provided.")

    tau_prev = {stop_id: INF_TIME for stop_id in timetable.stops}
    labels_by_round: list[dict[str, RaptorLabel]] = [{}]
    target_egress = {
        candidate.stop_id: candidate.egress_time_sec
        for candidate in query.target_candidates
    }
    horizon_end = (
        query.departure_time_sec + query.time_horizon_sec
        if query.time_horizon_sec is not None
        else None
    )

    best_final_arrival_sec = INF_TIME
    round_target_hits: dict[int, _RaptorTargetHit] = {}

    def update_best_target(
        *, stop_id: str, arrival_time_sec: int, round_k: int
    ) -> None:
        nonlocal best_final_arrival_sec
        egress_time_sec = target_egress.get(stop_id)
        if egress_time_sec is None:
            return
        final_arrival_sec = arrival_time_sec + egress_time_sec
        if horizon_end is not None and final_arrival_sec > horizon_end:
            return
        existing_round_hit = round_target_hits.get(round_k)
        if (
            existing_round_hit is None
            or final_arrival_sec < existing_round_hit.final_arrival_time_sec
        ):
            round_target_hits[round_k] = _RaptorTargetHit(
                stop_id=stop_id,
                transit_arrival_time_sec=arrival_time_sec,
                final_arrival_time_sec=final_arrival_sec,
                round_k=round_k,
            )
        if final_arrival_sec >= best_final_arrival_sec:
            return
        best_final_arrival_sec = final_arrival_sec

    def improve_stop(
        *,
        tau: dict[str, int],
        labels: dict[str, RaptorLabel],
        marked: set[str],
        stop_id: str,
        arrival_time_sec: int,
        round_k: int,
        parent: RaptorWalkParent | RaptorTripParent | None,
    ) -> bool:
        if horizon_end is not None and arrival_time_sec > horizon_end:
            return False
        if arrival_time_sec >= tau.get(stop_id, INF_TIME):
            return False
        tau[stop_id] = arrival_time_sec
        labels[stop_id] = RaptorLabel(
            arrival_time_sec=arrival_time_sec,
            parent=parent,
        )
        marked.add(stop_id)
        update_best_target(
            stop_id=stop_id,
            arrival_time_sec=arrival_time_sec,
            round_k=round_k,
        )
        return True

    def relax_footpaths(
        *,
        tau: dict[str, int],
        labels: dict[str, RaptorLabel],
        seed_stops: set[str],
        round_k: int,
    ) -> set[str]:
        new_marked_stops: set[str] = set()
        queue = deque(sorted(seed_stops))
        while queue:
            from_stop_id = queue.popleft()
            from_arrival_sec = tau.get(from_stop_id, INF_TIME)
            if from_arrival_sec >= INF_TIME:
                continue
            for footpath in timetable.footpaths_from.get(from_stop_id, ()):
                candidate_arrival_sec = from_arrival_sec + footpath.duration_sec
                if candidate_arrival_sec >= best_final_arrival_sec:
                    continue
                improved = improve_stop(
                    tau=tau,
                    labels=labels,
                    marked=new_marked_stops,
                    stop_id=footpath.to_stop_id,
                    arrival_time_sec=candidate_arrival_sec,
                    round_k=round_k,
                    parent=RaptorWalkParent(
                        from_stop_id=from_stop_id,
                        duration_sec=footpath.duration_sec,
                        transfer_type=footpath.transfer_type,
                        label=footpath.label,
                    ),
                )
                if improved:
                    queue.append(footpath.to_stop_id)
        return new_marked_stops

    marked_stops: set[str] = set()
    for source_candidate in query.source_candidates:
        improve_stop(
            tau=tau_prev,
            labels=labels_by_round[0],
            marked=marked_stops,
            stop_id=source_candidate.stop_id,
            arrival_time_sec=query.departure_time_sec
            + source_candidate.access_time_sec,
            round_k=0,
            parent=None,
        )
    marked_stops |= relax_footpaths(
        tau=tau_prev,
        labels=labels_by_round[0],
        seed_stops=set(marked_stops),
        round_k=0,
    )

    effective_transfer_penalty_sec = query.transfer_penalty_sec

    for round_k in range(1, query.max_rounds + 1):
        if not marked_stops:
            break

        tau_cur = dict(tau_prev)
        labels_cur: dict[str, RaptorLabel] = {}
        routes_to_scan: dict[str, int] = {}
        for stop_id in marked_stops:
            for route_key in timetable.stop_to_routes.get(stop_id, ()):
                for stop_index in timetable.route_stop_indices.get(
                    (route_key, stop_id),
                    (),
                ):
                    existing_start_index = routes_to_scan.get(route_key)
                    if (
                        existing_start_index is None
                        or stop_index < existing_start_index
                    ):
                        routes_to_scan[route_key] = stop_index

        new_marked_stops: set[str] = set()
        for route_key, start_stop_index in routes_to_scan.items():
            route = timetable.routes[route_key]
            current_trip_index: int | None = None
            boarded_from_stop_id: str | None = None
            boarded_departure_time_sec: int | None = None
            for stop_index in range(start_stop_index, len(route.stop_ids)):
                stop_id = route.stop_ids[stop_index]

                if current_trip_index is not None:
                    current_trip = route.trips[current_trip_index]
                    arrival_time_sec = current_trip.arrivals[stop_index]
                    if arrival_time_sec < tau_cur.get(stop_id, INF_TIME):
                        improve_stop(
                            tau=tau_cur,
                            labels=labels_cur,
                            marked=new_marked_stops,
                            stop_id=stop_id,
                            arrival_time_sec=arrival_time_sec,
                            round_k=round_k,
                            parent=RaptorTripParent(
                                from_stop_id=boarded_from_stop_id or stop_id,
                                trip_id=current_trip.trip_id,
                                route_id=current_trip.route_id,
                                departure_time_sec=boarded_departure_time_sec
                                or arrival_time_sec,
                            ),
                        )

                ready_time_sec = tau_prev.get(stop_id, INF_TIME)
                if ready_time_sec >= INF_TIME:
                    continue
                if round_k > 1 and effective_transfer_penalty_sec > 0:
                    ready_time_sec += effective_transfer_penalty_sec
                candidate_trip_index = _earliest_boardable_trip(
                    route=route,
                    stop_index=stop_index,
                    ready_time_sec=ready_time_sec,
                    max_wait_sec=query.max_wait_sec,
                    horizon_end_sec=horizon_end,
                )
                if candidate_trip_index is None:
                    continue
                candidate_trip = route.trips[candidate_trip_index]
                candidate_departure_time_sec = candidate_trip.departures[stop_index]
                if current_trip_index is None:
                    current_trip_index = candidate_trip_index
                    boarded_from_stop_id = stop_id
                    boarded_departure_time_sec = candidate_departure_time_sec
                    continue
                current_departure_time_sec = route.trips[current_trip_index].departures[
                    stop_index
                ]
                if candidate_departure_time_sec < current_departure_time_sec:
                    current_trip_index = candidate_trip_index
                    boarded_from_stop_id = stop_id
                    boarded_departure_time_sec = candidate_departure_time_sec

        new_marked_stops |= relax_footpaths(
            tau=tau_cur,
            labels=labels_cur,
            seed_stops=set(new_marked_stops),
            round_k=round_k,
        )
        labels_by_round.append(labels_cur)
        tau_prev = tau_cur
        marked_stops = new_marked_stops

    journey_options = _build_journey_options(
        labels_by_round=labels_by_round,
        round_target_hits=round_target_hits,
    )
    if not journey_options:
        return RaptorResult(
            path_result=PathResult(arrival_time_sec=None, stop_path=[], edge_path=[]),
            best_target_stop_id=None,
            best_round=None,
            transit_arrival_time_sec=None,
            options=(),
        )

    best_option = min(
        journey_options,
        key=lambda option: (
            option.final_arrival_time_sec,
            option.major_trip_transfers,
            option.round_k,
        ),
    )
    return RaptorResult(
        path_result=best_option.path_result,
        best_target_stop_id=best_option.target_stop_id,
        best_round=best_option.round_k,
        transit_arrival_time_sec=best_option.transit_arrival_time_sec,
        options=journey_options,
    )


def _earliest_boardable_trip(
    *,
    route: RaptorRoute,
    stop_index: int,
    ready_time_sec: int,
    max_wait_sec: int | None,
    horizon_end_sec: int | None,
) -> int | None:
    departures = route.departures_by_stop[stop_index]
    trip_indices = route.trip_indices_by_stop[stop_index]
    position = bisect_left(departures, ready_time_sec)
    if position >= len(departures):
        return None
    departure_time_sec = departures[position]
    if max_wait_sec is not None and departure_time_sec - ready_time_sec > max_wait_sec:
        return None
    if horizon_end_sec is not None and departure_time_sec > horizon_end_sec:
        return None
    return trip_indices[position]


def _reconstruct_path(
    *,
    labels_by_round: list[dict[str, RaptorLabel]],
    best_target_stop_id: str,
    best_round: int,
    final_arrival_time_sec: int,
) -> PathResult:
    current_stop_id = best_target_stop_id
    current_round = best_round
    stop_path_reversed = [best_target_stop_id]
    edge_path_reversed: list[ChosenEdge] = []

    while True:
        label = labels_by_round[current_round].get(current_stop_id)
        if label is None:
            return PathResult(arrival_time_sec=None, stop_path=[], edge_path=[])
        if label.parent is None:
            break
        if isinstance(label.parent, RaptorWalkParent):
            edge_path_reversed.append(
                ChosenEdge(
                    to_stop_id=current_stop_id,
                    weight_sec=label.parent.duration_sec,
                    kind="transfer",
                    trip_id=None,
                    route_id=None,
                    dep_time=None,
                    arr_time=None,
                    dep_time_sec=None,
                    arr_time_sec=None,
                    transfer_type=label.parent.transfer_type,
                    apply_penalty=False,
                    label=label.parent.label,
                )
            )
            current_stop_id = label.parent.from_stop_id
            stop_path_reversed.append(current_stop_id)
            continue

        edge_weight_sec = label.arrival_time_sec - label.parent.departure_time_sec
        edge_path_reversed.append(
            ChosenEdge(
                to_stop_id=current_stop_id,
                weight_sec=edge_weight_sec,
                kind="trip",
                trip_id=label.parent.trip_id,
                route_id=label.parent.route_id,
                dep_time=seconds_to_time_str(label.parent.departure_time_sec),
                arr_time=seconds_to_time_str(label.arrival_time_sec),
                dep_time_sec=label.parent.departure_time_sec,
                arr_time_sec=label.arrival_time_sec,
                transfer_type=None,
                apply_penalty=True,
                label=None,
            )
        )
        current_stop_id = label.parent.from_stop_id
        current_round -= 1
        stop_path_reversed.append(current_stop_id)

    stop_path = list(reversed(stop_path_reversed))
    edge_path = list(reversed(edge_path_reversed))
    return PathResult(
        arrival_time_sec=final_arrival_time_sec,
        stop_path=stop_path,
        edge_path=edge_path,
    )


def _build_journey_options(
    *,
    labels_by_round: list[dict[str, RaptorLabel]],
    round_target_hits: dict[int, _RaptorTargetHit],
) -> tuple[RaptorJourneyOption, ...]:
    journey_options: list[RaptorJourneyOption] = []
    best_final_arrival_sec = INF_TIME

    for round_k in sorted(round_target_hits):
        target_hit = round_target_hits[round_k]
        if target_hit.final_arrival_time_sec >= best_final_arrival_sec:
            continue
        path_result = _reconstruct_path(
            labels_by_round=labels_by_round,
            best_target_stop_id=target_hit.stop_id,
            best_round=round_k,
            final_arrival_time_sec=target_hit.final_arrival_time_sec,
        )
        if path_result.arrival_time_sec is None:
            continue
        transit_legs = sum(1 for edge in path_result.edge_path if edge.kind == "trip")
        journey_options.append(
            RaptorJourneyOption(
                path_result=path_result,
                target_stop_id=target_hit.stop_id,
                round_k=round_k,
                transit_arrival_time_sec=target_hit.transit_arrival_time_sec,
                final_arrival_time_sec=target_hit.final_arrival_time_sec,
                transit_legs=transit_legs,
                major_trip_transfers=max(transit_legs - 1, 0),
            )
        )
        best_final_arrival_sec = target_hit.final_arrival_time_sec

    journey_options.sort(
        key=lambda option: (
            -option.final_arrival_time_sec,
            option.major_trip_transfers,
            option.round_k,
        )
    )
    return tuple(journey_options)
