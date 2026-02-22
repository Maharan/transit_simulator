from __future__ import annotations

from types import SimpleNamespace

import pytest

import scripts.preload_graph_cache as preload_script


def test_main_preloads_and_prints_logs(monkeypatch, capsys) -> None:
    monkeypatch.setattr(preload_script, "load_dotenv", lambda **_kwargs: None)

    captured: dict[str, object] = {}

    class _FakeService:
        def __init__(self, args) -> None:
            captured["args"] = args

        def preload(self, *, rebuild: bool):
            captured["rebuild"] = rebuild
            return ["Built trip-stop graph from GTFS.", "Wrote graph pickle: x.pkl"]

    monkeypatch.setattr(preload_script, "RouteService", _FakeService)
    monkeypatch.setattr(
        preload_script.route_server,
        "_build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(
                skip_preload=False,
                rebuild_on_start=True,
                graph_method="trip_stop",
                graph_cache=".cache/trip_stop.pkl",
            )
        ),
    )

    preload_script.main(
        ["--graph-method", "trip_stop", "--graph-cache", ".cache/trip_stop.pkl"]
    )
    output = capsys.readouterr().out.strip().splitlines()

    assert captured["rebuild"] is True
    assert output == [
        "Built trip-stop graph from GTFS.",
        "Wrote graph pickle: x.pkl",
    ]


def test_main_rejects_skip_preload(monkeypatch) -> None:
    monkeypatch.setattr(preload_script, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setattr(
        preload_script.route_server,
        "_build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(
                skip_preload=True,
                rebuild_on_start=False,
            )
        ),
    )

    with pytest.raises(SystemExit, match="skip-preload"):
        preload_script.main([])
