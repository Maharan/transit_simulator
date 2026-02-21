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
        "enable_walking": True,
        "walk_max_distance_m": 500,
        "walk_speed_mps": 1.4,
        "walk_max_neighbors": 8,
        "symmetric_transfers": False,
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
    }
    assert any("Ignoring graph pickle" in line for line in log_lines)
    assert any("Loaded graph from DB cache." in line for line in log_lines)
    assert any("Wrote graph pickle" in line for line in log_lines)
