from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
)
REA_HOSTS = {"realestate.com.au", "www.realestate.com.au"}
STATE_PATTERN = r"NSW|VIC|QLD|SA|WA|TAS|ACT|NT"
BED_LABELS = r"beds?|bedrooms?|br|bdrs?|bdrms?"
BATH_LABELS = r"baths?|bathrooms?|ba"
CAR_LABELS = r"cars?|carparks?|car\s+parks?|parking(?:\s+spaces?)?|garages?"


def _clean_text(value: str) -> str:
    without_scripts = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style\b[^>]*>.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_styles)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _as_positive_number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    number = float(match.group(0))
    return number if number >= 0 else None


def _request_listing(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-AU,en;q=0.9",
        },
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract_meta(html_body: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_body, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _json_documents(html_body: str) -> Iterable[Any]:
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_body,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            yield json.loads(html.unescape(raw).strip())
        except (json.JSONDecodeError, TypeError):
            continue

    for marker in ("__NEXT_DATA__", "__APOLLO_STATE__"):
        match = re.search(
            rf'<script[^>]+id=["\']{marker}["\'][^>]*>(.*?)</script>',
            html_body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        try:
            yield json.loads(html.unescape(match.group(1)).strip())
        except (json.JSONDecodeError, TypeError):
            continue


def _first_json_value(documents: Iterable[Any], keys: set[str]) -> Any:
    normalized_keys = {key.lower() for key in keys}
    for document in documents:
        for node in _walk_json(document):
            for key, value in node.items():
                if str(key).lower() in normalized_keys and value not in (None, "", [], {}):
                    if isinstance(value, (str, int, float)):
                        return value
    return None


def _address_from_json(documents: Iterable[Any]) -> Dict[str, str]:
    for document in documents:
        for node in _walk_json(document):
            lowered = {str(key).lower(): value for key, value in node.items()}
            if not any(key in lowered for key in {"streetaddress", "street_address", "addressline1"}):
                continue
            street = lowered.get("streetaddress") or lowered.get("street_address") or lowered.get("addressline1")
            suburb = lowered.get("addresslocality") or lowered.get("suburb") or lowered.get("locality")
            state = lowered.get("addressregion") or lowered.get("state")
            postcode = lowered.get("postalcode") or lowered.get("postcode")
            if street:
                return {
                    "street": str(street).strip(),
                    "suburb": str(suburb or "").strip(),
                    "state": str(state or "").strip().upper(),
                    "postcode": str(postcode or "").strip(),
                }
    return {}


def _parse_address(text: str) -> Dict[str, str]:
    pattern = re.compile(
        rf"\b((?:Unit\s+)?\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?\s+[^,\n]{{2,80}}),\s*"
        rf"([^,\n]{{2,50}}),?\s+({STATE_PATTERN})\s+(\d{{4}})\b",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return {}
    street, suburb, state, postcode = (part.strip() for part in match.groups())
    return {
        "street": street,
        "suburb": suburb.title(),
        "state": state.upper(),
        "postcode": postcode,
    }


def _compose_address(parts: Dict[str, str]) -> str:
    street = parts.get("street", "").strip()
    suburb = parts.get("suburb", "").strip()
    state = parts.get("state", "").strip().upper()
    postcode = parts.get("postcode", "").strip()
    if not street:
        return ""
    locality = " ".join(part for part in [state, postcode] if part)
    return ", ".join(part for part in [street, suburb, locality] if part)


def _extract_count(text: str, labels: str) -> Optional[float]:
    patterns = [
        rf"\b(?:{labels})\s*[:\-]?\s*(\d+(?:\.\d+)?)\b",
        rf"\b(\d+(?:\.\d+)?)\s*(?:{labels})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _extract_rea_url(text: str) -> str:
    match = re.search(
        r"https?://(?:www\.)?realestate\.com\.au/property-[^\s<>\"']+",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(0).rstrip(".,);]") if match else ""


def _extract_price(text: str) -> tuple[Optional[float], Optional[float]]:
    range_patterns = [
        r"(?:price guide|asking price|offers? over|indicative selling price|estimated selling price)?[^$\d]{0,30}"
        r"\$\s*([\d,]{5,})\s*(?:-|to|\u2013|\u2014)\s*\$?\s*([\d,]{5,})",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            low = float(match.group(1).replace(",", ""))
            high = float(match.group(2).replace(",", ""))
            if 50_000 <= low <= 100_000_000 and 50_000 <= high <= 100_000_000:
                return min(low, high), max(low, high)

    contextual = re.search(
        r"(?:price guide|asking price|offers? over|for sale|sale price|listed price)\s*[:\-]?\s*"
        r"\$\s*([\d,]{5,})",
        text,
        flags=re.IGNORECASE,
    )
    if contextual:
        value = float(contextual.group(1).replace(",", ""))
        if 50_000 <= value <= 100_000_000:
            return value, value

    candidates = [
        float(raw.replace(",", ""))
        for raw in re.findall(r"\$\s*([\d,]{5,})", text)
        if 50_000 <= float(raw.replace(",", "")) <= 100_000_000
    ]
    if candidates:
        return candidates[0], candidates[0]
    return None, None


def _extract_weekly_rent(text: str) -> Optional[float]:
    patterns = [
        r"(?:rent(?:al)?(?: estimate| appraisal)?|leased|tenanted)[^$\d]{0,40}\$\s*([\d,]{3,5})\s*(?:pw|p/w|per week|weekly)",
        r"\$\s*([\d,]{3,5})\s*(?:pw|p/w|per week|weekly)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", ""))
            if 50 <= value <= 20_000:
                return value
    return None


def _property_type(text: str, url: str) -> str:
    url_match = re.search(
        r"/property-(house|apartment|unit|townhouse|villa|land|acreage|studio|duplex|semi-detached)-",
        url,
        flags=re.IGNORECASE,
    )
    if url_match:
        return url_match.group(1).replace("-", " ").title()
    for property_type in ["Townhouse", "Apartment", "Unit", "Villa", "House", "Land", "Studio", "Duplex"]:
        if re.search(rf"\b{property_type}\b", text, flags=re.IGNORECASE):
            return property_type
    return ""


def _tenancy_status(text: str) -> str:
    if re.search(r"\b(?:currently leased|currently tenanted|tenanted|lease in place|leased until)\b", text, re.IGNORECASE):
        return "Tenanted"
    if re.search(r"\b(?:vacant possession|currently vacant|vacant)\b", text, re.IGNORECASE):
        return "Vacant"
    if re.search(r"\bowner[- ]occupied\b", text, re.IGNORECASE):
        return "Owner occupied"
    return "Unknown"


def _merge_field(fields: Dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        fields[key] = value


def parse_listing_content(url: str, content: str, html_body: str = "") -> Dict[str, Any]:
    documents = list(_json_documents(html_body)) if html_body else []
    meta_title = _extract_meta(html_body, "og:title") if html_body else ""
    meta_description = _extract_meta(html_body, "og:description") if html_body else ""
    visible_text = _clean_text(html_body) if html_body else ""
    combined_text = " ".join(part for part in [content, meta_title, meta_description, visible_text] if part)
    combined_text = re.sub(r"\s+", " ", combined_text).strip()

    fields: Dict[str, Any] = {"listing_url": url.strip()}
    address_parts = _address_from_json(documents) or _parse_address(combined_text)
    _merge_field(fields, "property_address", _compose_address(address_parts))
    _merge_field(fields, "suburb", address_parts.get("suburb"))
    _merge_field(fields, "property_state", address_parts.get("state"))
    _merge_field(fields, "postcode", address_parts.get("postcode"))

    property_type = _first_json_value(documents, {"propertyType", "property_type", "dwellingType"})
    _merge_field(fields, "property_type", property_type or _property_type(combined_text, url))

    bedrooms = _first_json_value(documents, {"bedrooms", "bedroomCount", "numberOfBedrooms"})
    bathrooms = _first_json_value(documents, {"bathrooms", "bathroomCount", "numberOfBathrooms"})
    cars = _first_json_value(documents, {"parkingSpaces", "carSpaces", "carspaceCount", "garages"})
    _merge_field(fields, "bedrooms", _as_positive_number(bedrooms) or _extract_count(combined_text, BED_LABELS))
    _merge_field(fields, "bathrooms", _as_positive_number(bathrooms) or _extract_count(combined_text, BATH_LABELS))
    _merge_field(fields, "car_spaces", _as_positive_number(cars) or _extract_count(combined_text, CAR_LABELS))

    land_size = _first_json_value(documents, {"landSize", "landArea", "land_size"})
    if isinstance(land_size, dict):
        land_size = land_size.get("value")
    parsed_land_size = _as_positive_number(land_size)
    if parsed_land_size is None:
        land_match = re.search(r"(?:land size|land area)?\s*[:\-]?\s*([\d,.]+)\s*m(?:2|\u00b2)\b", combined_text, re.IGNORECASE)
        parsed_land_size = _as_positive_number(land_match.group(1)) if land_match else None
    _merge_field(fields, "land_size_sqm", parsed_land_size)

    price_low, price_high = _extract_price(combined_text)
    _merge_field(fields, "listing_price_low", price_low)
    _merge_field(fields, "listing_price_high", price_high)
    if price_low:
        midpoint = (price_low + (price_high or price_low)) / 2
        _merge_field(fields, "price", midpoint)
        _merge_field(fields, "property_value", midpoint)

    _merge_field(fields, "weekly_rent", _extract_weekly_rent(combined_text))
    _merge_field(fields, "tenancy_status", _tenancy_status(combined_text))
    summary = meta_description or content
    if summary:
        summary = re.sub(r"\s+", " ", summary).strip()
        _merge_field(fields, "listing_summary", summary[:700])
    return fields


def import_rea_listing(url: str, pasted_text: str = "") -> Dict[str, Any]:
    pasted_content = pasted_text.strip()
    cleaned_url = url.strip() or _extract_rea_url(pasted_content)
    parsed_url = urlparse(cleaned_url) if cleaned_url else None
    if cleaned_url and (parsed_url is None or parsed_url.scheme not in {"http", "https"} or parsed_url.hostname not in REA_HOSTS):
        return {
            "found": False,
            "blocked": False,
            "message": "Enter a valid realestate.com.au property URL, or leave the URL blank and paste listing text.",
            "fields": {},
        }

    html_body = ""
    fetch_error = ""
    # Pasted page content is faster and more reliable than retrying REA's blocked page request.
    if cleaned_url and not pasted_content:
        try:
            html_body = _request_listing(cleaned_url)
        except Exception as exc:
            fetch_error = str(exc)

    fields = parse_listing_content(cleaned_url, pasted_text, html_body)
    meaningful_fields = {
        key: value
        for key, value in fields.items()
        if key != "listing_url" and value not in (None, "") and not (key == "tenancy_status" and value == "Unknown")
    }
    substantive_keys = {
        "property_address",
        "listing_price_low",
        "listing_price_high",
        "price",
        "bedrooms",
        "bathrooms",
        "car_spaces",
        "land_size_sqm",
        "weekly_rent",
    }
    has_substantive_detail = any(key in fields for key in substantive_keys)
    has_listing_content = bool(html_body or pasted_content)
    if meaningful_fields and has_listing_content and has_substantive_detail:
        source = "REA page and pasted text" if html_body and pasted_content else ("REA page" if html_body else "pasted listing text")
        prefix = "REA blocked automatic page access; " if fetch_error else ""
        return {
            "found": True,
            "blocked": bool(fetch_error),
            "message": f"{prefix}imported {len(meaningful_fields)} editable property detail(s) from {source}.",
            "fields": fields,
        }

    if fetch_error:
        return {
            "found": False,
            "blocked": True,
            "message": (
                "REA blocked automatic access to this listing, so the dashboard received no bedrooms, bathrooms or parking data. "
                "Expand the listing-text section, paste the copied REA page text, then import again."
            ),
            "fields": fields,
        }
    return {
        "found": False,
        "blocked": False,
        "message": "No property details were detected. Paste the listing description or copied page text and try again.",
        "fields": {"listing_url": cleaned_url} if cleaned_url else {},
    }
