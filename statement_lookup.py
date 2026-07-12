from __future__ import annotations

import html
import ipaddress
import io
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/?q="
MAX_RESULTS = 8
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 25
MAX_LINK_DEPTH = 2
RANGE_SEPARATORS = r"(?:to|-|\u2013|\u2014)"
PRICE_CONTEXT_PATTERNS = [
    re.compile(
        rf"(?:indicative selling price|estimated selling price|statement of information|price range|price guide|agent price guide)"
        rf"[^$0-9]{{0,120}}\$?\s*([0-9][0-9,\s]{{4,}})\s*{RANGE_SEPARATORS}\s*\$?\s*([0-9][0-9,\s]{{4,}})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:single price|indicative selling price|estimated selling price|agent price guide)"
        rf"[^$0-9]{{0,120}}\$?\s*([0-9][0-9,\s]{{4,}})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\$?\s*([0-9][0-9,\s]{{4,}})\s*{RANGE_SEPARATORS}\s*\$?\s*([0-9][0-9,\s]{{4,}})",
        re.IGNORECASE,
    ),
]


def _is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return address.is_global


def _is_rea_property_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme in {"http", "https"}
        and hostname in {"realestate.com.au", "www.realestate.com.au"}
        and "/property-" in parsed.path
    )


def _request(url: str) -> tuple[bytes, str]:
    if not _is_safe_public_url(url):
        raise ValueError("SOI lookup rejected a non-public URL.")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=15) as response:
        content_type = response.headers.get("Content-Type", "")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOCUMENT_BYTES:
            raise ValueError("SOI document is larger than the supported 10 MB limit.")
        payload = response.read(MAX_DOCUMENT_BYTES + 1)
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise ValueError("SOI document is larger than the supported 10 MB limit.")
        return payload, content_type


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def _extract_result_urls(search_html: str) -> List[str]:
    urls: List[str] = []
    for href in re.findall(r'href="([^"]+)"', search_html):
        href = html.unescape(href)
        if "uddg=" in href:
            parsed = urlparse(href)
            target = parse_qs(parsed.query).get("uddg")
            if target:
                urls.append(unquote(target[0]))
        elif href.startswith("http"):
            urls.append(href)

    seen = set()
    filtered: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        if not _is_rea_property_url(url):
            continue
        filtered.append(url)
        if len(filtered) >= MAX_RESULTS:
            break
    return filtered


def _search_candidates(address: str) -> List[str]:
    queries = [
        f"site:realestate.com.au/property- \"{address}\" \"Statement of Information\"",
        f"site:realestate.com.au/property- \"{address}\" \"Agent price guide\"",
        f"site:realestate.com.au/property- \"{address}\"",
    ]
    candidates: List[str] = []
    seen = set()
    for query in queries:
        data, _ = _request(DUCKDUCKGO_HTML_URL + quote_plus(query))
        urls = _extract_result_urls(data.decode("utf-8", errors="ignore"))
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            candidates.append(url)
    return candidates[:MAX_RESULTS]


def _extract_price_number(raw: str) -> Optional[float]:
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) < 5:
        return None
    value = float(digits)
    if value < 50_000 or value > 100_000_000:
        return None
    return value


def _extract_price_range(text: str) -> Optional[Dict[str, float]]:
    normalized = re.sub(r"\s+", " ", text)
    for pattern in PRICE_CONTEXT_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        if len(match.groups()) >= 2:
            low = _extract_price_number(match.group(1))
            high = _extract_price_number(match.group(2))
            if low and high:
                return {"low": min(low, high), "high": max(low, high)}
        else:
            single = _extract_price_number(match.group(1))
            if single:
                return {"low": single, "high": single}
    return None


def _extract_pdf_links(html_body: str, base_url: str) -> List[str]:
    links: List[str] = []
    for href in re.findall(r'href="([^"]+)"', html_body, flags=re.IGNORECASE):
        absolute = urljoin(base_url, html.unescape(href))
        lowered = absolute.lower()
        if _is_safe_public_url(absolute) and (
            ".pdf" in lowered or "statement-of-information" in lowered or "statement_of_information" in lowered
        ):
            links.append(absolute)
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links[:5]


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    if PdfReader is None:
        return ""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        parts.append(page.extract_text() or "")
    return " ".join(parts)


def _normalize_address(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "street": "st",
        "road": "rd",
        "avenue": "ave",
        "parade": "pde",
        "drive": "dr",
        "court": "ct",
        "place": "pl",
        "boulevard": "blvd",
        "highway": "hwy",
    }
    for full, short in replacements.items():
        normalized = re.sub(rf"\b{full}\b", short, normalized)
    normalized = re.sub(r"\bunit\s+", "", normalized)
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _document_matches_address(text: str, expected_address: str) -> bool:
    normalized_text = _normalize_address(text)
    normalized_address = _normalize_address(expected_address)
    if not normalized_address:
        return False
    if normalized_address in normalized_text:
        return True

    address_tokens = normalized_address.split()
    postcode_tokens = [token for token in address_tokens if re.fullmatch(r"\d{4}", token)]
    number_tokens = [token for token in address_tokens if token.isdigit() and token not in postcode_tokens]
    word_tokens = [
        token
        for token in address_tokens
        if not token.isdigit() and token not in {"vic", "st", "rd", "ave", "pde", "dr", "ct", "pl", "blvd", "hwy"}
    ]
    required_tokens = postcode_tokens + number_tokens + word_tokens
    return bool(required_tokens) and all(re.search(rf"\b{re.escape(token)}\b", normalized_text) for token in required_tokens)


def extract_statement_pdf(pdf_bytes: bytes, expected_address: str, source_name: str = "Uploaded SOI PDF") -> Dict[str, Any]:
    if not expected_address.strip():
        return {
            "found": False,
            "message": "Select or enter the property address before importing the SOI PDF.",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }
    if not pdf_bytes or len(pdf_bytes) > MAX_DOCUMENT_BYTES:
        return {
            "found": False,
            "message": "The SOI PDF is empty or larger than the supported 10 MB limit.",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }
    try:
        text = _extract_pdf_text(pdf_bytes)
    except Exception as exc:
        return {
            "found": False,
            "message": f"The SOI PDF could not be read: {exc}",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }
    if not _document_matches_address(text, expected_address):
        return {
            "found": False,
            "message": "The uploaded SOI PDF does not match the selected property address, so no values were changed.",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }
    price_range = _extract_price_range(text)
    if not price_range:
        return {
            "found": False,
            "message": "The address matched, but no indicative selling price was found in the SOI PDF.",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }
    low = float(price_range["low"])
    high = float(price_range["high"])
    return {
        "found": True,
        "message": f"Verified {source_name} for the exact address: ${low:,.0f} to ${high:,.0f}.",
        "low": low,
        "high": high,
        "source_url": "",
    }


def _extract_from_document(
    url: str,
    expected_address: str,
    visited: Optional[set[str]] = None,
    depth: int = 0,
) -> Optional[Dict[str, Any]]:
    if depth > MAX_LINK_DEPTH:
        return None
    visited = visited or set()
    if url in visited:
        return None
    visited.add(url)
    payload, content_type = _request(url)
    lower_url = url.lower()
    if "pdf" in content_type.lower() or lower_url.endswith(".pdf") or ".pdf?" in lower_url:
        text = _extract_pdf_text(payload)
        if not _document_matches_address(text, expected_address):
            return None
        price_range = _extract_price_range(text)
        if price_range:
            return {"source_url": url, **price_range}
        return None

    body = payload.decode("utf-8", errors="ignore")
    direct_text = _clean_text(body)
    if _document_matches_address(direct_text, expected_address):
        price_range = _extract_price_range(direct_text)
        if price_range:
            return {"source_url": url, **price_range}

    for pdf_url in _extract_pdf_links(body, url):
        nested_result = _extract_from_document(pdf_url, expected_address, visited, depth + 1)
        if nested_result:
            return nested_result
    return None


def lookup_statement_of_information(address: str, listing_url: str = "") -> Dict[str, Any]:
    if not address.strip():
        return {
            "found": False,
            "message": "Enter a Victorian property address to look up the Statement of Information price range.",
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }

    # Try the user-supplied listing first. Search engines are a fallback and are
    # commonly blocked even when the listing itself remains publicly accessible.
    candidates: List[str] = []
    if _is_rea_property_url(listing_url):
        candidates.append(listing_url)

    search_error = ""
    try:
        for candidate in _search_candidates(address):
            if candidate not in candidates:
                candidates.append(candidate)
    except Exception as exc:
        search_error = str(exc)

    if not candidates and search_error:
        return {
            "found": False,
            "message": (
                "REA search was not publicly accessible and no valid REA listing link was available. "
                "Existing values were kept; download the SOI PDF from REA and upload it for verified import."
            ),
            "low": 0.0,
            "high": 0.0,
            "source_url": "",
        }

    for candidate in candidates:
        try:
            result = _extract_from_document(candidate, address)
        except Exception:
            continue
        if result:
            low = float(result["low"])
            high = float(result["high"])
            if low == high:
                message = f"Verified REA Statement of Information single price for the exact address: ${low:,.0f}."
            else:
                message = f"Verified REA Statement of Information price range for the exact address: ${low:,.0f} to ${high:,.0f}."
            return {
                "found": True,
                "message": message,
                "low": low,
                "high": high,
                "source_url": str(result["source_url"]),
            }

    return {
        "found": False,
        "message": (
            "No exact-address-verified REA Statement of Information was publicly accessible. "
            "Existing values were kept; download the SOI PDF from REA and upload it for verified import."
        ),
        "low": 0.0,
        "high": 0.0,
        "source_url": "",
    }
