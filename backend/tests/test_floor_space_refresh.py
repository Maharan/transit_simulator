from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

import core.built_environment.floor_space as floor_space


class _FakeResult:
    def __init__(self, value: int = 0) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _FakeConnection:
    def __init__(self, inserted_count: int) -> None:
        self.inserted_count = inserted_count
        self.executed: list[tuple[object, object | None]] = []

    def execute(self, statement, params=None):
        self.executed.append((statement, params))
        return _FakeResult(self.inserted_count)


class _FakeBegin:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeConnection:
        return self._connection

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self._connection)


def test_build_floor_space_refresh_count_statement_uses_expression_ctes() -> None:
    statement = floor_space._build_floor_space_refresh_count_statement()
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).lower()

    assert "with building_weights as" in compiled
    assert "insert into built_environment.hh_floor_space_grid" in compiled
    assert "st_pointonsurface" in compiled
    assert "st_transform" in compiled


def test_refresh_hamburg_floor_space_grid_executes_delete_and_refresh_statement(
    monkeypatch,
) -> None:
    connection = _FakeConnection(inserted_count=7)
    engine = _FakeEngine(connection)
    captured: dict[str, object] = {}

    monkeypatch.setattr(floor_space, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        floor_space,
        "_ensure_postgis_and_schema",
        lambda arg: captured.setdefault("ensured", arg),
    )
    monkeypatch.setattr(
        floor_space.HamburgFloorSpaceCell.__table__,
        "create",
        lambda bind, checkfirst=True: captured.setdefault(
            "created",
            (bind, checkfirst),
        ),
    )

    inserted_count = floor_space.refresh_hamburg_floor_space_grid(
        database_url="postgresql://example",
        dataset_release="2023-04-01",
        grid_resolution_m=100,
        total_population=1_850_000.0,
        default_storey_height_m=3.2,
        replace_existing=True,
    )

    assert inserted_count == 7
    assert captured["ensured"] is engine
    assert captured["created"] == (engine, True)
    assert len(connection.executed) == 2
    assert not isinstance(connection.executed[1][0], TextClause)
    assert connection.executed[1][1] == {
        "dataset_release": "2023-04-01",
        "grid_resolution_m": 100,
        "total_population": 1_850_000.0,
        "default_storey_height_m": 3.2,
    }


def test_refresh_hamburg_floor_space_grid_validates_numeric_inputs() -> None:
    try:
        floor_space.refresh_hamburg_floor_space_grid(
            database_url="postgresql://example",
            grid_resolution_m=0,
        )
    except ValueError as exc:
        assert "grid_resolution_m" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected ValueError for non-positive grid resolution.")
