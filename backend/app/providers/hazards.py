from __future__ import annotations

from datetime import datetime, timezone
import csv
from io import StringIO
from typing import Any

import httpx


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_noaa_feature(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    return {
        "provider": "NOAA",
        "provider_event_id": props.get("id") or feature.get("id"),
        "event_type": props.get("event", "weather_alert"),
        "title": props.get("headline") or props.get("event", "NOAA alert"),
        "severity": (props.get("severity") or "unknown").lower(),
        "geometry": feature.get("geometry"),
        "valid_at": parse_datetime(props.get("effective")),
        "source_mode": "live",
    }


def parse_eonet_event(event: dict[str, Any]) -> dict[str, Any]:
    latest = (event.get("geometry") or [{}])[-1]
    categories = event.get("categories") or [{}]
    return {
        "provider": "NASA_EONET",
        "provider_event_id": event.get("id"),
        "event_type": categories[0].get("title", "natural_event"),
        "title": event.get("title", "NASA EONET event"),
        "severity": "observed",
        "geometry": {"type": latest.get("type", "Point"), "coordinates": latest.get("coordinates", [])},
        "valid_at": parse_datetime(latest.get("date")),
        "source_mode": "live",
    }


def fetch_live_hazards(user_agent: str, firms_map_key: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    headers = {"User-Agent": user_agent, "Accept": "application/geo+json, application/json"}
    try:
        response = httpx.get("https://api.weather.gov/alerts/active?status=actual&message_type=alert", headers=headers, timeout=8)
        response.raise_for_status()
        events.extend(parse_noaa_feature(f) for f in response.json().get("features", [])[:25] if f.get("geometry"))
    except httpx.HTTPError as exc:
        errors.append(f"NOAA unavailable: {type(exc).__name__}")
    try:
        response = httpx.get("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=25", headers=headers, timeout=8)
        response.raise_for_status()
        events.extend(parse_eonet_event(e) for e in response.json().get("events", []) if e.get("geometry"))
    except httpx.HTTPError as exc:
        errors.append(f"NASA EONET unavailable: {type(exc).__name__}")
    if firms_map_key:
        try:
            # FIRMS uses a separate free MAP_KEY; a general NASA API key is not interchangeable.
            area = "-160.5,17.5,-63.8,50"
            response = httpx.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{firms_map_key}/VIIRS_NOAA20_NRT/{area}/2", headers=headers, timeout=12)
            response.raise_for_status()
            rows = list(csv.DictReader(StringIO(response.text)))[:100]
            for row in rows:
                latitude, longitude = float(row["latitude"]), float(row["longitude"])
                acquisition = f"{row['acq_date']}T{row.get('acq_time', '0000').zfill(4)[:2]}:{row.get('acq_time', '0000').zfill(4)[2:]}:00Z"
                frp = float(row.get("frp") or 0)
                events.append({
                    "provider": "NASA_FIRMS",
                    "provider_event_id": f"{row.get('satellite','VIIRS')}-{row['acq_date']}-{row.get('acq_time')}-{latitude:.4f}-{longitude:.4f}",
                    "event_type": "active_fire_detection",
                    "title": f"VIIRS active fire detection · FRP {frp:.1f} MW",
                    "severity": "severe" if frp >= 50 else "moderate" if frp >= 10 else "observed",
                    "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                    "valid_at": parse_datetime(acquisition),
                    "source_mode": "live",
                })
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            errors.append(f"NASA FIRMS unavailable: {type(exc).__name__}")
    return events, errors
