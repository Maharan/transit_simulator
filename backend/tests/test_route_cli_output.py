from __future__ import annotations

from core.routing.output import build_output_lines


class _FakeItinerary:
    def lines(self) -> list[str]:
        return ["summary", "timing", "Path:", "Legs:"]


def test_build_output_lines_defaults_to_subset() -> None:
    lines = build_output_lines(
        cache_logs=["Loaded graph from pickle: .cache/graph.pkl"],
        context_lines=[
            "Evaluated coordinate candidates: 3 from x 3 to = 9 pair(s).",
            "Access walk: 166m (237s) to Rodingsmarkt (stop)",
            "Egress walk: 50m (71s) from Strassburger Strasse (stop)",
        ],
        itinerary_lines=_FakeItinerary().lines(),
        include_cache_logs=False,
        include_candidate_evaluation=False,
    )

    assert "Loaded graph from pickle: .cache/graph.pkl" not in lines
    assert "Evaluated coordinate candidates: 3 from x 3 to = 9 pair(s)." not in lines
    assert "Access walk: 166m (237s) to Rodingsmarkt (stop)" in lines
    assert "Egress walk: 50m (71s) from Strassburger Strasse (stop)" in lines
    assert lines[-4:] == ["summary", "timing", "Path:", "Legs:"]


def test_build_output_lines_with_debug_flags() -> None:
    lines = build_output_lines(
        cache_logs=["Loaded graph from pickle: .cache/graph.pkl"],
        context_lines=["Evaluated coordinate candidates: 2 from x 2 to = 4 pair(s)."],
        itinerary_lines=["summary"],
        include_cache_logs=True,
        include_candidate_evaluation=True,
    )

    assert lines == [
        "Loaded graph from pickle: .cache/graph.pkl",
        "Evaluated coordinate candidates: 2 from x 2 to = 4 pair(s).",
        "summary",
    ]
