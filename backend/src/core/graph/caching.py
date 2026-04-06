from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from core.graph.graph_methods.multi_edge_graph import GraphCache
from core.graph.graph_methods.trip_stop_anytime_graph import (
    build_trip_stop_anytime_graph_from_gtfs,
)
from core.graph.graph_methods.trip_stop_graph import build_trip_stop_graph_from_gtfs
from core.graph.lite import GraphLite
from core.routing.raptor import build_raptor_timetable_from_gtfs

GRAPH_METHOD_TRIP_STOP = "trip_stop"
GRAPH_METHOD_MULTI_EDGE = "multi_edge"
GRAPH_METHOD_TRIP_STOP_ANYTIME = "trip_stop_anytime"
GRAPH_METHOD_RAPTOR = "raptor"
DEFAULT_GRAPH_METHOD = GRAPH_METHOD_TRIP_STOP
SUPPORTED_GRAPH_METHODS: tuple[str, ...] = (
    GRAPH_METHOD_TRIP_STOP,
    GRAPH_METHOD_MULTI_EDGE,
    GRAPH_METHOD_TRIP_STOP_ANYTIME,
    GRAPH_METHOD_RAPTOR,
)

GRAPH_METHOD_ALIASES: dict[str, str] = {
    "trip_stop_schedule": GRAPH_METHOD_TRIP_STOP,
    "trip_stop_graph": GRAPH_METHOD_TRIP_STOP,
    "multi_edge_graph": GRAPH_METHOD_MULTI_EDGE,
    "raptor_timetable": GRAPH_METHOD_RAPTOR,
}


def normalize_graph_method(graph_method: str | None) -> str:
    if graph_method is None:
        return DEFAULT_GRAPH_METHOD
    normalized = graph_method.strip().lower()
    if not normalized:
        return DEFAULT_GRAPH_METHOD
    normalized = GRAPH_METHOD_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_GRAPH_METHODS:
        supported = ", ".join(SUPPORTED_GRAPH_METHODS)
        raise ValueError(
            f"Unsupported graph_method '{graph_method}'. Supported values: {supported}."
        )
    return normalized


@dataclass(frozen=True)
class GraphCacheKey:
    feed_id: str
    graph_cache_version: int
    graph_options: tuple[tuple[str, object], ...]


def _normalize_graph_options(
    graph_options: dict[str, object] | None,
) -> tuple[tuple[str, object], ...]:
    if not graph_options:
        return ()
    return tuple(sorted(graph_options.items(), key=lambda item: item[0]))


class InMemoryGraphCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._graphs: dict[GraphCacheKey, object] = {}

    def get(
        self,
        *,
        feed_id: str,
        graph_cache_version: int,
        graph_options: dict[str, object] | None = None,
    ) -> object | None:
        key = GraphCacheKey(
            feed_id=feed_id,
            graph_cache_version=graph_cache_version,
            graph_options=_normalize_graph_options(graph_options),
        )
        with self._lock:
            return self._graphs.get(key)

    def set(
        self,
        *,
        feed_id: str,
        graph_cache_version: int,
        graph_options: dict[str, object] | None = None,
        graph: object,
    ) -> None:
        key = GraphCacheKey(
            feed_id=feed_id,
            graph_cache_version=graph_cache_version,
            graph_options=_normalize_graph_options(graph_options),
        )
        with self._lock:
            self._graphs[key] = graph

    def delete(
        self,
        *,
        feed_id: str,
        graph_cache_version: int,
        graph_options: dict[str, object] | None = None,
    ) -> None:
        key = GraphCacheKey(
            feed_id=feed_id,
            graph_cache_version=graph_cache_version,
            graph_options=_normalize_graph_options(graph_options),
        )
        with self._lock:
            self._graphs.pop(key, None)


def get_pickle(
    *,
    cache_path: Path,
    feed_id: str,
    graph_cache_version: int,
    graph_options: dict[str, object] | None = None,
):
    try:
        with cache_path.open("rb") as handle:
            payload = pickle.load(handle)
        if (
            isinstance(payload, dict)
            and payload.get("feed_id") == feed_id
            and payload.get("version") == graph_cache_version
            and (
                graph_options is None
                or payload.get("graph_options", {}) == graph_options
            )
        ):
            return payload.get("graph")
    except Exception:
        return None
    return None


def create_pickle(
    *,
    cache_path: Path,
    feed_id: str,
    graph_cache_version: int,
    graph_options: dict[str, object] | None = None,
    graph,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as handle:
        pickle.dump(
            {
                "feed_id": feed_id,
                "graph": graph,
                "version": graph_cache_version,
                "graph_options": graph_options or {},
            },
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )


def access_or_create_graph_cache(
    *,
    session,
    feed_id: str,
    cache_path: Path | None,
    graph_cache_version: int,
    rebuild_cache: bool,
    symmetric_transfers: bool,
    enable_walking: bool,
    walk_max_distance_m: int,
    walk_speed_mps: float,
    walk_max_neighbors: int,
    graph_method: str = DEFAULT_GRAPH_METHOD,
    anytime_default_headway_sec: int | None = None,
    progress: bool = False,
    progress_every: int = 5000,
    in_memory_cache: InMemoryGraphCache | None = None,
) -> tuple[object, list[str]]:
    log_lines: list[str] = []
    graph_method = normalize_graph_method(graph_method)
    graph = None
    graph_options = {
        "graph_method": graph_method,
        "enable_walking": enable_walking,
        "walk_max_distance_m": walk_max_distance_m,
        "walk_speed_mps": walk_speed_mps,
        "walk_max_neighbors": walk_max_neighbors,
        "symmetric_transfers": symmetric_transfers,
        "anytime_default_headway_sec": anytime_default_headway_sec
        if graph_method == GRAPH_METHOD_TRIP_STOP_ANYTIME
        else None,
    }

    if in_memory_cache:
        if rebuild_cache:
            in_memory_cache.delete(
                feed_id=feed_id,
                graph_cache_version=graph_cache_version,
                graph_options=graph_options,
            )
        else:
            graph = in_memory_cache.get(
                feed_id=feed_id,
                graph_cache_version=graph_cache_version,
                graph_options=graph_options,
            )
            if graph is not None:
                log_lines.append("Loaded graph from in-memory cache.")

    if graph is None and cache_path and cache_path.exists() and not rebuild_cache:
        graph = get_pickle(
            cache_path=cache_path,
            feed_id=feed_id,
            graph_cache_version=graph_cache_version,
            graph_options=graph_options,
        )
        if graph is not None:
            log_lines.append(f"Loaded graph from pickle: {cache_path}")
        else:
            log_lines.append("Ignoring graph pickle because cache options mismatch.")

    if graph is None:
        if graph_method == GRAPH_METHOD_MULTI_EDGE:
            cache = GraphCache(
                session=session,
                feed_id=feed_id,
                rebuild=rebuild_cache,
                symmetric_transfers=symmetric_transfers,
                enable_walking=enable_walking,
                walk_max_distance_m=walk_max_distance_m,
                walk_speed_mps=walk_speed_mps,
                walk_max_neighbors=walk_max_neighbors,
                progress=progress,
                progress_every=progress_every,
            )
            graph = GraphLite.from_graph(cache.graph)
            log_lines.append("Loaded graph from DB cache.")
        elif graph_method == GRAPH_METHOD_TRIP_STOP:
            graph = build_trip_stop_graph_from_gtfs(
                session=session,
                feed_id=feed_id,
                symmetric_transfers=symmetric_transfers,
                enable_walking=enable_walking,
                walk_max_distance_m=walk_max_distance_m,
                walk_speed_mps=walk_speed_mps,
                walk_max_neighbors=walk_max_neighbors,
                progress=progress,
                progress_every=progress_every,
            )
            log_lines.append("Built trip-stop graph from GTFS.")
        elif graph_method == GRAPH_METHOD_TRIP_STOP_ANYTIME:
            graph = build_trip_stop_anytime_graph_from_gtfs(
                session=session,
                feed_id=feed_id,
                symmetric_transfers=symmetric_transfers,
                enable_walking=enable_walking,
                walk_max_distance_m=walk_max_distance_m,
                walk_speed_mps=walk_speed_mps,
                walk_max_neighbors=walk_max_neighbors,
                default_headway_sec=anytime_default_headway_sec,
                progress=progress,
                progress_every=progress_every,
            )
            log_lines.append("Built trip-stop anytime graph from GTFS.")
        elif graph_method == GRAPH_METHOD_RAPTOR:
            graph = build_raptor_timetable_from_gtfs(
                session=session,
                feed_id=feed_id,
                symmetric_transfers=symmetric_transfers,
                enable_walking=enable_walking,
                walk_max_distance_m=walk_max_distance_m,
                walk_speed_mps=walk_speed_mps,
                walk_max_neighbors=walk_max_neighbors,
                progress=progress,
                progress_every=progress_every,
            )
            log_lines.append("Built RAPTOR timetable from GTFS.")
        else:  # pragma: no cover - normalize_graph_method guards this.
            raise ValueError(f"Unsupported graph_method '{graph_method}'.")
        if cache_path:
            create_pickle(
                cache_path=cache_path,
                feed_id=feed_id,
                graph_cache_version=graph_cache_version,
                graph_options=graph_options,
                graph=graph,
            )
            log_lines.append(f"Wrote graph pickle: {cache_path}")

    if in_memory_cache and graph is not None:
        in_memory_cache.set(
            feed_id=feed_id,
            graph_cache_version=graph_cache_version,
            graph_options=graph_options,
            graph=graph,
        )
        log_lines.append("Stored graph in in-memory cache.")

    return graph, log_lines
