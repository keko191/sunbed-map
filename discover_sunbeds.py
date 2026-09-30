"""Discover UV tanning / sunbed businesses across London and the South East.

Searches several consumer terms, deduplicates by Google Place ID, and writes one
unified location list. Search-term differences are not shown on the map.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

API_KEY = os.environ["GOOGLE_API_KEY"]
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "stores.json")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.websiteUri,"
    "places.googleMapsUri,"
    "places.businessStatus,"
    "places.types,"
    "nextPageToken"
)

# London, Surrey, Berkshire and surrounding South-East catchments.
LAT_MIN = float(os.environ.get("LAT_MIN", "50.95"))
LAT_MAX = float(os.environ.get("LAT_MAX", "51.80"))
LNG_MIN = float(os.environ.get("LNG_MIN", "-1.35"))
LNG_MAX = float(os.environ.get("LNG_MAX", "0.55"))

GRID_LAT = float(os.environ.get("GRID_LAT", "0.095"))
GRID_LNG = float(os.environ.get("GRID_LNG", "0.145"))
SEARCH_RADIUS_M = int(os.environ.get("SEARCH_RADIUS_M", "8500"))

QUERIES = ["sunbed", "sunbeds", "tanning salon", "tanning"]


def frange(start: float, stop: float, step: float) -> list[float]:
    out = []
    value = start
    while value <= stop + 1e-9:
        out.append(round(value, 6))
        value += step
    return out


def search_point(query: str, lat: float, lng: float) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": query,
        "regionCode": "GB",
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": SEARCH_RADIUS_M,
            }
        },
    }

    found = []
    page_token = None
    for _ in range(3):
        if page_token:
            body["pageToken"] = page_token
        else:
            body.pop("pageToken", None)

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            print(f"API error {resp.status_code} for {query!r} @ {lat},{lng}: {resp.text[:250]}")
            break

        data = resp.json()
        found.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)

    return found


def looks_relevant(place: dict, matched_queries: set[str]) -> bool:
    """Keep broad coverage while removing obvious non-tanning false positives."""
    name = place.get("displayName", {}).get("text", "").lower()
    types = set(place.get("types", []))

    if "tanning_salon" in types:
        return True

    if {"sunbed", "sunbeds"} & matched_queries:
        return True

    keywords = ("tan", "tanning", "sunbed", "sun bed", "solarium")
    return any(k in name for k in keywords)


def main() -> None:
    lat_points = frange(LAT_MIN, LAT_MAX, GRID_LAT)
    lng_points = frange(LNG_MIN, LNG_MAX, GRID_LNG)
    total = len(lat_points) * len(lng_points) * len(QUERIES)

    raw: dict[str, dict] = {}
    matches: dict[str, set[str]] = {}
    n = 0

    print(f"Running {total} Google Places searches")
    for lat in lat_points:
        for lng in lng_points:
            for query in QUERIES:
                n += 1
                print(f"[{n}/{total}] {query!r} @ {lat},{lng}")
                for place in search_point(query, lat, lng):
                    pid = place.get("id")
                    loc = place.get("location", {})
                    if not pid or loc.get("latitude") is None or loc.get("longitude") is None:
                        continue
                    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                        continue
                    raw[pid] = place
                    matches.setdefault(pid, set()).add(query)
                time.sleep(0.10)

    stores = []
    for pid, place in raw.items():
        qs = matches.get(pid, set())
        if not looks_relevant(place, qs):
            continue
        loc = place.get("location", {})
        stores.append({
            "place_id": pid,
            "name": place.get("displayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
            "website_uri": place.get("websiteUri"),
            "google_maps_uri": place.get("googleMapsUri"),
            "business_status": place.get("businessStatus"),
        })

    stores.sort(key=lambda s: ((s.get("name") or "").lower(), (s.get("address") or "").lower()))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_bounds": {
            "lat_min": LAT_MIN,
            "lat_max": LAT_MAX,
            "lng_min": LNG_MIN,
            "lng_max": LNG_MAX,
        },
        "stores": stores,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Done: {len(stores)} relevant locations -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
