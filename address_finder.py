from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "PropertyCheck/1.0 (address finder)"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
STATE_ABBREVIATIONS = {
    "new south wales": "NSW",
    "victoria": "VIC",
    "queensland": "QLD",
    "south australia": "SA",
    "western australia": "WA",
    "tasmania": "TAS",
    "australian capital territory": "ACT",
    "northern territory": "NT",
}


def _request_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-AU,en;q=0.9",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _state_code(raw_state: str) -> str:
    if not raw_state:
        return ""
    lowered = raw_state.strip().lower()
    return STATE_ABBREVIATIONS.get(lowered, raw_state.upper())


def _formatted_address(address_parts: Dict[str, Any], display_name: str) -> str:
    house_number = str(address_parts.get("house_number", "")).strip()
    road = str(address_parts.get("road", "")).strip()
    street = " ".join(part for part in [house_number, road] if part)
    suburb = (
        str(address_parts.get("suburb", "")).strip()
        or str(address_parts.get("town", "")).strip()
        or str(address_parts.get("city_district", "")).strip()
        or str(address_parts.get("city", "")).strip()
        or str(address_parts.get("village", "")).strip()
    )
    state = _state_code(str(address_parts.get("state", "")).strip())
    postcode = str(address_parts.get("postcode", "")).strip()

    locality = " ".join(part for part in [suburb, state, postcode] if part)
    formatted = ", ".join(part for part in [street, locality] if part)
    return formatted or display_name


def find_addresses(query: str, limit: int = 5) -> List[Dict[str, str]]:
    params = urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "countrycodes": "au",
            "limit": limit,
            "dedupe": 1,
        }
    )
    payload = _request_json(f"{NOMINATIM_SEARCH_URL}?{params}")

    results: List[Dict[str, str]] = []
    for item in payload:
        address_parts = item.get("address", {})
        display_name = str(item.get("display_name", "")).strip()
        formatted_address = _formatted_address(address_parts, display_name)
        if not formatted_address:
            continue
        results.append(
            {
                "formatted_address": formatted_address,
                "display_name": display_name,
            }
        )
    return results
