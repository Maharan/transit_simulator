from __future__ import annotations

from collections.abc import Iterable


def select_context_lines(
    context_lines: Iterable[str],
    *,
    include_candidate_evaluation: bool,
) -> list[str]:
    selected: list[str] = []
    for line in context_lines:
        if line.startswith("Access walk:") or line.startswith("Egress walk:"):
            selected.append(line)
            continue
        if include_candidate_evaluation and line.startswith(
            "Evaluated coordinate candidates:"
        ):
            selected.append(line)
    return selected


def build_output_lines(
    *,
    cache_logs: list[str],
    context_lines: list[str],
    itinerary_lines: list[str],
    include_cache_logs: bool,
    include_candidate_evaluation: bool,
) -> list[str]:
    lines: list[str] = []
    if include_cache_logs:
        lines.extend(cache_logs)
    lines.extend(
        select_context_lines(
            context_lines,
            include_candidate_evaluation=include_candidate_evaluation,
        )
    )
    lines.extend(itinerary_lines)
    return lines
