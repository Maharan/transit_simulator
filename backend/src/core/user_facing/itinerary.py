from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.routing.types import ResultLike
from core.routing.utils import parse_time_to_seconds, seconds_to_time_str

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Itinerary:
    summary: str
    timing: str
    path_lines: list[str] = field(default_factory=list)
    leg_lines: list[str] = field(default_factory=list)
    stops: list["ItineraryStop"] = field(default_factory=list)
    path_segments: list["ItineraryPathSegment"] = field(default_factory=list)
    legs: list["ItineraryLeg"] = field(default_factory=list)

    def lines(self) -> list[str]:
        lines = [self.summary, self.timing]
        if self.path_lines:
            lines.append("Path:")
            lines.extend(self.path_lines)
        if self.leg_lines:
            lines.append("Legs:")
            lines.extend(self.leg_lines)
        return lines


class ItineraryBuilder:
    def __init__(
        self,
        *,
        stop_names: dict[str, str],
        route_short_names: dict[str, str],
        transfer_penalty_sec: int,
    ) -> None:
        self._stop_names = stop_names
        self._route_short_names = route_short_names
        self._transfer_penalty_sec = transfer_penalty_sec

    def build(
        self,
        result: ResultLike,
        *,
        from_stop_name: str,
        to_stop_name: str,
        depart_time_str: str,
    ) -> Itinerary:
        if result.arrival_time_sec is None:
            raise ValueError("Itinerary requires a successful routing result.")
        depart_time_sec = parse_time_to_seconds(depart_time_str)
        if depart_time_sec is None:
            raise ValueError("Invalid depart_time_str. Expected HH:MM:SS.")

        travel_sec = result.arrival_time_sec - depart_time_sec
        minutes = travel_sec / 60
        summary = (
            f"{from_stop_name} -> {to_stop_name}: {travel_sec} sec ({minutes:.1f} min)"
        )
        timing = (
            f"Depart: {depart_time_str} | "
            f"Arrive: {self._format_seconds(result.arrival_time_sec)}"
        )

        stops = self._build_stops(result)
        path_segments = self._build_path_segments(
            stops=stops, edge_path=result.edge_path
        )
        path_lines = self._build_path_lines(path_segments)
        legs = self._build_legs(result)
        leg_lines = self._build_leg_lines(legs)
        return Itinerary(
            summary=summary,
            timing=timing,
            stops=stops,
            path_segments=path_segments,
            path_lines=path_lines,
            leg_lines=leg_lines,
            legs=legs,
        )

    def _build_stops(self, result: ResultLike) -> list["ItineraryStop"]:
        if not result.stop_path:
            return []
        return [
            ItineraryStop(
                stop_id=stop_id,
                stop_name=self._stop_names.get(stop_id, stop_id),
            )
            for stop_id in result.stop_path
        ]

    def _build_path_segments(
        self,
        *,
        stops: list["ItineraryStop"],
        edge_path,
    ) -> list["ItineraryPathSegment"]:
        if not stops or not edge_path:
            return []
        segments: list[ItineraryPathSegment] = []
        for index, edge in enumerate(edge_path):
            if index + 1 >= len(stops):
                break
            from_stop = stops[index]
            to_stop = stops[index + 1]
            route = None
            if edge.route_id:
                route = self._route_short_names.get(edge.route_id) or edge.route_id
            segments.append(
                ItineraryPathSegment(
                    from_stop=from_stop,
                    to_stop=to_stop,
                    edge=ItineraryPathEdge(
                        kind=edge.kind,
                        label=getattr(edge, "label", None),
                        weight_sec=edge.weight_sec,
                        route=route,
                        route_id=edge.route_id,
                        trip_id=edge.trip_id,
                        dep_time=edge.dep_time,
                        arr_time=edge.arr_time,
                        dep_time_sec=edge.dep_time_sec,
                        arr_time_sec=edge.arr_time_sec,
                        transfer_type=edge.transfer_type,
                        apply_penalty=getattr(edge, "apply_penalty", True),
                    ),
                )
            )
        return segments

    def _build_path_lines(
        self,
        path_segments: list["ItineraryPathSegment"],
    ) -> list[str]:
        if not path_segments:
            return []
        lines: list[str] = []
        for segment in path_segments:
            lines.append(
                f"  {segment.from_stop.stop_name} ({segment.from_stop.stop_id})"
            )
            lines.append(
                "    -> "
                f"{segment.to_stop.stop_name} ({segment.to_stop.stop_id}) "
                f"[{self._format_edge(segment.edge)}]"
            )
        return lines

    def _build_legs(self, result: ResultLike) -> list["ItineraryLeg"]:
        return self._summarize_legs(result.edge_path, result.stop_path)

    def _build_leg_lines(self, legs: list["ItineraryLeg"]) -> list[str]:
        return [f"  {leg.text}" for leg in legs]

    def _format_seconds(self, total_seconds: int | None) -> str:
        if total_seconds is None:
            return "n/a"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _format_duration(self, total_seconds: int | None) -> str:
        if total_seconds is None:
            return "n/a"
        minutes = total_seconds / 60
        return f"{total_seconds}s ({minutes:.1f} min)"

    def _format_edge(self, edge) -> str:
        label = getattr(edge, "label", None)
        parts: list[str] = [label or edge.kind]
        if edge.kind == "trip":
            route_label = getattr(edge, "route", None)
            if route_label:
                parts.append(f"route={route_label}")
            elif edge.route_id:
                route_short = self._route_short_names.get(edge.route_id)
                if route_short:
                    parts.append(f"route={route_short}")
                else:
                    parts.append(f"route={edge.route_id}")
            if edge.trip_id:
                parts.append(f"trip={edge.trip_id}")
            if edge.dep_time and edge.arr_time:
                parts.append(f"{edge.dep_time}->{edge.arr_time}")
            elif edge.dep_time_sec is not None and edge.arr_time_sec is not None:
                dep_str = seconds_to_time_str(edge.dep_time_sec)
                arr_str = seconds_to_time_str(edge.arr_time_sec)
                if dep_str and arr_str:
                    parts.append(f"{dep_str}->{arr_str}")
        if edge.kind == "transfer" and edge.transfer_type is not None:
            parts.append(f"type={edge.transfer_type}")
        if edge.weight_sec is not None:
            parts.append(f"{edge.weight_sec}s")
        apply_penalty = getattr(edge, "apply_penalty", True)
        if edge.kind == "transfer" and self._transfer_penalty_sec and apply_penalty:
            parts.append(f"+{self._transfer_penalty_sec}s penalty")
        return ", ".join(parts)

    def _summarize_legs(self, edge_path, stop_path) -> list["ItineraryLeg"]:
        legs: list[ItineraryLeg] = []
        current_route: str | None = None
        leg_start_name: str | None = None
        leg_time_sec: int | None = 0

        for index, edge in enumerate(edge_path):
            from_stop = stop_path[index]
            to_stop = stop_path[index + 1]
            from_name = self._stop_names.get(from_stop, from_stop)
            to_name = self._stop_names.get(to_stop, to_stop)

            if edge.kind == "transfer":
                if current_route:
                    legs.append(
                        self._create_leg(
                            mode="ride",
                            from_stop=leg_start_name,
                            to_stop=from_name,
                            route=current_route,
                            duration_sec=leg_time_sec,
                        )
                    )
                    current_route = None
                    leg_start_name = None
                    leg_time_sec = 0
                transfer_time = edge.weight_sec
                apply_penalty = getattr(edge, "apply_penalty", True)
                if transfer_time is not None and apply_penalty:
                    transfer_time += self._transfer_penalty_sec
                transfer_label = "Transfer"
                edge_label = getattr(edge, "label", None)
                if edge_label == "station_link":
                    transfer_label = "Station link"
                elif edge_label == "walk":
                    transfer_label = "Walk"
                legs.append(
                    self._create_leg(
                        mode=transfer_label.lower().replace(" ", "_"),
                        from_stop=from_name,
                        to_stop=to_name,
                        route=None,
                        duration_sec=transfer_time,
                    )
                )
                continue

            if edge.kind == "trip":
                if edge.route_id:
                    route_label = (
                        self._route_short_names.get(edge.route_id) or edge.route_id
                    )
                else:
                    route_label = "unknown route"

                if current_route is None:
                    current_route = route_label
                    leg_start_name = from_name
                    leg_time_sec = 0
                elif current_route != route_label:
                    legs.append(
                        self._create_leg(
                            mode="ride",
                            from_stop=leg_start_name,
                            to_stop=from_name,
                            route=current_route,
                            duration_sec=leg_time_sec,
                        )
                    )
                    current_route = route_label
                    leg_start_name = from_name
                    leg_time_sec = 0

                edge_duration = edge.weight_sec
                if edge_duration is None:
                    dep_sec = edge.dep_time_sec
                    arr_sec = edge.arr_time_sec
                    if dep_sec is None or arr_sec is None:
                        dep_sec = parse_time_to_seconds(getattr(edge, "dep_time", None))
                        arr_sec = parse_time_to_seconds(getattr(edge, "arr_time", None))
                    if (
                        dep_sec is not None
                        and arr_sec is not None
                        and arr_sec >= dep_sec
                    ):
                        edge_duration = arr_sec - dep_sec
                if edge_duration is not None:
                    leg_time_sec = (leg_time_sec or 0) + edge_duration
                else:
                    leg_time_sec = None

        if current_route:
            legs.append(
                self._create_leg(
                    mode="ride",
                    from_stop=leg_start_name,
                    to_stop=self._stop_names.get(stop_path[-1], stop_path[-1]),
                    route=current_route,
                    duration_sec=leg_time_sec,
                )
            )
        return legs

    def _create_leg(
        self,
        *,
        mode: str,
        from_stop: str | None,
        to_stop: str | None,
        route: str | None,
        duration_sec: int | None,
    ) -> "ItineraryLeg":
        duration_min = None if duration_sec is None else duration_sec / 60.0
        duration_label = self._format_duration(duration_sec)
        if mode == "ride":
            route_label = route or "unknown route"
            text = (
                f"Ride {route_label} from {from_stop} to {to_stop} ({duration_label})"
            )
        else:
            mode_label = mode.replace("_", " ").title()
            text = f"{mode_label} from {from_stop} to {to_stop} ({duration_label})"
        return ItineraryLeg(
            mode=mode,
            from_stop=from_stop,
            to_stop=to_stop,
            route=route,
            duration_sec=duration_sec,
            duration_min=duration_min,
            text=text,
        )


@dataclass(frozen=True)
class ItineraryLeg:
    mode: str
    from_stop: str | None
    to_stop: str | None
    route: str | None
    duration_sec: int | None
    duration_min: float | None
    text: str


@dataclass(frozen=True)
class ItineraryStop:
    stop_id: str
    stop_name: str


@dataclass(frozen=True)
class ItineraryPathEdge:
    kind: str
    label: str | None
    weight_sec: int | None
    route: str | None
    route_id: str | None
    trip_id: str | None
    dep_time: str | None
    arr_time: str | None
    dep_time_sec: int | None
    arr_time_sec: int | None
    transfer_type: int | None
    apply_penalty: bool


@dataclass(frozen=True)
class ItineraryPathSegment:
    from_stop: ItineraryStop
    to_stop: ItineraryStop
    edge: ItineraryPathEdge


def create_itinerary_data(
    *,
    session: "Session",
    feed_id: str,
    stop_ids: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    from core.gtfs.models import Route, Stop

    route_rows = (
        session.query(Route.route_id, Route.route_short_name)
        .filter(Route.feed_id == feed_id)
        .all()
    )
    route_short_names = {
        route_id: route_short_name
        for route_id, route_short_name in route_rows
        if route_id and route_short_name
    }

    stop_name_rows = (
        session.query(Stop.stop_id, Stop.stop_name)
        .filter(Stop.feed_id == feed_id)
        .filter(Stop.stop_id.in_(stop_ids))
        .all()
    )
    stop_names = {stop_id: stop_name for stop_id, stop_name in stop_name_rows}
    return stop_names, route_short_names


def create_itinerary(
    *,
    result: ResultLike,
    from_stop_name: str,
    to_stop_name: str,
    depart_time_str: str,
    stop_names: dict[str, str],
    route_short_names: dict[str, str],
    transfer_penalty_sec: int,
) -> Itinerary:
    builder = ItineraryBuilder(
        stop_names=stop_names,
        route_short_names=route_short_names,
        transfer_penalty_sec=transfer_penalty_sec,
    )
    return builder.build(
        result,
        from_stop_name=from_stop_name,
        to_stop_name=to_stop_name,
        depart_time_str=depart_time_str,
    )
