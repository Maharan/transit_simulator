from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.gtfs.models import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = {"schema": "gtfs"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    from_stop_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    to_stop_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    weight_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    route_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    service_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    dep_time: Mapped[str | None] = mapped_column(String, nullable=True)
    arr_time: Mapped[str | None] = mapped_column(String, nullable=True)
    transfer_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)


Index("ix_graph_edges_feed_from", GraphEdge.feed_id, GraphEdge.from_stop_id)
Index("ix_graph_edges_feed_to", GraphEdge.feed_id, GraphEdge.to_stop_id)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("feed_id", "stop_id", name="uq_graph_node_feed_stop_id"),
        {"schema": "gtfs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    stop_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    stop_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_lon: Mapped[float | None] = mapped_column(Float, nullable=True)


Index("ix_graph_nodes_feed_stop", GraphNode.feed_id, GraphNode.stop_id)
