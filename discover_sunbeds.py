"""Discover UV tanning / sunbed businesses across London and the South East.

Uses Google's dedicated `tanning_studio` place type plus sunbed/tanning keyword
searches. Results are hard-restricted to the configured map bounds and deduped
by Google Place ID.
"""
from __future__ import annotations

import json
import os
import re
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

# London, Surrey, Berkshire and nearby South-East catchments.
LAT_MIN = float(os.environ.get("LAT_MIN", "50.95"))
LAT_MAX = float(os.environ.get("LAT_MAX", "51.80"))
LNG_MIN = float(os.environ.get("LNG_MIN", "-1.35"))
LNG_MAX = float(os.environ.get("LNG_MAX", "0.55"))

GRID_LAT = float(os.environ.get("GRID_LAT", "0.095"))
GRID_LNG = float(os.environ.get("GRID_LNG", "0.145"))

# Search terms are intentionally redundant. They are only used for discovery;
# the map displays one unified competitor type.
QUERIES = [
    ("tanning studio", True),
    ("sunbed", False),
    ("sunbeds", False),
    ("tanning salon", False),
]

KNOWN_CHAIN_ALIASES = (
    "indigo sun",
    "consol",
    "the tanning shop",
    "tanning shop",
    "the sunshine co",
    "sunshine co",
    "tango'd",
    "tango’d",
    "tangod",
    "kwik tan",
    "kwiktan",
    "lextan",
)

NAME_PATTERN = re.compile(
    r"\bsun\s*beds?\b|\btanning\b|\btans?\b|\btanlines?\b|"
    r"\btango['’]?d\b|\bsolarium\b|\bbronzing\b|\bbronze\b",
    re.IGNORECASE,
)


def frange(start: float, stop: float, step: float) -> list[float]:
    out = []
    value = start
    while value <= stop + 1e-9:
        out.append(round(value, 6))
        value += step
    return out


def viewport_for_point(lat: float, lng: float) -> dict:
    # Slight overlap between cells so businesses near edges are not missed.
    half_lat = GRID_LAT * 0.60
    half_lng = GRID_LNG * 0.60
    return {
        "rectangle": {
            "low": {
                "latitude": max(LAT_MIN, lat - half_lat),
                "longitude": max(LNG_MIN, lng - half_lng),
            },
            "high": {
                "latitude": min(LAT_MAX, lat + half_lat),
                "longitude": min(LNG_MAX, lng + half_lng),
            },
        }
    }


def search_point(query: str, strict_tanning_type: bool, lat: float, lng: float) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": query,
        "regionCode": "GB",
        "locationRestriction": viewport_for_point(lat, lng),
    }

    if strict_tanning_type:
        body["includedType"] = "tanning_studio"
        body["strictTypeFiltering"] = True

    found = []
    page_token = None
    for _ in range(3):
        if page_token:
            body["pageToken"] = page_token
        else:
            body.pop("pageToken", None)

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            print(
                f"API error {resp.status_code} for {query!r} @ {lat},{lng}: "
                f"{resp.text[:250]}"
            )
            break

        data = resp.json()
        found.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)

    return found


def inside_bounds(place: dict) -> bool:
    loc = place.get("location", {})
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    return (
        lat is not None
        and lng is not None
        and LAT_MIN <= lat <= LAT_MAX
        and LNG_MIN <= lng <= LNG_MAX
    )


def looks_relevant(place: dict) -> bool:
    name = place.get("displayName", {}).get("text", "")
    types = set(place.get("types", []))

    # Google's dedicated category is the strongest signal.
    if "tanning_studio" in types:
        return True

    n = name.lower()
    if any(alias in n for alias in KNOWN_CHAIN_ALIASES):
        return True

    # Fallback for businesses Google has not categorised correctly yet.
    return bool(NAME_PATTERN.search(name))


def main() -> None:
    lat_points = frange(LAT_MIN, LAT_MAX, GRID_LAT)
    lng_points = frange(LNG_MIN, LNG_MAX, GRID_LNG)
    total = len(lat_points) * len(lng_points) * len(QUERIES)

    raw: dict[str, dict] = {}
    n = 0

    print(f"Running {total} Google Places searches")
    for lat in lat_points:
        for lng in lng_points:
            for query, strict_type in QUERIES:
                n += 1
                print(f"[{n}/{total}] {query!r} @ {lat},{lng}")
                for place in search_point(query, strict_type, lat, lng):
                    pid = place.get("id")
                    if not pid or not inside_bounds(place):
                        continue
                    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                        continue
                    if not looks_relevant(place):
                        continue
                    raw[pid] = place
                time.sleep(0.08)

    stores = []
    for pid, place in raw.items():
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
            "types": place.get("types", []),
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
