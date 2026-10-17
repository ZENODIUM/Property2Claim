from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from shapely.geometry import Point, Polygon, shape


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(a))


def property_matches_geometry(latitude: float, longitude: float, geometry: dict[str, Any], radius_km: float = 50) -> tuple[bool, float]:
    point = Point(longitude, latitude)
    geom = shape(geometry)
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom.covers(point), 0.0 if geom.covers(point) else 9999.0
    if geom.geom_type == "Point":
        distance = haversine_km(latitude, longitude, geom.y, geom.x)
        return distance <= radius_km, distance
    return False, 9999.0


def normalized_object_shape(geometry_type: str, geometry: dict[str, Any]):
    if geometry_type == "point":
        return Point(geometry["x"], geometry["y"])
    if geometry_type == "rect":
        x, y = geometry["x"], geometry["y"]
        return Polygon([(x, y), (x + geometry["w"], y), (x + geometry["w"], y + geometry["h"]), (x, y + geometry["h"])])
    return Polygon(geometry["points"])

