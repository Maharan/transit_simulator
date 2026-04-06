from __future__ import annotations

from pathlib import Path

import core.graph.caching as caching_module


def test_create_and_get_pickle_round_trip_with_options(tmp_path: Path) -> None:
    cache_path = tmp_path / "graph.pkl"
    graph_obj = {"graph": "payload"}
    options = {"enable_walking": True, "walk_max_distance_m": 400}

    caching_module.create_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options=options,
        graph=graph_obj,
    )
    loaded = caching_module.get_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options=options,
    )
    assert loaded == graph_obj


def test_get_pickle_returns_none_when_options_do_not_match(tmp_path: Path) -> None:
    cache_path = tmp_path / "graph.pkl"
    caching_module.create_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options={"enable_walking": True},
        graph={"graph": "payload"},
    )

    loaded = caching_module.get_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options={"enable_walking": False},
    )
    assert loaded is None


def test_access_or_create_graph_cache_uses_pickle_when_available(tmp_path, monkeypatch):
    cache_path = tmp_path / "graph.pkl"
    expected_graph = {"graph": "from-pickle"}
    options = {
        "graph_method": "multi_edge",
        "enable_walking": True,
        "walk_max_distance_m": 500,
        "walk_speed_mps": 1.4,
        "walk_max_neighbors": 8,
        "symmetric_transfers": False,
        "anytime_default_headway_sec": None,
    }
    caching_module.create_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options=options,
        graph=expected_graph,
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("GraphCache should not be called when pickle matches.")

    monkeypatch.setattr(caching_module, "GraphCache", fail_if_called)

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session=object(),
        feed_id="feed-1",
        cache_path=cache_path,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=False,
        enable_walking=True,
        walk_max_distance_m=500,
        walk_speed_mps=1.4,
        walk_max_neighbors=8,
        graph_method="multi_edge",
    )
    assert graph == expected_graph
    assert any("Loaded graph from pickle" in line for line in log_lines)


def test_access_or_create_graph_cache_rebuilds_on_option_mismatch(
    tmp_path, monkeypatch
) -> None:
    cache_path = tmp_path / "graph.pkl"
    caching_module.create_pickle(
        cache_path=cache_path,
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options={"enable_walking": False},
        graph={"stale": True},
    )

    captured: dict[str, object] = {}

    class FakeGraphCache:
        def __init__(
            self,
            *,
            session,
            feed_id,
            rebuild,
            symmetric_transfers,
            enable_walking,
            walk_max_distance_m,
            walk_speed_mps,
            walk_max_neighbors,
            progress,
            progress_every,
        ):
            captured["init"] = {
                "session": session,
                "feed_id": feed_id,
                "rebuild": rebuild,
                "symmetric_transfers": symmetric_transfers,
                "enable_walking": enable_walking,
                "walk_max_distance_m": walk_max_distance_m,
                "walk_speed_mps": walk_speed_mps,
                "walk_max_neighbors": walk_max_neighbors,
                "progress": progress,
                "progress_every": progress_every,
            }
            self.graph = {"raw": "graph"}

    monkeypatch.setattr(caching_module, "GraphCache", FakeGraphCache)
    monkeypatch.setattr(
        caching_module.GraphLite,
        "from_graph",
        staticmethod(lambda graph: {"lite": graph}),
    )

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session="db-session",
        feed_id="feed-1",
        cache_path=cache_path,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=True,
        enable_walking=True,
        walk_max_distance_m=600,
        walk_speed_mps=1.5,
        walk_max_neighbors=7,
        graph_method="multi_edge",
    )

    assert graph == {"lite": {"raw": "graph"}}
    assert captured["init"] == {
        "session": "db-session",
        "feed_id": "feed-1",
        "rebuild": False,
        "symmetric_transfers": True,
        "enable_walking": True,
        "walk_max_distance_m": 600,
        "walk_speed_mps": 1.5,
        "walk_max_neighbors": 7,
        "progress": False,
        "progress_every": 5000,
    }
    assert any("Ignoring graph pickle" in line for line in log_lines)
    assert any("Loaded graph from DB cache." in line for line in log_lines)
    assert any("Wrote graph pickle" in line for line in log_lines)


def test_access_or_create_graph_cache_uses_in_memory_when_available(monkeypatch):
    in_memory_cache = caching_module.InMemoryGraphCache()
    options = {
        "graph_method": "multi_edge",
        "enable_walking": True,
        "walk_max_distance_m": 500,
        "walk_speed_mps": 1.4,
        "walk_max_neighbors": 8,
        "symmetric_transfers": False,
        "anytime_default_headway_sec": None,
    }
    expected_graph = {"graph": "in-memory"}
    in_memory_cache.set(
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options=options,
        graph=expected_graph,
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError(
            "GraphCache should not be called when memory cache matches."
        )

    monkeypatch.setattr(caching_module, "GraphCache", fail_if_called)

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session=object(),
        feed_id="feed-1",
        cache_path=None,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=False,
        enable_walking=True,
        walk_max_distance_m=500,
        walk_speed_mps=1.4,
        walk_max_neighbors=8,
        graph_method="multi_edge",
        in_memory_cache=in_memory_cache,
    )

    assert graph == expected_graph
    assert any("Loaded graph from in-memory cache." in line for line in log_lines)


def test_access_or_create_graph_cache_stores_graph_in_memory_after_build(
    monkeypatch,
) -> None:
    in_memory_cache = caching_module.InMemoryGraphCache()
    options = {
        "graph_method": "multi_edge",
        "enable_walking": True,
        "walk_max_distance_m": 700,
        "walk_speed_mps": 1.5,
        "walk_max_neighbors": 5,
        "symmetric_transfers": True,
        "anytime_default_headway_sec": None,
    }

    class FakeGraphCache:
        def __init__(self, **_kwargs):
            self.graph = {"raw": "graph"}

    monkeypatch.setattr(caching_module, "GraphCache", FakeGraphCache)
    monkeypatch.setattr(
        caching_module.GraphLite,
        "from_graph",
        staticmethod(lambda graph: {"lite": graph}),
    )

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session="db-session",
        feed_id="feed-1",
        cache_path=None,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=options["symmetric_transfers"],
        enable_walking=options["enable_walking"],
        walk_max_distance_m=options["walk_max_distance_m"],
        walk_speed_mps=options["walk_speed_mps"],
        walk_max_neighbors=options["walk_max_neighbors"],
        graph_method=options["graph_method"],
        in_memory_cache=in_memory_cache,
    )

    cached_graph = in_memory_cache.get(
        feed_id="feed-1",
        graph_cache_version=6,
        graph_options=options,
    )
    assert graph == {"lite": {"raw": "graph"}}
    assert cached_graph == graph
    assert any("Stored graph in in-memory cache." in line for line in log_lines)


def test_access_or_create_graph_cache_builds_trip_stop_graph(monkeypatch) -> None:
    expected_graph = {"graph": "trip-stop"}

    def fail_if_graph_cache_called(*_args, **_kwargs):
        raise AssertionError(
            "GraphCache should not be used for trip_stop graph_method."
        )

    monkeypatch.setattr(caching_module, "GraphCache", fail_if_graph_cache_called)
    monkeypatch.setattr(
        caching_module,
        "build_trip_stop_graph_from_gtfs",
        lambda **_kwargs: expected_graph,
    )

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session="db-session",
        feed_id="feed-1",
        cache_path=None,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=False,
        enable_walking=True,
        walk_max_distance_m=500,
        walk_speed_mps=1.4,
        walk_max_neighbors=8,
        graph_method="trip_stop",
    )

    assert graph == expected_graph
    assert any("Built trip-stop graph from GTFS." in line for line in log_lines)


def test_access_or_create_graph_cache_builds_trip_stop_anytime_graph(
    monkeypatch,
) -> None:
    expected_graph = {"graph": "trip-stop-anytime"}
    captured: dict[str, object] = {}

    def fake_build_trip_stop_anytime_graph_from_gtfs(**kwargs):
        captured["kwargs"] = kwargs
        return expected_graph

    monkeypatch.setattr(
        caching_module,
        "build_trip_stop_anytime_graph_from_gtfs",
        fake_build_trip_stop_anytime_graph_from_gtfs,
    )

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session="db-session",
        feed_id="feed-1",
        cache_path=None,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=False,
        enable_walking=True,
        walk_max_distance_m=500,
        walk_speed_mps=1.4,
        walk_max_neighbors=8,
        graph_method="trip_stop_anytime",
        anytime_default_headway_sec=900,
    )

    assert graph == expected_graph
    assert captured["kwargs"]["default_headway_sec"] == 900
    assert any("Built trip-stop anytime graph from GTFS." in line for line in log_lines)


def test_access_or_create_graph_cache_builds_raptor_timetable(
    monkeypatch,
) -> None:
    expected_graph = {"graph": "raptor"}

    monkeypatch.setattr(
        caching_module,
        "build_raptor_timetable_from_gtfs",
        lambda **_kwargs: expected_graph,
    )

    graph, log_lines = caching_module.access_or_create_graph_cache(
        session="db-session",
        feed_id="feed-1",
        cache_path=None,
        graph_cache_version=6,
        rebuild_cache=False,
        symmetric_transfers=True,
        enable_walking=True,
        walk_max_distance_m=500,
        walk_speed_mps=1.4,
        walk_max_neighbors=8,
        graph_method="raptor",
    )

    assert graph == expected_graph
    assert any("Built RAPTOR timetable from GTFS." in line for line in log_lines)
