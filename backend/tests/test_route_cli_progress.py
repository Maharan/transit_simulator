from __future__ import annotations

import scripts.route_cli as route_cli


def test_route_cli_parser_accepts_progress_flags() -> None:
    args = route_cli._build_parser().parse_args(
        [
            "--from-stop-id",
            "A",
            "--to-stop-id",
            "B",
            "--progress",
            "--progress-every",
            "7",
        ]
    )

    assert args.progress is True
    assert args.progress_every == 7
    assert args.max_wait_sec == 1200
    assert args.max_rounds == 8
    assert args.max_major_transfers == 4


def test_route_cli_parser_defaults_to_gtfs_transfer_times_without_extra_penalties() -> (
    None
):
    args = route_cli._build_parser().parse_args(
        [
            "--from-stop-id",
            "A",
            "--to-stop-id",
            "B",
        ]
    )

    assert args.transfer_penalty == 0
    assert args.route_change_penalty == 0
    assert args.max_major_transfers == 4
