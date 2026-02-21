from __future__ import annotations

import pickle
from pathlib import Path

from core.graph.build import GraphCache
from core.graph.lite import GraphLite


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
) -> tuple[GraphLite, list[str]]:
    log_lines: list[str] = []
    graph = None
    graph_options = {
        "enable_walking": enable_walking,
        "walk_max_distance_m": walk_max_distance_m,
        "walk_speed_mps": walk_speed_mps,
        "walk_max_neighbors": walk_max_neighbors,
        "symmetric_transfers": symmetric_transfers,
    }

    if cache_path and cache_path.exists() and not rebuild_cache:
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
        cache = GraphCache(
            session=session,
            feed_id=feed_id,
            rebuild=rebuild_cache,
            symmetric_transfers=symmetric_transfers,
            enable_walking=enable_walking,
            walk_max_distance_m=walk_max_distance_m,
            walk_speed_mps=walk_speed_mps,
            walk_max_neighbors=walk_max_neighbors,
        )
        graph = GraphLite.from_graph(cache.graph)
        log_lines.append("Loaded graph from DB cache.")
        if cache_path:
            create_pickle(
                cache_path=cache_path,
                feed_id=feed_id,
                graph_cache_version=graph_cache_version,
                graph_options=graph_options,
                graph=graph,
            )
            log_lines.append(f"Wrote graph pickle: {cache_path}")

    return graph, log_lines
