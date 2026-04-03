from __future__ import annotations

from sqlalchemy import Text, func
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.types import UserDefinedType


class PostGISGeometry(UserDefinedType):
    cache_ok = True

    def __init__(self, geometry_type: str, srid: int):
        self.geometry_type = geometry_type
        self.srid = srid

    def get_col_spec(self, **_kwargs: object) -> str:
        return f"geometry({self.geometry_type},{self.srid})"

    def bind_expression(self, bindvalue: ClauseElement) -> ClauseElement:
        return func.ST_GeomFromText(bindvalue, self.srid)

    def column_expression(self, col: ClauseElement) -> ClauseElement:
        return func.ST_AsText(col, type_=Text())

    def copy(self, **_kwargs: object) -> PostGISGeometry:
        return type(self)(self.geometry_type, self.srid)

    @property
    def python_type(self) -> type[str]:
        return str
