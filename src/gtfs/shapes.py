from __future__ import annotations

import pandas as pd


def coerce_shape_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if "shape_pt_lat" in frame.columns:
        frame["shape_pt_lat"] = pd.to_numeric(frame["shape_pt_lat"], errors="coerce")
    if "shape_pt_lon" in frame.columns:
        frame["shape_pt_lon"] = pd.to_numeric(frame["shape_pt_lon"], errors="coerce")
    if "shape_pt_sequence" in frame.columns:
        frame["shape_pt_sequence"] = pd.to_numeric(
            frame["shape_pt_sequence"], errors="coerce"
        ).astype("Int64")
    if "shape_dist_traveled" in frame.columns:
        frame["shape_dist_traveled"] = pd.to_numeric(
            frame["shape_dist_traveled"], errors="coerce"
        )
    return frame
