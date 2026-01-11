#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["shapely", "requests"]
# ///
"""
EAWS Micro-Region Lookup

Given coordinates, determines the appropriate EAWS avalanche micro-region
using point-in-polygon matching against official EAWS GeoJSON boundaries.

Usage:
    uv run --script region_lookup.py <lat> <lon>

Returns JSON: {"region_code": "AT-07", "micro_region": "AT-07-22"}
Exit code 1 if coordinates are outside known regions.
"""

import json
import sys
from typing import TypedDict

import requests
from shapely.geometry import Point, shape


class RegionResult(TypedDict):
    region_code: str
    micro_region: str


# Parent region rough bounding boxes (lat_min, lat_max, lon_min, lon_max)
PARENT_REGIONS = {
    "AT-02": (46.4, 47.2, 12.7, 15.1),  # Carinthia
    "AT-03": (47.5, 48.1, 14.5, 16.1),  # Lower Austria
    "AT-06": (47.0, 47.8, 13.5, 16.2),  # Styria
    "AT-07": (46.7, 47.6, 10.1, 12.9),  # Tyrol
    "AT-08": (46.8, 47.5, 9.5, 10.5),  # Vorarlberg
}

GEOJSON_URL = (
    "https://regions.avalanches.org/micro-regions/{}_micro-regions.geojson.json"
)


def get_parent_region(lat: float, lon: float) -> str | None:
    """Determine parent region code from coordinates using bounding boxes."""
    for region, (lat_min, lat_max, lon_min, lon_max) in PARENT_REGIONS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return region
    return None


def get_micro_region(lat: float, lon: float, parent: str) -> str | None:
    """Find the micro-region containing the given point."""
    point = Point(lon, lat)  # GeoJSON uses lon, lat order

    try:
        resp = requests.get(GEOJSON_URL.format(parent), timeout=15)
        resp.raise_for_status()
        geojson = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Error fetching region data: {e}", file=sys.stderr)
        return None

    for feature in geojson.get("features", []):
        try:
            polygon = shape(feature["geometry"])
            if polygon.contains(point):
                return feature["properties"]["id"]
        except (KeyError, TypeError, ValueError):
            # Skip malformed features (missing geometry, invalid coordinates, etc.)
            continue

    return None


def lookup_region(lat: float, lon: float) -> RegionResult | None:
    """
    Look up the EAWS region for given coordinates.

    Returns dict with region_code and micro_region, or None if not found.
    """
    parent = get_parent_region(lat, lon)
    if not parent:
        return None

    micro = get_micro_region(lat, lon, parent)
    if not micro:
        return None

    return {"region_code": parent, "micro_region": micro}


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: region_lookup.py <lat> <lon>", file=sys.stderr)
        return 2

    try:
        lat = float(sys.argv[1])
        lon = float(sys.argv[2])
    except ValueError:
        print("Error: lat and lon must be valid numbers", file=sys.stderr)
        return 2

    result = lookup_region(lat, lon)
    if result:
        print(json.dumps(result))
        return 0
    else:
        print(
            f"No matching EAWS region found for coordinates ({lat}, {lon})",
            file=sys.stderr,
        )
        print("Coordinates may be outside Austrian alpine coverage.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
