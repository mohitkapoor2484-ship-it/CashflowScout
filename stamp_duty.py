from __future__ import annotations

import re
from typing import Dict


VIC_SOURCE_URL = "https://www.sro.vic.gov.au/about-us/rates-and-statistics/current-rates/land-transfer-duty-non-principal-place-residence-current-rates"
NSW_SOURCE_URL = "https://www.revenue.nsw.gov.au/taxes-duties-levies-royalties/transfer-duty"
QLD_SOURCE_URL = "https://qro.qld.gov.au/duties/transfer-duty/calculate/rates/"
STATE_CODES = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"}


def parse_state(address: str) -> str:
    parts = [part.strip(" ,").upper() for part in re.split(r"\s+", address.replace(",", " ")) if part.strip(" ,")]
    for part in reversed(parts):
        if part in STATE_CODES:
            return part
    return "Unknown"


def calculate_vic_investor_duty(price: float) -> float:
    if price <= 0:
        return 0.0
    if price <= 25_000:
        return price * 0.014
    if price <= 130_000:
        return 350 + (price - 25_000) * 0.024
    if price <= 960_000:
        return 2_870 + (price - 130_000) * 0.06
    if price <= 2_000_000:
        return price * 0.055
    return 110_000 + (price - 2_000_000) * 0.065


def calculate_nsw_general_duty(price: float) -> float:
    if price <= 0:
        return 0.0
    if price <= 17_000:
        return max(price * 0.0125, 20)
    if price <= 37_000:
        return 212 + (price - 17_000) * 0.015
    if price <= 99_000:
        return 512 + (price - 37_000) * 0.0175
    if price <= 372_000:
        return 1_597 + (price - 99_000) * 0.035
    if price <= 1_240_000:
        return 11_152 + (price - 372_000) * 0.045
    if price <= 3_721_000:
        return 50_212 + (price - 1_240_000) * 0.055
    return 186_667 + (price - 3_721_000) * 0.07


def calculate_qld_general_duty(price: float) -> float:
    if price <= 0:
        return 0.0
    if price <= 5_000:
        return 0.0
    if price <= 75_000:
        return ((price - 5_000) / 100) * 1.5
    if price <= 540_000:
        return 1_050 + ((price - 75_000) / 100) * 3.5
    if price <= 1_000_000:
        return 17_325 + ((price - 540_000) / 100) * 4.5
    return 38_025 + ((price - 1_000_000) / 100) * 5.75


def calculate_stamp_duty(price: float, address: str) -> Dict[str, str | float | bool]:
    state = parse_state(address)

    if state == "VIC":
        duty = calculate_vic_investor_duty(price)
        return {
            "supported": True,
            "state": state,
            "duty": duty,
            "source_url": VIC_SOURCE_URL,
            "message": "Auto-calculated using Victoria non-principal-place-of-residence rates updated 11 December 2025.",
        }

    if state == "NSW":
        duty = calculate_nsw_general_duty(price)
        return {
            "supported": True,
            "state": state,
            "duty": duty,
            "source_url": NSW_SOURCE_URL,
            "message": "Auto-calculated using NSW transfer duty rates effective 1 July 2025 to 30 June 2026.",
        }

    if state == "QLD":
        duty = calculate_qld_general_duty(price)
        return {
            "supported": True,
            "state": state,
            "duty": duty,
            "source_url": QLD_SOURCE_URL,
            "message": "Auto-calculated using Queensland transfer duty rates updated 25 June 2026.",
        }

    return {
        "supported": False,
        "state": state,
        "duty": 0.0,
        "source_url": "",
        "message": "Stamp duty auto-calc currently supports VIC, NSW and QLD only. You can still enter it manually.",
    }
