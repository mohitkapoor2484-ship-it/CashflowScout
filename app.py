from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
import importlib
import re
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from address_finder import find_addresses
from listing_import import import_rea_listing
import pdf_report
from stamp_duty import calculate_stamp_duty
from statement_lookup import extract_statement_pdf, lookup_statement_of_information
from storage import (
    delete_property,
    init_db,
    list_properties,
    load_property,
    load_setting,
    save_property,
    save_setting,
    toggle_property_favorite,
)

WEEKS_PER_YEAR = 52
QUARTERS_PER_YEAR = 4
MONTHS_PER_YEAR = 12
STATE_CODES = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"}
EDITOR_KEYS = ["facts_editor", "purchase_editor", "rent_rates_editor", "finance_editor", "tax_editor"]
DIRECT_WIDGET_KEYS = {
    "vacancy_risk",
    "liquidity_risk",
    "finance_difficulty",
    "body_corporate_risk",
    "regional_risk",
    "capital_growth_potential",
    "tenant_demand",
    "special_levy_risk",
}
LVR_COMPARISON_LEVELS = [95, 90, 85, 80, 75, 70]
LMI_SOURCE_URL = "https://www.helia.com.au/the-hub/calculators-estimators/lmi-fee-estimator"
PORTFOLIO_DEFAULTS: Dict[str, Any] = {
    "portfolio_deposit_mode": "Percent",
    "portfolio_deposit_value": 20.0,
    "portfolio_loan_rate": 6.1,
    "portfolio_loan_years": 30.0,
    "portfolio_repayment_type": "P+I",
    "portfolio_solicitor_charge": 1800.0,
    "portfolio_inspection_costs": 650.0,
    "portfolio_annual_borrowing_costs": 395.0,
    "portfolio_building_insurance_annual": 1000.0,
    "portfolio_landlord_insurance_annual": 450.0,
    "portfolio_property_manager_rate": 7.0,
    "portfolio_vacancy_allowance_pct": 2.0,
    "portfolio_maintenance_allowance_pct": 1.0,
    "portfolio_income_tax_rate": 37.0,
}
PORTFOLIO_NUMERIC_KEYS = [
    "portfolio_deposit_value",
    "portfolio_loan_rate",
    "portfolio_loan_years",
    "portfolio_solicitor_charge",
    "portfolio_inspection_costs",
    "portfolio_annual_borrowing_costs",
    "portfolio_building_insurance_annual",
    "portfolio_landlord_insurance_annual",
    "portfolio_property_manager_rate",
    "portfolio_vacancy_allowance_pct",
    "portfolio_maintenance_allowance_pct",
    "portfolio_income_tax_rate",
]
PORTFOLIO_INPUT_KEY_MAP = {
    "portfolio_deposit_mode": "portfolio_deposit_mode_input",
    "portfolio_deposit_value": "portfolio_deposit_value_input",
    "portfolio_loan_rate": "portfolio_loan_rate_input",
    "portfolio_loan_years": "portfolio_loan_years_input",
    "portfolio_repayment_type": "portfolio_repayment_type_input",
    "portfolio_solicitor_charge": "portfolio_solicitor_charge_input",
    "portfolio_inspection_costs": "portfolio_inspection_costs_input",
    "portfolio_annual_borrowing_costs": "portfolio_annual_borrowing_costs_input",
    "portfolio_building_insurance_annual": "portfolio_building_insurance_annual_input",
    "portfolio_landlord_insurance_annual": "portfolio_landlord_insurance_annual_input",
    "portfolio_property_manager_rate": "portfolio_property_manager_rate_input",
    "portfolio_vacancy_allowance_pct": "portfolio_vacancy_allowance_pct_input",
    "portfolio_maintenance_allowance_pct": "portfolio_maintenance_allowance_pct_input",
    "portfolio_income_tax_rate": "portfolio_income_tax_rate_input",
}
PORTFOLIO_PM_USAGE_SETTING_KEY = "portfolio_property_manager_usage"

DEFAULTS: Dict[str, Any] = {
    "listing_url": "",
    "listing_text": "",
    "listing_price_low": None,
    "listing_price_high": None,
    "listing_summary": "",
    "property_address": "",
    "suburb": "",
    "property_state": "",
    "postcode": "",
    "property_type": "",
    "is_sold": False,
    "bedrooms": None,
    "bathrooms": None,
    "car_spaces": None,
    "land_size_sqm": None,
    "tenancy_status": "Unknown",
    "price": None,
    "deposit_input_mode": "Percent",
    "deposit_input_value": 20.0,
    "deposit_pct": 20.0,
    "stamp_duty": None,
    "stamp_duty_source_url": "",
    "stamp_duty_message": "",
    "solicitor_charge": None,
    "inspection_costs": None,
    "statement_price_low": None,
    "statement_price_high": None,
    "statement_source_url": "",
    "statement_lookup_message": "",
    "property_value": None,
    "weekly_rent": None,
    "vacancy_allowance_pct": 2.0,
    "maintenance_allowance_pct": 1.0,
    "rent_growth_pct": 3.0,
    "expense_inflation_pct": 3.0,
    "property_growth_pct": 3.0,
    "council_quarterly": None,
    "water_quarterly": None,
    "strata_quarterly": None,
    "building_insurance_annual": None,
    "landlord_insurance_annual": None,
    "deposit_source": "Cash",
    "mortgage_1_rate": None,
    "mortgage_1_amount": None,
    "mortgage_1_years": None,
    "mortgage_1_repayment_type": "P+I",
    "mortgage_2_rate": None,
    "mortgage_2_amount": None,
    "mortgage_2_years": None,
    "mortgage_2_repayment_type": "P+I",
    "mortgage_3_rate": None,
    "mortgage_3_amount": None,
    "mortgage_3_years": None,
    "mortgage_3_repayment_type": "P+I",
    "annual_borrowing_costs": None,
    "property_manager_rate": None,
    "depreciation_estimate": None,
    "income": None,
    "income_tax_rate": None,
    "vacancy_risk": 5,
    "liquidity_risk": 5,
    "finance_difficulty": 5,
    "body_corporate_risk": 5,
    "regional_risk": 5,
    "capital_growth_potential": 5,
    "tenant_demand": 5,
    "special_levy_risk": 5,
}


@dataclass
class Loan:
    name: str
    rate_pct: float
    amount: float
    term_years: float
    repayment_type: str

    @property
    def annual_interest(self) -> float:
        return max(self.amount, 0.0) * max(self.rate_pct, 0.0) / 100

    @property
    def effective_term_years(self) -> float:
        return max(self.term_years, 0.0) or 30.0

    @property
    def annual_repayment(self) -> float:
        amount = max(self.amount, 0.0)
        rate_pct = max(self.rate_pct, 0.0)
        if str(self.repayment_type) == "I only":
            return self.annual_interest

        term_years = self.effective_term_years
        if amount <= 0:
            return 0.0
        if rate_pct <= 0:
            return amount / term_years

        monthly_rate = rate_pct / 100 / MONTHS_PER_YEAR
        total_payments = int(round(term_years * MONTHS_PER_YEAR))
        if total_payments <= 0:
            return self.annual_interest
        monthly_repayment = amount * monthly_rate / (1 - (1 + monthly_rate) ** (-total_payments))
        return monthly_repayment * MONTHS_PER_YEAR


def ensure_state() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("deposit_input_mode_input", st.session_state.deposit_input_mode)
    st.session_state.setdefault("deposit_source_input", st.session_state.deposit_source)
    st.session_state.setdefault("mortgage_1_repayment_type_input", st.session_state.mortgage_1_repayment_type)
    st.session_state.setdefault("mortgage_2_repayment_type_input", st.session_state.mortgage_2_repayment_type)
    st.session_state.setdefault("mortgage_3_repayment_type_input", st.session_state.mortgage_3_repayment_type)
    st.session_state.setdefault("save_name", "")
    st.session_state.setdefault("save_name_input", st.session_state.save_name)
    st.session_state.setdefault("loaded_property_name", "")
    st.session_state.setdefault("last_soi_lookup_address", "")
    st.session_state.setdefault("address_search_query", "")
    st.session_state.setdefault("address_search_results", [])
    st.session_state.setdefault("selected_address", "")
    st.session_state.setdefault("address_finder_message", "")
    st.session_state.setdefault("listing_url_input", st.session_state.listing_url)
    st.session_state.setdefault("listing_text_input", st.session_state.listing_text)
    st.session_state.setdefault("listing_import_message", "")
    st.session_state.setdefault("saved_property_filter", "")
    st.session_state.setdefault("has_calculated", False)
    st.session_state.setdefault("calculated_payload", {})
    st.session_state.setdefault("stamp_duty_auto_signature", "")
    st.session_state.setdefault("active_page", "Property workspace")
    st.session_state.setdefault("_pending_active_page", None)
    st.session_state.setdefault("portfolio_settings_saved_notice", False)
    st.session_state.setdefault("portfolio_widget_nonce", 0)
    st.session_state.setdefault("portfolio_property_manager_usage", {})
    st.session_state.setdefault("portfolio_screener_row_keys", [])
    st.session_state.setdefault("portfolio_screener_editor_applied_signature", "")
    st.session_state.setdefault("_portfolio_pm_usage_loaded", False)
    for key, value in PORTFOLIO_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        st.session_state.setdefault(input_key, st.session_state[key])
    sync_portfolio_transient_inputs()
    saved_portfolio_settings = load_setting("portfolio_screener_inputs", {})
    should_restore_portfolio_settings = (
        not st.session_state.get("_portfolio_settings_loaded", False)
        or portfolio_settings_are_blank()
        or portfolio_widget_values_are_blank()
    )
    if should_restore_portfolio_settings and isinstance(saved_portfolio_settings, dict):
        for key, default_value in PORTFOLIO_DEFAULTS.items():
            if key in saved_portfolio_settings:
                st.session_state[key] = saved_portfolio_settings.get(key, default_value)
        hydrate_portfolio_transient_inputs()
        refresh_portfolio_widget_state()
    else:
        ensure_portfolio_widget_state()
    st.session_state["_portfolio_settings_loaded"] = True
    saved_portfolio_pm_usage = load_setting(PORTFOLIO_PM_USAGE_SETTING_KEY, {})
    should_restore_portfolio_pm_usage = (
        not st.session_state.get("_portfolio_pm_usage_loaded", False)
        or not st.session_state.get("portfolio_property_manager_usage")
    )
    if should_restore_portfolio_pm_usage and isinstance(saved_portfolio_pm_usage, dict):
        st.session_state["portfolio_property_manager_usage"] = {
            str(name): as_bool(value, default=True) for name, value in saved_portfolio_pm_usage.items()
        }
    st.session_state["_portfolio_pm_usage_loaded"] = True
    if (
        not st.session_state.stamp_duty_auto_signature
        and st.session_state.stamp_duty_source_url
        and st.session_state.property_address
        and as_number(st.session_state.price) > 0
    ):
        st.session_state.stamp_duty_auto_signature = stamp_duty_signature(
            as_number(st.session_state.price), str(st.session_state.property_address)
        )


def clear_editor_drafts() -> None:
    for editor_key in EDITOR_KEYS:
        st.session_state.pop(editor_key, None)
        st.session_state.pop(f"{editor_key}_draft", None)


def clear_editor_draft(editor_key: str) -> None:
    st.session_state.pop(editor_key, None)
    st.session_state.pop(f"{editor_key}_draft", None)


def reset_to_defaults() -> None:
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    st.session_state.deposit_input_mode_input = st.session_state.deposit_input_mode
    st.session_state.deposit_source_input = st.session_state.deposit_source
    st.session_state.mortgage_1_repayment_type_input = st.session_state.mortgage_1_repayment_type
    st.session_state.mortgage_2_repayment_type_input = st.session_state.mortgage_2_repayment_type
    st.session_state.mortgage_3_repayment_type_input = st.session_state.mortgage_3_repayment_type
    st.session_state.listing_url_input = st.session_state.listing_url
    st.session_state.listing_text_input = st.session_state.listing_text
    st.session_state.listing_import_message = ""
    st.session_state.save_name = ""
    st.session_state.save_name_input = ""
    st.session_state.loaded_property_name = ""
    st.session_state.last_soi_lookup_address = ""
    st.session_state.stamp_duty_auto_signature = ""
    st.session_state.has_calculated = False
    st.session_state.calculated_payload = {}
    clear_editor_drafts()


def queue_payload_apply(
    payload: Dict[str, Any],
    property_name: str,
    preserve_calculation: bool = False,
) -> None:
    st.session_state["_pending_payload_apply"] = {
        "payload": dict(payload),
        "property_name": property_name,
        "preserve_calculation": preserve_calculation,
    }


def apply_payload_to_state(
    payload: Dict[str, Any],
    property_name: str,
    preserve_calculation: bool = False,
) -> None:
    for key, default_value in DEFAULTS.items():
        st.session_state[key] = payload.get(key, default_value)
    if "deposit_input_value" not in payload:
        st.session_state.deposit_input_value = payload.get("deposit_pct", DEFAULTS["deposit_input_value"])
    if "deposit_input_mode" not in payload:
        st.session_state.deposit_input_mode = "Percent"
    st.session_state.deposit_input_mode_input = st.session_state.deposit_input_mode
    st.session_state.deposit_source_input = st.session_state.deposit_source
    st.session_state.mortgage_1_repayment_type_input = st.session_state.mortgage_1_repayment_type
    st.session_state.mortgage_2_repayment_type_input = st.session_state.mortgage_2_repayment_type
    st.session_state.mortgage_3_repayment_type_input = st.session_state.mortgage_3_repayment_type
    st.session_state.listing_url_input = st.session_state.listing_url
    st.session_state.listing_text_input = st.session_state.listing_text
    st.session_state.listing_import_message = ""
    st.session_state.save_name = property_name
    st.session_state.loaded_property_name = property_name
    st.session_state.last_soi_lookup_address = str(st.session_state.property_address).strip()
    st.session_state.stamp_duty_auto_signature = ""
    if not preserve_calculation:
        st.session_state.has_calculated = False
        st.session_state.calculated_payload = {}
    clear_editor_drafts()


def consume_pending_payload_apply() -> None:
    pending = st.session_state.pop("_pending_payload_apply", None)
    if not pending:
        return
    apply_payload_to_state(
        pending["payload"],
        str(pending["property_name"]),
        preserve_calculation=bool(pending.get("preserve_calculation", False)),
    )


def queue_active_page(page_name: str) -> None:
    st.session_state["_pending_active_page"] = page_name


def consume_pending_active_page() -> None:
    pending_page = st.session_state.get("_pending_active_page")
    if pending_page:
        st.session_state["active_page"] = str(pending_page)
        st.session_state["_pending_active_page"] = None


def delete_loaded_property_and_reset() -> None:
    loaded_name = str(st.session_state.get("loaded_property_name", "")).strip()
    if loaded_name:
        delete_property(loaded_name)
    reset_to_defaults()


def sync_transient_inputs() -> None:
    st.session_state.deposit_input_mode = str(
        st.session_state.get("deposit_input_mode_input", st.session_state.get("deposit_input_mode", "Percent"))
    )
    st.session_state.deposit_source = str(
        st.session_state.get("deposit_source_input", st.session_state.get("deposit_source", "Cash"))
    )
    st.session_state.listing_url = str(
        st.session_state.get("listing_url_input", st.session_state.get("listing_url", ""))
    ).strip()
    st.session_state.listing_text = str(
        st.session_state.get("listing_text_input", st.session_state.get("listing_text", ""))
    )
    for mortgage_number in (1, 2, 3):
        key = f"mortgage_{mortgage_number}_repayment_type"
        st.session_state[key] = str(
            st.session_state.get(f"{key}_input", st.session_state.get(key, "P+I"))
        )


def sync_portfolio_transient_inputs() -> None:
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        if input_key in st.session_state:
            st.session_state[key] = st.session_state[input_key]


def hydrate_portfolio_transient_inputs() -> None:
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        st.session_state[input_key] = st.session_state.get(key, PORTFOLIO_DEFAULTS[key])


def portfolio_widget_state_key(key: str) -> str:
    nonce = int(st.session_state.get("portfolio_widget_nonce", 0))
    return f"{PORTFOLIO_INPUT_KEY_MAP[key]}__{nonce}"


def ensure_portfolio_widget_state() -> None:
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        widget_key = portfolio_widget_state_key(key)
        st.session_state.setdefault(widget_key, st.session_state.get(input_key, st.session_state.get(key, PORTFOLIO_DEFAULTS[key])))


def refresh_portfolio_widget_state() -> None:
    st.session_state["portfolio_widget_nonce"] = int(st.session_state.get("portfolio_widget_nonce", 0)) + 1
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        widget_key = portfolio_widget_state_key(key)
        st.session_state[widget_key] = st.session_state.get(input_key, st.session_state.get(key, PORTFOLIO_DEFAULTS[key]))


def sync_portfolio_widgets_to_inputs() -> None:
    for key, input_key in PORTFOLIO_INPUT_KEY_MAP.items():
        widget_key = portfolio_widget_state_key(key)
        if widget_key in st.session_state:
            value = st.session_state[widget_key]
            st.session_state[input_key] = value
            st.session_state[key] = value


def portfolio_input_value(key: str) -> Any:
    input_key = PORTFOLIO_INPUT_KEY_MAP[key]
    return st.session_state.get(input_key, st.session_state.get(key, PORTFOLIO_DEFAULTS[key]))


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "on"}:
            return True
        if lowered in {"false", "no", "n", "0", "off"}:
            return False
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return default


def apply_portfolio_screener_manager_rate_edits() -> None:
    editor_state = st.session_state.get("portfolio_screener_editor", {})
    if not isinstance(editor_state, dict):
        return

    edited_rows = editor_state.get("edited_rows", {})
    signature = repr(edited_rows)
    if signature == str(st.session_state.get("portfolio_screener_editor_applied_signature", "")):
        return

    row_keys = st.session_state.get("portfolio_screener_row_keys", [])
    if not isinstance(edited_rows, dict) or not isinstance(row_keys, list):
        st.session_state["portfolio_screener_editor_applied_signature"] = signature
        return

    usage_map = dict(st.session_state.get("portfolio_property_manager_usage", {}))
    has_changes = False
    for row_index, changes in edited_rows.items():
        if not isinstance(changes, dict) or "Use PM rate" not in changes:
            continue
        try:
            row_position = int(row_index)
        except (TypeError, ValueError):
            continue
        if 0 <= row_position < len(row_keys):
            usage_map[str(row_keys[row_position])] = as_bool(changes["Use PM rate"], default=True)
            has_changes = True

    st.session_state["portfolio_property_manager_usage"] = usage_map
    st.session_state["portfolio_screener_editor_applied_signature"] = signature
    if has_changes:
        save_setting(PORTFOLIO_PM_USAGE_SETTING_KEY, usage_map)


def current_payload() -> Dict[str, Any]:
    sync_transient_inputs()
    return {key: st.session_state[key] for key in DEFAULTS}


def as_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def portfolio_settings_are_blank() -> bool:
    return all(as_number(st.session_state.get(key)) <= 0 for key in PORTFOLIO_NUMERIC_KEYS)


def portfolio_widget_values_are_blank() -> bool:
    values: List[float] = []
    for key in PORTFOLIO_NUMERIC_KEYS:
        widget_key = portfolio_widget_state_key(key)
        input_key = PORTFOLIO_INPUT_KEY_MAP[key]
        if widget_key in st.session_state:
            values.append(as_number(st.session_state.get(widget_key)))
        else:
            values.append(as_number(st.session_state.get(input_key)))
    return all(value <= 0 for value in values)


def currency(value: Any) -> str:
    if value in (None, "") or pd.isna(value):
        return ""
    amount = as_number(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def pct(value: float) -> str:
    return f"{value:.2f}%"


def resolve_deposit_values(price: float, deposit_input_mode: str, deposit_input_value: Any) -> tuple[float, float]:
    numeric_value = max(as_number(deposit_input_value), 0.0)
    if str(deposit_input_mode) == "Dollar":
        deposit_amount = numeric_value
        deposit_pct = safe_divide(deposit_amount, price) * 100 if price > 0 else 0.0
    else:
        deposit_pct = numeric_value
        deposit_amount = price * deposit_pct / 100
    return deposit_pct, deposit_amount


def sync_deposit_input_mode() -> None:
    old_mode = str(st.session_state.get("deposit_input_mode", "Percent"))
    new_mode = str(st.session_state.get("deposit_input_mode_input", "Percent"))
    if old_mode == new_mode:
        return

    price = as_number(st.session_state.get("price"))
    source_value = st.session_state.get("deposit_input_value", st.session_state.get("deposit_pct", 0.0))
    deposit_pct, deposit_amount = resolve_deposit_values(price, old_mode, source_value)

    st.session_state.deposit_input_value = deposit_amount if new_mode == "Dollar" and price > 0 else (
        deposit_pct if new_mode == "Percent" else as_number(source_value)
    )
    if new_mode == "Dollar" and price <= 0:
        st.session_state.deposit_input_value = as_number(source_value)
    st.session_state.deposit_input_mode = new_mode
    st.session_state.deposit_pct = deposit_pct
    clear_editor_draft("purchase_editor")


def parse_state_from_address(address: str) -> str:
    parts = [part.strip(" ,").upper() for part in re.split(r"\s+", address.replace(",", " ")) if part.strip(" ,")]
    for part in reversed(parts):
        if part in STATE_CODES:
            return part
    return "Unknown"


def should_resolve_address(address: str) -> bool:
    cleaned = address.strip().rstrip(",")
    if not cleaned:
        return False
    has_state = parse_state_from_address(cleaned) in STATE_CODES
    has_postcode = bool(re.search(r"\b\d{4}\b", cleaned))
    return not (has_state and has_postcode)


def resolve_property_address(address: str) -> str:
    cleaned = address.strip().rstrip(",")
    if not cleaned:
        return ""
    if not should_resolve_address(cleaned):
        return cleaned

    results = find_addresses(cleaned, limit=1)
    if not results:
        return cleaned
    return str(results[0]["formatted_address"]).strip()


def address_components(address: str) -> Dict[str, str]:
    cleaned = re.sub(r"\s+", " ", address.strip())
    state = parse_state_from_address(cleaned)
    postcode_match = re.search(r"\b(\d{4})\b", cleaned)
    postcode = postcode_match.group(1) if postcode_match else ""
    locality_pattern = rf",\s*([^,]+?)\s*,?\s+({state})\s+{postcode}\b" if state in STATE_CODES and postcode else ""
    locality_match = re.search(locality_pattern, cleaned, flags=re.IGNORECASE) if locality_pattern else None
    suburb = locality_match.group(1).strip().title() if locality_match else ""
    return {
        "suburb": suburb,
        "property_state": state if state in STATE_CODES else "",
        "postcode": postcode,
    }


def apply_address_components(address: str) -> None:
    for key, value in address_components(address).items():
        if value:
            st.session_state[key] = value


def stamp_duty_signature(price: float, address: str) -> str:
    normalized_address = re.sub(r"\s+", " ", address.strip().casefold())
    return f"{normalized_address}|{price:.2f}"


def refresh_stamp_duty() -> None:
    price = as_number(st.session_state.price)
    address = str(st.session_state.property_address).strip()
    if price <= 0 or not address:
        st.session_state.stamp_duty = None
        st.session_state.stamp_duty_source_url = ""
        st.session_state.stamp_duty_message = ""
        st.session_state.stamp_duty_auto_signature = ""
        return

    result = calculate_stamp_duty(price, address)
    had_auto_duty = bool(st.session_state.get("stamp_duty_auto_signature", "")) or bool(
        st.session_state.get("stamp_duty_source_url", "")
    )
    st.session_state.stamp_duty_source_url = str(result["source_url"])
    st.session_state.stamp_duty_message = str(result["message"])
    if bool(result["supported"]):
        st.session_state.stamp_duty = round(float(result["duty"]), 0)
        st.session_state.stamp_duty_auto_signature = stamp_duty_signature(price, address)
    else:
        if had_auto_duty:
            st.session_state.stamp_duty = None
        st.session_state.stamp_duty_auto_signature = ""


def run_address_finder() -> None:
    query = str(st.session_state.address_search_query).strip()
    st.session_state.address_finder_message = ""
    st.session_state.address_search_results = []
    st.session_state.selected_address = ""

    if not query:
        st.session_state.address_finder_message = "Enter a suburb, street, or full address to search."
        return

    try:
        results = find_addresses(query)
    except Exception as exc:
        st.session_state.address_finder_message = f"Address finder failed: {exc}"
        return

    if not results:
        st.session_state.address_finder_message = "No address matches found."
        return

    st.session_state.address_search_results = results
    st.session_state.selected_address = str(results[0]["formatted_address"])
    st.session_state.address_finder_message = f"Found {len(results)} address match(es)."


def apply_selected_address() -> None:
    selected_address = str(st.session_state.selected_address).strip()
    if not selected_address:
        return

    st.session_state.property_address = selected_address
    apply_address_components(selected_address)
    st.session_state.save_name = selected_address
    fetch_statement_price_range()
    refresh_stamp_duty()
    clear_editor_drafts()


def run_listing_import(mode: str = "link") -> None:
    url = str(st.session_state.get("listing_url_input", "")).strip()
    all_pasted_text = str(st.session_state.get("listing_text_input", "")).strip()
    pasted_text = all_pasted_text if mode == "paste" else ""
    if mode == "paste" and not pasted_text:
        st.session_state.listing_import_message = "Paste the copied REA listing details before importing."
        return
    result = import_rea_listing(url, pasted_text)
    fields = dict(result.get("fields", {}))

    for key, value in fields.items():
        if key in DEFAULTS and value not in (None, ""):
            st.session_state[key] = value

    resolved_url = str(fields.get("listing_url") or url).strip()
    st.session_state.listing_url = resolved_url
    if resolved_url and not url:
        st.session_state.listing_url_input = resolved_url
    st.session_state.listing_text = all_pasted_text
    st.session_state.listing_import_message = str(result.get("message", ""))
    address = str(st.session_state.get("property_address", "")).strip()
    if address:
        apply_address_components(address)
        st.session_state.save_name = address
        fetch_statement_price_range()
        refresh_stamp_duty()
    clear_editor_drafts()


def clear_listing_text() -> None:
    st.session_state.listing_text_input = ""
    st.session_state.listing_text = ""
    st.session_state.listing_import_message = ""


def clear_stale_soi_values(address: str) -> None:
    previous_address = str(st.session_state.get("last_soi_lookup_address", "")).strip()
    if not previous_address or previous_address.casefold() == address.casefold():
        return
    # An SOI belongs to one exact property. Never carry its values to a new address.
    st.session_state.statement_price_low = None
    st.session_state.statement_price_high = None
    st.session_state.statement_source_url = ""


def fetch_statement_price_range(force: bool = False) -> None:
    raw_address = str(st.session_state.property_address).strip()
    address = raw_address.rstrip(",")
    if not address:
        return

    if should_resolve_address(address):
        try:
            resolved_address = resolve_property_address(address)
        except Exception as exc:
            st.session_state.statement_lookup_message = f"Address resolve failed: {exc}"
            return
        address = resolved_address or address
        st.session_state.property_address = address

    previous_address = str(st.session_state.get("last_soi_lookup_address", "")).strip()
    clear_stale_soi_values(address)
    if not address or (address == previous_address and not force):
        return

    st.session_state.last_soi_lookup_address = address
    st.session_state.statement_lookup_message = ""

    state = parse_state_from_address(address)
    if state != "VIC":
        st.session_state.statement_lookup_message = "SOI auto-fill only applies to Victorian properties."
        return

    try:
        result = lookup_statement_of_information(address, str(st.session_state.get("listing_url", "")))
    except Exception as exc:
        st.session_state.statement_lookup_message = f"SOI lookup failed: {exc}"
        return

    if not result["found"]:
        st.session_state.statement_lookup_message = str(result["message"])
        return

    st.session_state.statement_price_low = float(result["low"])
    st.session_state.statement_price_high = float(result["high"])
    st.session_state.statement_source_url = str(result["source_url"])
    st.session_state.statement_lookup_message = str(result["message"])
    apply_statement_midpoint()


def import_uploaded_soi() -> None:
    uploaded = st.session_state.get("soi_pdf_upload")
    if uploaded is None:
        st.session_state.statement_lookup_message = "Choose the downloaded REA Statement of Information PDF first."
        return

    address = str(st.session_state.get("property_address", "")).strip()
    clear_stale_soi_values(address)
    st.session_state.last_soi_lookup_address = address
    result = extract_statement_pdf(uploaded.getvalue(), address, str(uploaded.name))
    st.session_state.statement_lookup_message = str(result["message"])
    if not bool(result["found"]):
        return

    st.session_state.statement_price_low = float(result["low"])
    st.session_state.statement_price_high = float(result["high"])
    st.session_state.statement_source_url = ""
    st.session_state.last_soi_lookup_address = address
    apply_statement_midpoint()
    clear_editor_drafts()


def apply_statement_midpoint() -> None:
    low = as_number(st.session_state.statement_price_low)
    high = as_number(st.session_state.statement_price_high)
    if low <= 0:
        return
    midpoint = (low + high) / 2 if high > 0 else low
    st.session_state.price = midpoint
    st.session_state.property_value = midpoint
    refresh_stamp_duty()


def grouped_properties(saved_properties: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in saved_properties:
        groups.setdefault(str(item["state"]), []).append(item)
    return dict(sorted(groups.items(), key=lambda group: group[0]))


def render_saved_property_row(item: Dict[str, Any], key_scope: str) -> None:
    label = str(item["name"])
    display_label = f"★ {label}" if bool(item.get("is_favorite")) else label
    favorite_label = "★" if bool(item.get("is_favorite")) else "☆"
    favorite_col, load_col = st.columns([0.18, 0.82], gap="small")
    if favorite_col.button(favorite_label, key=f"favorite_{key_scope}_{label}", use_container_width=True):
        toggle_property_favorite(label)
        st.rerun()
    if load_col.button(display_label, key=f"load_{key_scope}_{label}", use_container_width=True):
        loaded = load_property(label)
        if loaded is not None:
            apply_payload_to_state(loaded["payload"], label)
            queue_active_page("Property workspace")
            st.rerun()
    st.caption(f"{item['address']}")


def render_portfolio_screener_page(saved_properties: List[Dict[str, Any]]) -> None:
    st.markdown(
        """
        <div class="pc-card" style="margin-bottom:0.9rem;">
            <div class="pc-card-title">Portfolio screener</div>
            <div class="pc-meta">Apply one deposit and funding scenario across every saved property, let the app auto-calculate stamp duty, and rank each deal by recommendation.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not saved_properties:
        st.info("Save at least one property first to use the portfolio screener.")
        return

    ensure_portfolio_widget_state()

    with st.expander("Filters & assumptions", expanded=True):
        control_col_1, control_col_2, control_col_3, control_col_4 = st.columns(4)
        control_col_1.selectbox(
            "Deposit mode",
            ["Percent", "Dollar"],
            index=["Percent", "Dollar"].index(str(portfolio_input_value("portfolio_deposit_mode"))),
            key=portfolio_widget_state_key("portfolio_deposit_mode"),
        )
        control_col_2.number_input(
            "Deposit value",
            value=float(as_number(portfolio_input_value("portfolio_deposit_value"))),
            key=portfolio_widget_state_key("portfolio_deposit_value"),
            min_value=0.0,
            step=1.0,
        )
        control_col_3.number_input(
            "Loan rate (%)",
            value=float(as_number(portfolio_input_value("portfolio_loan_rate"))),
            key=portfolio_widget_state_key("portfolio_loan_rate"),
            min_value=0.0,
            step=0.05,
        )
        control_col_4.number_input(
            "Loan term (years)",
            value=float(as_number(portfolio_input_value("portfolio_loan_years"))),
            key=portfolio_widget_state_key("portfolio_loan_years"),
            min_value=0.0,
            step=1.0,
        )

        assumptions_col_1, assumptions_col_2, assumptions_col_3, assumptions_col_4 = st.columns(4)
        assumptions_col_1.selectbox(
            "Repayment type",
            ["P+I", "I only"],
            index=["P+I", "I only"].index(str(portfolio_input_value("portfolio_repayment_type"))),
            key=portfolio_widget_state_key("portfolio_repayment_type"),
        )
        assumptions_col_2.number_input(
            "Solicitor / conveyancer",
            value=float(as_number(portfolio_input_value("portfolio_solicitor_charge"))),
            key=portfolio_widget_state_key("portfolio_solicitor_charge"),
            min_value=0.0,
            step=50.0,
        )
        assumptions_col_3.number_input(
            "Inspection costs",
            value=float(as_number(portfolio_input_value("portfolio_inspection_costs"))),
            key=portfolio_widget_state_key("portfolio_inspection_costs"),
            min_value=0.0,
            step=50.0,
        )
        assumptions_col_4.number_input(
            "Annual borrowing / package costs",
            value=float(as_number(portfolio_input_value("portfolio_annual_borrowing_costs"))),
            key=portfolio_widget_state_key("portfolio_annual_borrowing_costs"),
            min_value=0.0,
            step=50.0,
        )

        holding_col_1, holding_col_2, holding_col_3, holding_col_4, holding_col_5 = st.columns(5)
        holding_col_1.number_input(
            "Building insurance (annual)",
            value=float(as_number(portfolio_input_value("portfolio_building_insurance_annual"))),
            key=portfolio_widget_state_key("portfolio_building_insurance_annual"),
            min_value=0.0,
            step=50.0,
        )
        holding_col_2.number_input(
            "Landlord insurance (annual)",
            value=float(as_number(portfolio_input_value("portfolio_landlord_insurance_annual"))),
            key=portfolio_widget_state_key("portfolio_landlord_insurance_annual"),
            min_value=0.0,
            step=50.0,
        )
        holding_col_3.number_input(
            "Property manager rate (%)",
            value=float(as_number(portfolio_input_value("portfolio_property_manager_rate"))),
            key=portfolio_widget_state_key("portfolio_property_manager_rate"),
            min_value=0.0,
            step=0.1,
        )
        holding_col_4.number_input(
            "Vacancy allowance (%)",
            value=float(as_number(portfolio_input_value("portfolio_vacancy_allowance_pct"))),
            key=portfolio_widget_state_key("portfolio_vacancy_allowance_pct"),
            min_value=0.0,
            step=0.1,
        )
        holding_col_5.number_input(
            "Maintenance allowance (%)",
            value=float(as_number(portfolio_input_value("portfolio_maintenance_allowance_pct"))),
            key=portfolio_widget_state_key("portfolio_maintenance_allowance_pct"),
            min_value=0.0,
            step=0.1,
        )

        tax_col_1, tax_col_2 = st.columns(2)
        tax_col_1.number_input(
            "Income tax rate (%)",
            value=float(as_number(portfolio_input_value("portfolio_income_tax_rate"))),
            key=portfolio_widget_state_key("portfolio_income_tax_rate"),
            min_value=0.0,
            step=0.1,
        )
        with tax_col_2:
            st.markdown(
                """
                <div class="pc-mini-card" style="height:100%;">
                    <div class="pc-mini-title">How it works</div>
                    <div class="pc-compact-note">For each saved property, the screener uses the saved price, rent, and rates where available, auto-calculates stamp duty for VIC, NSW and QLD, then sets the main loan to the purchase price less the chosen deposit. Cash required upfront includes the deposit plus stamp duty and buying costs.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        sync_portfolio_widgets_to_inputs()

        save_settings_col, _ = st.columns([1, 4])
        save_settings_col.button(
            "Save screener inputs",
            use_container_width=True,
            on_click=persist_portfolio_screener_inputs,
        )

    if st.session_state.get("portfolio_settings_saved_notice", False):
        st.success("Portfolio screener inputs saved for next time.")
        st.session_state["portfolio_settings_saved_notice"] = False

    apply_portfolio_screener_manager_rate_edits()
    shared = portfolio_shared_inputs()
    screener = portfolio_screening_table(
        saved_properties,
        shared,
        st.session_state.get("portfolio_property_manager_usage", {}),
    )
    if screener.empty:
        st.info("Saved properties need at least a price and weekly rent before they can be screened.")
        return

    buy_count = int((screener["Recommendation"] == "BUY").sum())
    watch_count = int((screener["Recommendation"] == "WATCH").sum())
    avoid_count = int((screener["Recommendation"] == "AVOID").sum())
    metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
    metric_col_1.metric("Saved deals", len(screener))
    metric_col_2.metric("BUY", buy_count)
    metric_col_3.metric("WATCH", watch_count)
    metric_col_4.metric("AVOID", avoid_count)

    st.session_state["portfolio_screener_row_keys"] = list(screener["Property"])
    display_screener = screener.copy()
    display_screener["Recommendation"] = display_screener["Recommendation"].map(recommendation_badge)
    for column in [
        "Price",
        "Rent / wk",
        "Council / yr",
        "Water / yr",
        "Strata / yr",
        "Stamp duty",
        "Deposit",
        "Cash upfront",
        "Loan needed",
        "Break-even rent / wk",
        "Pre-tax CF / yr",
        "Post-tax CF / yr",
    ]:
        display_screener[column] = display_screener[column].map(currency)
    display_screener["Gross yield"] = display_screener["Gross yield"].map(lambda value: f"{float(value):.2f}%")
    display_screener["Net yield"] = display_screener["Net yield"].map(lambda value: f"{float(value):.2f}%")
    display_screener["DSCR"] = display_screener["DSCR"].map(lambda value: f"{float(value):.2f}x")
    display_screener["Overall / 10"] = display_screener["Overall / 10"].map(lambda value: f"{float(value):.1f}")

    st.data_editor(
        display_screener,
        key="portfolio_screener_editor",
        hide_index=True,
        use_container_width=True,
        disabled=[column for column in display_screener.columns if column != "Use PM rate"],
        column_config={
            "Use PM rate": st.column_config.CheckboxColumn("Use PM rate"),
        },
        height=760,
    )
    st.caption("Toggle `Use PM rate` per property to include or exclude the shared management fee from that row's screening calculations.")


def suggested_loan_split(price: float, deposit_amount: float, buying_costs: float, deposit_source: str) -> Dict[str, float]:
    return {
        "mortgage_1_amount": deposit_amount + buying_costs if deposit_source == "Equity" else 0.0,
        "mortgage_2_amount": max(price - deposit_amount, 0.0),
        "mortgage_3_amount": 0.0,
    }


def suggested_funding_message(price: float, deposit_amount: float, buying_costs: float, deposit_source: str) -> str:
    if price <= 0:
        return "Enter the purchase price to see the estimated loan needed."

    total_required = price + buying_costs
    if deposit_source == "Equity":
        equity_top_up = deposit_amount + buying_costs
        main_loan = max(price - deposit_amount, 0.0)
        total_loans = equity_top_up + main_loan
        return (
            f"Estimated loan needed: {currency(total_loans)} total, made up of "
            f"{currency(main_loan)} main loan and {currency(equity_top_up)} equity/top-up loan."
        )

    main_loan = max(price - deposit_amount, 0.0)
    cash_upfront = deposit_amount + buying_costs
    return (
        f"Estimated loan needed: {currency(main_loan)}. "
        f"You would also need {currency(cash_upfront)} cash upfront for the deposit and buying costs "
        f"on a total project cost of {currency(total_required)}."
    )


def calculate_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    price = as_number(payload["price"])
    deposit_input_mode = str(payload.get("deposit_input_mode", "Percent"))
    deposit_input_value = payload.get("deposit_input_value", payload.get("deposit_pct"))
    deposit_pct, deposit_amount = resolve_deposit_values(price, deposit_input_mode, deposit_input_value)
    property_value = as_number(payload["property_value"]) or price
    stamp_duty = as_number(payload["stamp_duty"])
    solicitor_charge = as_number(payload["solicitor_charge"])
    inspection_costs = as_number(payload["inspection_costs"])
    weekly_rent = as_number(payload["weekly_rent"])
    vacancy_allowance_pct = max(as_number(payload.get("vacancy_allowance_pct")), 0.0)
    maintenance_allowance_pct = max(as_number(payload.get("maintenance_allowance_pct")), 0.0)
    council_quarterly = as_number(payload["council_quarterly"])
    water_quarterly = as_number(payload["water_quarterly"])
    strata_quarterly = as_number(payload["strata_quarterly"])
    building_insurance_annual = as_number(payload["building_insurance_annual"])
    landlord_insurance_annual = as_number(payload["landlord_insurance_annual"])
    annual_borrowing_costs = as_number(payload["annual_borrowing_costs"])
    property_manager_rate = as_number(payload["property_manager_rate"])
    use_property_manager_rate = as_bool(payload.get("use_property_manager_rate"), default=True)
    depreciation_estimate = as_number(payload["depreciation_estimate"])
    income_tax_rate = as_number(payload["income_tax_rate"])
    deposit_source = str(payload["deposit_source"])

    buying_costs = stamp_duty + solicitor_charge + inspection_costs
    total_project_cost = price + buying_costs
    acquisition_cash_component = deposit_amount + buying_costs

    loans = [
        Loan(
            "Mortgage 1 / Equity Top-Up",
            as_number(payload["mortgage_1_rate"]),
            as_number(payload["mortgage_1_amount"]),
            as_number(payload["mortgage_1_years"]),
            str(payload.get("mortgage_1_repayment_type", "P+I")),
        ),
        Loan(
            "Mortgage 2 / Main Loan",
            as_number(payload["mortgage_2_rate"]),
            as_number(payload["mortgage_2_amount"]),
            as_number(payload["mortgage_2_years"]),
            str(payload.get("mortgage_2_repayment_type", "P+I")),
        ),
        Loan(
            "Mortgage 3 / Additional Loan",
            as_number(payload["mortgage_3_rate"]),
            as_number(payload["mortgage_3_amount"]),
            as_number(payload["mortgage_3_years"]),
            str(payload.get("mortgage_3_repayment_type", "P+I")),
        ),
    ]

    annual_rent = weekly_rent * WEEKS_PER_YEAR
    vacancy_allowance = annual_rent * vacancy_allowance_pct / 100
    effective_annual_rent = max(annual_rent - vacancy_allowance, 0.0)
    maintenance_allowance = annual_rent * maintenance_allowance_pct / 100
    council_annual = council_quarterly * QUARTERS_PER_YEAR
    water_annual = water_quarterly * QUARTERS_PER_YEAR
    strata_annual = strata_quarterly * QUARTERS_PER_YEAR
    insurance_annual = building_insurance_annual + landlord_insurance_annual
    applied_property_manager_rate = property_manager_rate if use_property_manager_rate else 0.0
    property_manager_fee = effective_annual_rent * applied_property_manager_rate / 100
    fixed_holding_costs = council_annual + water_annual + strata_annual + insurance_annual
    operating_expenses = fixed_holding_costs + property_manager_fee + maintenance_allowance
    total_interest = sum(loan.annual_interest for loan in loans)
    total_loan_repayments = sum(loan.annual_repayment for loan in loans)
    total_cash_expenses = (
        vacancy_allowance
        + operating_expenses
        + annual_borrowing_costs
        + total_loan_repayments
    )
    pre_tax_cashflow = annual_rent - total_cash_expenses

    taxable_result = effective_annual_rent - (
        operating_expenses + annual_borrowing_costs + total_interest + depreciation_estimate
    )
    tax_effect = -taxable_result * income_tax_rate / 100
    after_tax_cashflow = pre_tax_cashflow + tax_effect

    if deposit_source == "Equity":
        cash_required_upfront = max(acquisition_cash_component - as_number(payload["mortgage_1_amount"]), 0.0)
        equity_borrowed = as_number(payload["mortgage_1_amount"])
    else:
        cash_required_upfront = acquisition_cash_component
        equity_borrowed = 0.0

    total_borrowings = sum(loan.amount for loan in loans)
    funding_sources = cash_required_upfront + total_borrowings
    funding_gap = total_project_cost - funding_sources

    gross_yield = safe_divide(annual_rent, property_value) * 100
    net_operating_income = effective_annual_rent - operating_expenses
    net_yield_before_interest = safe_divide(net_operating_income, property_value) * 100
    net_yield_after_interest = safe_divide(
        net_operating_income - total_interest,
        property_value,
    ) * 100
    dscr = safe_divide(net_operating_income, total_loan_repayments)
    interest_cover = safe_divide(net_operating_income - annual_borrowing_costs, total_interest)
    total_debt_ratio = safe_divide(total_borrowings, property_value) * 100
    cash_on_cash = safe_divide(after_tax_cashflow, cash_required_upfront) * 100 if cash_required_upfront else 0.0
    rent_contribution_rate = (
        (1 - vacancy_allowance_pct / 100) * (1 - property_manager_rate / 100)
        - maintenance_allowance_pct / 100
    )
    fixed_cash_commitments = fixed_holding_costs + annual_borrowing_costs + total_loan_repayments
    break_even_rent_weekly = safe_divide(
        fixed_cash_commitments,
        WEEKS_PER_YEAR * max(rent_contribution_rate, 0.01),
    )

    adverse_risks = [
        as_number(payload.get("vacancy_risk", 5)),
        as_number(payload.get("liquidity_risk", 5)),
        as_number(payload.get("finance_difficulty", 5)),
        as_number(payload.get("body_corporate_risk", 5)),
        as_number(payload.get("regional_risk", 5)),
        as_number(payload.get("special_levy_risk", 5)),
    ]
    risk_score = sum(adverse_risks) / len(adverse_risks)
    growth_score = (
        as_number(payload.get("capital_growth_potential", 5)) * 0.65
        + as_number(payload.get("tenant_demand", 5)) * 0.35
    )
    yield_score = min(max(net_yield_before_interest * 1.5, 0.0), 10.0)
    cashflow_margin = safe_divide(pre_tax_cashflow, annual_rent) * 100 if annual_rent else -10.0
    cashflow_score = min(max(5 + cashflow_margin / 2, 0.0), 10.0)
    overall_score = (
        yield_score * 0.35
        + growth_score * 0.25
        + (10 - risk_score) * 0.25
        + cashflow_score * 0.15
    )

    if price <= 0 or annual_rent <= 0:
        recommendation = "INCOMPLETE"
    elif overall_score >= 7 and risk_score <= 6 and funding_gap <= 1_000:
        recommendation = "BUY"
    elif overall_score >= 5 and risk_score <= 7.5:
        recommendation = "WATCH"
    else:
        recommendation = "AVOID"

    recommendation_reasons: List[str] = []
    recommendation_reasons.append(
        f"Net yield before interest is {net_yield_before_interest:.2f}%."
    )
    recommendation_reasons.append(
        f"Annual pre-tax cash flow is {currency(pre_tax_cashflow)}."
    )
    if risk_score > 6:
        recommendation_reasons.append(f"Risk inputs average {risk_score:.1f}/10, which needs closer review.")
    if growth_score >= 7:
        recommendation_reasons.append(f"Growth and tenant-demand inputs support a {growth_score:.1f}/10 growth score.")
    if funding_gap > 1_000:
        recommendation_reasons.append(f"There is an unfunded deal gap of {currency(funding_gap)}.")

    return {
        "deposit_amount": deposit_amount,
        "buying_costs": buying_costs,
        "total_project_cost": total_project_cost,
        "acquisition_cash_component": acquisition_cash_component,
        "cash_required_upfront": cash_required_upfront,
        "equity_borrowed": equity_borrowed,
        "annual_rent": annual_rent,
        "effective_annual_rent": effective_annual_rent,
        "vacancy_allowance": vacancy_allowance,
        "maintenance_allowance": maintenance_allowance,
        "council_annual": council_annual,
        "water_annual": water_annual,
        "strata_annual": strata_annual,
        "insurance_annual": insurance_annual,
        "use_property_manager_rate": use_property_manager_rate,
        "applied_property_manager_rate": applied_property_manager_rate,
        "property_manager_fee": property_manager_fee,
        "fixed_holding_costs": fixed_holding_costs,
        "operating_expenses": operating_expenses,
        "net_operating_income": net_operating_income,
        "total_interest": total_interest,
        "total_loan_repayments": total_loan_repayments,
        "total_cash_expenses": total_cash_expenses,
        "pre_tax_cashflow": pre_tax_cashflow,
        "taxable_result": taxable_result,
        "tax_effect": tax_effect,
        "after_tax_cashflow": after_tax_cashflow,
        "gross_yield": gross_yield,
        "net_yield_before_interest": net_yield_before_interest,
        "net_yield_after_interest": net_yield_after_interest,
        "dscr": dscr,
        "interest_cover": interest_cover,
        "total_borrowings": total_borrowings,
        "total_debt_ratio": total_debt_ratio,
        "funding_gap": funding_gap,
        "cash_on_cash": cash_on_cash,
        "break_even_rent_weekly": break_even_rent_weekly,
        "risk_score": risk_score,
        "growth_score": growth_score,
        "yield_score": yield_score,
        "cashflow_score": cashflow_score,
        "overall_score": overall_score,
        "recommendation": recommendation,
        "recommendation_reasons": recommendation_reasons,
        "monthly_pre_tax_cashflow": pre_tax_cashflow / MONTHS_PER_YEAR,
        "monthly_after_tax_cashflow": after_tax_cashflow / MONTHS_PER_YEAR,
        "weekly_pre_tax_cashflow": pre_tax_cashflow / WEEKS_PER_YEAR,
        "weekly_after_tax_cashflow": after_tax_cashflow / WEEKS_PER_YEAR,
        "cashflow_label": (
            "Negative cash flow" if pre_tax_cashflow < 0 else ("Neutral cash flow" if pre_tax_cashflow == 0 else "Positive cash flow")
        ),
        "tax_position_label": (
            "Negatively geared" if taxable_result < 0 else ("Tax neutral" if taxable_result == 0 else "Positively geared")
        ),
        "loans": loans,
    }


def five_year_projection(payload: Dict[str, Any], metrics: Dict[str, Any]) -> pd.DataFrame:
    rent_growth = as_number(payload.get("rent_growth_pct")) / 100
    expense_inflation = as_number(payload.get("expense_inflation_pct")) / 100
    property_growth = as_number(payload.get("property_growth_pct")) / 100
    vacancy_rate = as_number(payload.get("vacancy_allowance_pct")) / 100
    maintenance_rate = as_number(payload.get("maintenance_allowance_pct")) / 100
    manager_rate = as_number(payload.get("property_manager_rate")) / 100
    income_tax_rate = as_number(payload.get("income_tax_rate")) / 100
    annual_borrowing_costs = as_number(payload.get("annual_borrowing_costs"))
    depreciation = as_number(payload.get("depreciation_estimate"))
    base_property_value = as_number(payload.get("property_value")) or as_number(payload.get("price"))
    base_rent = as_number(payload.get("weekly_rent")) * WEEKS_PER_YEAR
    base_fixed_expenses = float(metrics.get("fixed_holding_costs", 0.0))
    loans = list(metrics.get("loans", []))
    schedules = [amortization_schedule(loan) for loan in loans]
    cumulative_after_tax = 0.0
    rows: List[Dict[str, float | int]] = []

    for year in range(0, 6):
        gross_rent = base_rent * ((1 + rent_growth) ** year)
        vacancy = gross_rent * vacancy_rate
        effective_rent = max(gross_rent - vacancy, 0.0)
        maintenance = gross_rent * maintenance_rate
        manager_fee = effective_rent * manager_rate
        fixed_expenses = base_fixed_expenses * ((1 + expense_inflation) ** year)
        operating_expenses = fixed_expenses + maintenance + manager_fee
        property_value = base_property_value * ((1 + property_growth) ** year)

        if year == 0:
            loan_balance = sum(max(loan.amount, 0.0) for loan in loans)
            loan_repayments = sum(loan.annual_repayment for loan in loans)
            loan_interest = sum(loan.annual_interest for loan in loans)
        else:
            loan_balance = 0.0
            loan_repayments = 0.0
            loan_interest = 0.0
            for loan, schedule in zip(loans, schedules):
                if schedule.empty:
                    continue
                row_index = min(year - 1, len(schedule) - 1)
                schedule_row = schedule.iloc[row_index]
                loan_balance += as_number(schedule_row["Remaining balance"])
                if year <= len(schedule):
                    loan_repayments += loan.annual_repayment
                    loan_interest += as_number(schedule_row["Interest paid"])

        pre_tax_cashflow = (
            effective_rent
            - operating_expenses
            - annual_borrowing_costs
            - loan_repayments
        )
        taxable_result = (
            effective_rent
            - operating_expenses
            - annual_borrowing_costs
            - loan_interest
            - depreciation
        )
        tax_effect = -taxable_result * income_tax_rate
        after_tax_cashflow = pre_tax_cashflow + tax_effect
        if year > 0:
            cumulative_after_tax += after_tax_cashflow

        rows.append(
            {
                "Year": year,
                "Property value": property_value,
                "Gross rent": gross_rent,
                "Effective rent": effective_rent,
                "Operating expenses": operating_expenses,
                "Loan repayments": loan_repayments,
                "Pre-tax cash flow": pre_tax_cashflow,
                "After-tax cash flow": after_tax_cashflow,
                "Loan balance": loan_balance,
                "Estimated equity": property_value - loan_balance,
                "Cumulative after-tax cash flow": cumulative_after_tax,
            }
        )

    return pd.DataFrame(rows)


def annual_expense_table(metrics: Dict[str, float | str | List[Loan]], payload: Dict[str, float | str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Category": "Gross rent", "Annual amount": float(metrics["annual_rent"])},
            {"Category": "Vacancy allowance", "Annual amount": -float(metrics["vacancy_allowance"])},
            {"Category": "Council rates", "Annual amount": -float(metrics["council_annual"])},
            {"Category": "Water rates", "Annual amount": -float(metrics["water_annual"])},
            {"Category": "Strata", "Annual amount": -float(metrics["strata_annual"])},
            {"Category": "Building insurance", "Annual amount": -as_number(payload["building_insurance_annual"])},
            {"Category": "Landlord insurance", "Annual amount": -as_number(payload["landlord_insurance_annual"])},
            {"Category": "Property manager fee", "Annual amount": -float(metrics["property_manager_fee"])},
            {"Category": "Maintenance allowance", "Annual amount": -float(metrics["maintenance_allowance"])},
            {"Category": "Borrowing/package costs", "Annual amount": -as_number(payload["annual_borrowing_costs"])},
            {"Category": "Mortgage repayments", "Annual amount": -float(metrics["total_loan_repayments"])},
            {"Category": "Pre-tax cash flow", "Annual amount": float(metrics["pre_tax_cashflow"])},
            {"Category": "Estimated tax effect", "Annual amount": float(metrics["tax_effect"])},
            {"Category": "After-tax cash flow", "Annual amount": float(metrics["after_tax_cashflow"])},
        ]
    )


def table_value(value: Any, field_type: str = "", format_currency: bool = False) -> str:
    if value in (None, ""):
        return ""
    if format_currency and field_type == "currency":
        return currency(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_table_value(value: Any, field_type: str, options: List[str] | None = None) -> Any:
    text = str(value).strip() if value is not None else ""
    if field_type in {"number", "currency", "percent"}:
        cleaned = text.replace("$", "").replace(",", "").replace("%", "")
        if cleaned == "":
            return None
        numeric = as_number(cleaned)
        return numeric
    if field_type == "number":
        return None if text == "" else as_number(text)
    if field_type == "choice":
        normalized_options = options or []
        for option in normalized_options:
            if text.lower() == str(option).lower():
                return option
        lowered = text.lower()
        if lowered == "cash":
            return "Cash"
        if lowered == "equity":
            return "Equity"
        if lowered == "percent":
            return "Percent"
        if lowered == "dollar":
            return "Dollar"
        return text
    return text


def render_editable_section(title: str, editor_key: str, rows: List[Dict[str, str]], show_title: bool = True) -> None:
    if show_title and title:
        st.markdown(f"**{title}**")
    draft_key = f"{editor_key}_draft"
    if draft_key not in st.session_state:
        format_currency = bool(st.session_state.get("has_calculated", False))
        st.session_state[draft_key] = pd.DataFrame(
            [
                {
                    "": row["label"],
                    " ": table_value(st.session_state[row["key"]], row["type"], format_currency),
                    "  ": (
                        st.session_state.get(row.get("source_key", ""), "")
                        if row.get("source_key")
                        else ""
                    ),
                }
                for row in rows
            ]
        )

    edited = st.data_editor(
        st.session_state[draft_key],
        key=editor_key,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=["", "  "],
        column_config={
            "": st.column_config.TextColumn("", disabled=True),
            " ": st.column_config.TextColumn(""),
            "  ": st.column_config.LinkColumn("", display_text="Source", disabled=True),
        },
    )
    st.session_state[draft_key] = edited.copy()


def render_table_like_select_row(label: str, widget_key: str, options: List[str]) -> None:
    row_col_1, row_col_2, row_col_3 = st.columns([0.45, 0.45, 0.10], gap="small")
    row_col_1.markdown(label)
    row_col_2.selectbox(label, options=options, key=widget_key, label_visibility="collapsed")
    row_col_3.write("")


def payload_from_editor_sections(section_rows: List[tuple[str, List[Dict[str, str]]]]) -> Dict[str, Any]:
    payload = current_payload()
    for editor_key, rows in section_rows:
        frame = st.session_state.get(f"{editor_key}_draft")
        if frame is None:
            continue
        for idx, row in enumerate(rows):
            payload[row["key"]] = parse_table_value(frame.iloc[idx][" "], row["type"], row.get("options"))
    return payload


def input_editor_sections() -> Dict[str, List[Dict[str, str]]]:
    current_deposit_mode = str(
        st.session_state.get(
            "deposit_input_mode_input",
            st.session_state.get("deposit_input_mode", "Percent"),
        )
    )
    deposit_row_label = "Deposit %" if current_deposit_mode == "Percent" else "Deposit $"
    deposit_row_type = "percent" if current_deposit_mode == "Percent" else "currency"
    return {
        "facts_editor": [
            {"label": "Property address", "key": "property_address", "type": "text"},
            {"label": "Suburb", "key": "suburb", "type": "text"},
            {"label": "State", "key": "property_state", "type": "text"},
            {"label": "Postcode", "key": "postcode", "type": "text"},
            {"label": "Property type", "key": "property_type", "type": "text"},
            {"label": "Bedrooms", "key": "bedrooms", "type": "number"},
            {"label": "Bathrooms", "key": "bathrooms", "type": "number"},
            {"label": "Car spaces", "key": "car_spaces", "type": "number"},
            {"label": "Land size (sqm)", "key": "land_size_sqm", "type": "number"},
            {"label": "Tenancy status", "key": "tenancy_status", "type": "text"},
            {"label": "REA listing notes", "key": "listing_summary", "type": "text"},
        ],
        "purchase_editor": [
            {"label": "REA price low", "key": "listing_price_low", "type": "currency"},
            {"label": "REA price high", "key": "listing_price_high", "type": "currency"},
            {"label": "SOI price low", "key": "statement_price_low", "type": "currency"},
            {"label": "SOI price high", "key": "statement_price_high", "type": "currency"},
            {"label": "Price", "key": "price", "type": "currency"},
            {"label": deposit_row_label, "key": "deposit_input_value", "type": deposit_row_type},
            {
                "label": "Stamp duty",
                "key": "stamp_duty",
                "type": "currency",
                "source_key": "stamp_duty_source_url",
            },
            {"label": "Solicitor charge", "key": "solicitor_charge", "type": "currency"},
            {"label": "Building & pest / other costs", "key": "inspection_costs", "type": "currency"},
            {"label": "Property value", "key": "property_value", "type": "currency"},
        ],
        "rent_rates_editor": [
            {"label": "Weekly rent", "key": "weekly_rent", "type": "currency"},
            {"label": "Vacancy allowance", "key": "vacancy_allowance_pct", "type": "percent"},
            {"label": "Maintenance allowance", "key": "maintenance_allowance_pct", "type": "percent"},
            {"label": "Annual rent growth", "key": "rent_growth_pct", "type": "percent"},
            {"label": "Annual expense inflation", "key": "expense_inflation_pct", "type": "percent"},
            {"label": "Annual property growth", "key": "property_growth_pct", "type": "percent"},
            {"label": "Council (quarterly)", "key": "council_quarterly", "type": "currency"},
            {"label": "Water (quarterly)", "key": "water_quarterly", "type": "currency"},
            {"label": "Strata (quarterly)", "key": "strata_quarterly", "type": "currency"},
            {"label": "Building insurance (annual)", "key": "building_insurance_annual", "type": "currency"},
            {"label": "Landlord insurance (annual)", "key": "landlord_insurance_annual", "type": "currency"},
        ],
        "finance_editor": [
            {"label": "Mortgage 1 rate", "key": "mortgage_1_rate", "type": "percent"},
            {"label": "Mortgage 1 amount", "key": "mortgage_1_amount", "type": "currency"},
            {"label": "Mortgage 1 years", "key": "mortgage_1_years", "type": "number"},
            {"label": "Mortgage 2 rate", "key": "mortgage_2_rate", "type": "percent"},
            {"label": "Mortgage 2 amount", "key": "mortgage_2_amount", "type": "currency"},
            {"label": "Mortgage 2 years", "key": "mortgage_2_years", "type": "number"},
            {"label": "Mortgage 3 rate", "key": "mortgage_3_rate", "type": "percent"},
            {"label": "Mortgage 3 amount", "key": "mortgage_3_amount", "type": "currency"},
            {"label": "Mortgage 3 years", "key": "mortgage_3_years", "type": "number"},
            {"label": "Annual borrowing / package costs", "key": "annual_borrowing_costs", "type": "currency"},
        ],
        "tax_editor": [
            {"label": "Property manager rate", "key": "property_manager_rate", "type": "percent"},
            {"label": "Depreciation estimate", "key": "depreciation_estimate", "type": "currency"},
            {"label": "Income", "key": "income", "type": "currency"},
            {"label": "Income tax rate", "key": "income_tax_rate", "type": "percent"},
        ],
    }


def latest_input_payload(section_rows: Dict[str, List[Dict[str, str]]] | None = None) -> Dict[str, Any]:
    sections = section_rows or input_editor_sections()
    payload = payload_from_editor_sections(list(sections.items()))
    payload["listing_url"] = str(st.session_state.get("listing_url_input", payload["listing_url"])).strip()
    payload["listing_text"] = str(st.session_state.get("listing_text_input", payload["listing_text"]))
    payload["deposit_input_mode"] = str(
        st.session_state.get("deposit_input_mode_input", payload["deposit_input_mode"])
    )
    payload["deposit_pct"] = resolve_deposit_values(
        as_number(payload["price"]),
        str(payload["deposit_input_mode"]),
        payload["deposit_input_value"],
    )[0]
    payload["deposit_source"] = str(st.session_state.get("deposit_source_input", payload["deposit_source"]))
    for mortgage_number in (1, 2, 3):
        key = f"mortgage_{mortgage_number}_repayment_type"
        payload[key] = str(st.session_state.get(f"{key}_input", payload[key]))
    return payload


def save_ready_payload() -> Dict[str, Any]:
    return latest_input_payload(input_editor_sections())


def update_editor_draft_values(editor_key: str, rows: List[Dict[str, str]], updates: Dict[str, Any]) -> None:
    draft_key = f"{editor_key}_draft"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = pd.DataFrame(
            [
                {
                    "": row["label"],
                    " ": table_value(st.session_state[row["key"]]),
                    "  ": (
                        st.session_state.get(row.get("source_key", ""), "")
                        if row.get("source_key")
                        else ""
                    ),
                }
                for row in rows
            ]
        )

    frame = st.session_state[draft_key].copy()
    for idx, row in enumerate(rows):
        if row["key"] in updates:
            frame.at[idx, " "] = table_value(updates[row["key"]])
    st.session_state[draft_key] = frame


def loan_table(loans: List[Loan]) -> pd.DataFrame:
    rows = []
    for loan in loans:
        rows.append(
            {
                "Loan": loan.name,
                "Repayment type": loan.repayment_type,
                "Term (yrs)": loan.effective_term_years if loan.effective_term_years > 0 else None,
                "Rate": loan.rate_pct / 100,
                "Amount": loan.amount,
                "Annual repayment": loan.annual_repayment,
                "Annual interest": loan.annual_interest,
            }
        )
    return pd.DataFrame(rows)


def amortization_schedule(loan: Loan) -> pd.DataFrame:
    amount = max(loan.amount, 0.0)
    term_years = max(loan.effective_term_years, 0.0)
    columns = ["Year", "Principal repaid", "Interest paid", "Remaining balance"]
    if amount <= 0 or term_years <= 0:
        return pd.DataFrame(columns=columns)

    total_payments = max(int(round(term_years * MONTHS_PER_YEAR)), 1)
    monthly_rate = max(loan.rate_pct, 0.0) / 100 / MONTHS_PER_YEAR
    if str(loan.repayment_type) == "I only":
        monthly_payment = amount * monthly_rate
    elif monthly_rate > 0:
        monthly_payment = amount * monthly_rate / (1 - (1 + monthly_rate) ** (-total_payments))
    else:
        monthly_payment = amount / total_payments

    balance = amount
    annual_interest = 0.0
    annual_principal = 0.0
    rows: List[Dict[str, float]] = []

    for payment_number in range(1, total_payments + 1):
        interest = balance * monthly_rate
        if str(loan.repayment_type) == "I only":
            principal = 0.0
        else:
            principal = min(max(monthly_payment - interest, 0.0), balance)
            balance = max(balance - principal, 0.0)

        annual_interest += interest
        annual_principal += principal
        if payment_number % MONTHS_PER_YEAR == 0 or payment_number == total_payments:
            rows.append(
                {
                    "Year": float((payment_number - 1) // MONTHS_PER_YEAR + 1),
                    "Principal repaid": annual_principal,
                    "Interest paid": annual_interest,
                    "Remaining balance": balance,
                }
            )
            annual_interest = 0.0
            annual_principal = 0.0

    return pd.DataFrame(rows, columns=columns)


def render_amortization_charts(loans: List[Loan]) -> None:
    active_loans = [loan for loan in loans if loan.amount > 0]
    if not active_loans:
        st.info("Enter a mortgage amount, rate, and term to generate the repayment curve.")
        return

    st.markdown("#### Mortgage principal and interest curves")
    st.caption("Each curve shows the annual principal and interest portions calculated from the selected loan settings.")
    for loan in active_loans:
        schedule = amortization_schedule(loan)
        if schedule.empty:
            continue
        schedule["Cumulative interest paid"] = schedule["Interest paid"].cumsum()
        total_interest = float(schedule["Cumulative interest paid"].iloc[-1])
        title = (
            f"{loan.name}: {currency(loan.amount)} at {loan.rate_pct:.2f}% "
            f"over {loan.effective_term_years:.0f} years ({loan.repayment_type})"
        )
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(
                x=schedule["Year"],
                y=schedule["Principal repaid"],
                name="Annual principal repaid",
                mode="lines",
                line={"color": "#0f766e", "width": 3},
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=schedule["Year"],
                y=schedule["Interest paid"],
                name="Annual interest paid",
                mode="lines",
                line={"color": "#c2410c", "width": 3},
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=schedule["Year"],
                y=schedule["Cumulative interest paid"],
                name="Interest paid over tenure",
                mode="lines",
                line={"color": "#1d4ed8", "width": 3, "dash": "dash"},
            ),
            secondary_y=True,
        )
        fig.add_annotation(
            x=1,
            y=1.14,
            xref="paper",
            yref="paper",
            text=f"Total interest over tenure: <b>{currency(total_interest)}</b>",
            showarrow=False,
            xanchor="right",
        )
        fig.update_layout(
            title=title,
            hovermode="x unified",
            legend_title_text="",
            margin={"t": 105},
        )
        fig.update_xaxes(title_text="Mortgage year")
        fig.update_yaxes(
            title_text="Annual principal / interest (AUD)",
            tickprefix="$",
            tickformat=",.0f",
            secondary_y=False,
        )
        fig.update_yaxes(
            title_text="Interest paid over tenure (AUD)",
            tickprefix="$",
            tickformat=",.0f",
            secondary_y=True,
        )
        st.plotly_chart(fig, width="stretch")


def acquisition_table(metrics: Dict[str, float | str | List[Loan]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Item": "Purchase price", "Amount": float(metrics["total_project_cost"]) - float(metrics["buying_costs"])},
            {"Item": "Deposit amount", "Amount": float(metrics["deposit_amount"])},
            {"Item": "Buying costs", "Amount": float(metrics["buying_costs"])},
            {"Item": "Deposit + buying costs", "Amount": float(metrics["acquisition_cash_component"])},
            {"Item": "Cash required upfront", "Amount": float(metrics["cash_required_upfront"])},
            {"Item": "Borrowed equity used", "Amount": float(metrics["equity_borrowed"])},
            {"Item": "Total borrowings", "Amount": float(metrics["total_borrowings"])},
            {"Item": "Funding gap / surplus", "Amount": float(metrics["funding_gap"])},
        ]
    )


def sensitivity_table(payload: Dict[str, float | str]) -> pd.DataFrame:
    rent_shifts = [-0.10, -0.05, 0.0, 0.05, 0.10]
    rate_shifts = [-1.0, -0.5, 0.0, 0.5, 1.0]
    rows = []

    for rate_shift in rate_shifts:
        scenario_row: Dict[str, float | str] = {"Rate shift": f"{rate_shift:+.2f} pts"}
        for rent_shift in rent_shifts:
            scenario_payload = dict(payload)
            scenario_payload["weekly_rent"] = max(as_number(payload["weekly_rent"]) * (1 + rent_shift), 0.0)
            scenario_payload["mortgage_1_rate"] = max(as_number(payload["mortgage_1_rate"]) + rate_shift, 0.0)
            scenario_payload["mortgage_2_rate"] = max(as_number(payload["mortgage_2_rate"]) + rate_shift, 0.0)
            scenario_payload["mortgage_3_rate"] = max(as_number(payload["mortgage_3_rate"]) + rate_shift, 0.0)
            scenario_metrics = calculate_metrics(scenario_payload)
            scenario_row[f"Rent {rent_shift:+.0%}"] = float(scenario_metrics["after_tax_cashflow"])
        rows.append(scenario_row)

    return pd.DataFrame(rows)


def indicative_lmi_premium(loan_amount: float, property_value: float) -> float:
    if loan_amount <= 0 or property_value <= 0:
        return 0.0

    lvr = safe_divide(loan_amount, property_value) * 100
    if lvr <= 80:
        return 0.0
    if lvr <= 85:
        rate = 0.01
    elif lvr <= 90:
        rate = 0.015
    else:
        rate = 0.02
    return round(loan_amount * rate, 0)


def base_loan_for_target_lvr(target_lvr_pct: float, property_value: float) -> tuple[float, float]:
    if target_lvr_pct <= 0 or property_value <= 0:
        return 0.0, 0.0

    target_total_loan = property_value * target_lvr_pct / 100
    base_loan = target_total_loan
    for _ in range(10):
        lmi = indicative_lmi_premium(base_loan, property_value)
        next_base_loan = max(target_total_loan - lmi, 0.0)
        if abs(next_base_loan - base_loan) < 1:
            base_loan = next_base_loan
            break
        base_loan = next_base_loan

    lmi = indicative_lmi_premium(base_loan, property_value)
    return round(base_loan, 0), round(lmi, 0)


def deposit_comparison_table(payload: Dict[str, float | str]) -> pd.DataFrame:
    price = as_number(payload["price"])
    property_value = as_number(payload["property_value"]) or price
    if price <= 0:
        return pd.DataFrame()

    stamp_duty = as_number(payload["stamp_duty"])
    solicitor_charge = as_number(payload["solicitor_charge"])
    inspection_costs = as_number(payload["inspection_costs"])
    buying_costs = stamp_duty + solicitor_charge + inspection_costs
    main_rate = as_number(payload["mortgage_2_rate"]) or as_number(payload["mortgage_1_rate"]) or as_number(payload["mortgage_3_rate"])
    main_term_years = (
        as_number(payload["mortgage_2_years"])
        or as_number(payload["mortgage_1_years"])
        or as_number(payload["mortgage_3_years"])
    )
    main_repayment_type = str(
        payload.get("mortgage_2_repayment_type")
        or payload.get("mortgage_1_repayment_type")
        or payload.get("mortgage_3_repayment_type")
        or "P+I"
    )

    rows = []
    for lvr_pct in LVR_COMPARISON_LEVELS:
        base_loan, lmi = base_loan_for_target_lvr(lvr_pct, property_value)
        deposit_amount = max(price - base_loan, 0.0)
        deposit_pct = safe_divide(deposit_amount, price) * 100
        total_loan = base_loan + lmi

        scenario_payload = dict(payload)
        scenario_payload.update(
            {
                "deposit_input_mode": "Percent",
                "deposit_input_value": float(deposit_pct),
                "deposit_pct": float(deposit_pct),
                "deposit_source": "Cash",
                "mortgage_1_rate": 0.0,
                "mortgage_1_amount": 0.0,
                "mortgage_1_years": 0.0,
                "mortgage_1_repayment_type": "P+I",
                "mortgage_2_rate": main_rate,
                "mortgage_2_amount": total_loan,
                "mortgage_2_years": main_term_years,
                "mortgage_2_repayment_type": main_repayment_type,
                "mortgage_3_rate": 0.0,
                "mortgage_3_amount": 0.0,
                "mortgage_3_years": 0.0,
                "mortgage_3_repayment_type": "P+I",
                "property_value": property_value,
            }
        )
        scenario_metrics = calculate_metrics(scenario_payload)

        rows.append(
            {
                "LVR": f"{lvr_pct:.0f}%",
                "Deposit %": f"{deposit_pct:.0f}%",
                "Deposit ($)": deposit_amount,
                "Base loan ($)": base_loan,
                "Indicative LMI ($)": lmi,
                "Loan incl. LMI ($)": total_loan,
                "Actual LVR incl. LMI": safe_divide(total_loan, property_value) * 100,
                "Cash upfront ($)": deposit_amount + buying_costs,
                "Annual interest ($)": float(scenario_metrics["total_interest"]),
                "Pre-tax cash flow ($)": float(scenario_metrics["pre_tax_cashflow"]),
                "After-tax cash flow ($)": float(scenario_metrics["after_tax_cashflow"]),
            }
        )

    return pd.DataFrame(rows)


def saved_property_comparison_table() -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for item in list_properties():
        saved = load_property(str(item["name"]))
        if saved is None:
            continue
        payload = dict(DEFAULTS)
        payload.update(saved["payload"])
        metrics = calculate_metrics(payload)
        rows.append(
            {
                "Property": str(item["name"]),
                "Price": as_number(payload.get("price")),
                "Weekly rent": as_number(payload.get("weekly_rent")),
                "Gross yield": float(metrics["gross_yield"]),
                "Net yield": float(metrics["net_yield_before_interest"]),
                "Pre-tax cash flow": float(metrics["pre_tax_cashflow"]),
                "Cash required": float(metrics["cash_required_upfront"]),
                "Risk / 10": float(metrics["risk_score"]),
                "Overall / 10": float(metrics["overall_score"]),
                "Recommendation": str(metrics["recommendation"]),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Overall / 10", "Net yield"], ascending=[False, False])


def portfolio_price(payload: Dict[str, Any]) -> float:
    direct_price = as_number(payload.get("price"))
    if direct_price > 0:
        return direct_price
    low = as_number(payload.get("listing_price_low"))
    high = as_number(payload.get("listing_price_high"))
    if low > 0 and high > 0:
        return (low + high) / 2
    return low or high


def portfolio_shared_inputs() -> Dict[str, Any]:
    sync_portfolio_transient_inputs()
    return {
        "deposit_mode": str(st.session_state.get("portfolio_deposit_mode", "Percent")),
        "deposit_value": st.session_state.get("portfolio_deposit_value", 20.0),
        "loan_rate": st.session_state.get("portfolio_loan_rate", 6.1),
        "loan_years": st.session_state.get("portfolio_loan_years", 30.0),
        "repayment_type": str(st.session_state.get("portfolio_repayment_type", "P+I")),
        "solicitor_charge": st.session_state.get("portfolio_solicitor_charge", 1800.0),
        "inspection_costs": st.session_state.get("portfolio_inspection_costs", 650.0),
        "annual_borrowing_costs": st.session_state.get("portfolio_annual_borrowing_costs", 395.0),
        "building_insurance_annual": st.session_state.get("portfolio_building_insurance_annual", 1000.0),
        "landlord_insurance_annual": st.session_state.get("portfolio_landlord_insurance_annual", 450.0),
        "property_manager_rate": st.session_state.get("portfolio_property_manager_rate", 7.0),
        "vacancy_allowance_pct": st.session_state.get("portfolio_vacancy_allowance_pct", 2.0),
        "maintenance_allowance_pct": st.session_state.get("portfolio_maintenance_allowance_pct", 1.0),
        "income_tax_rate": st.session_state.get("portfolio_income_tax_rate", 37.0),
    }


def build_portfolio_screening_payload(
    saved: Dict[str, Any],
    shared: Dict[str, Any],
    use_property_manager_rate: bool = True,
) -> Dict[str, Any]:
    payload = dict(DEFAULTS)
    payload.update(saved.get("payload", {}))

    address = str(payload.get("property_address") or saved.get("address") or "").strip()
    price = portfolio_price(payload)
    property_value = as_number(payload.get("property_value")) or price
    deposit_mode = str(shared["deposit_mode"])
    deposit_value = shared["deposit_value"]
    deposit_pct, deposit_amount = resolve_deposit_values(price, deposit_mode, deposit_value)
    stamp_result = calculate_stamp_duty(price, address)
    stamp_duty = (
        float(stamp_result["duty"])
        if bool(stamp_result["supported"])
        else as_number(payload.get("stamp_duty"))
    )

    payload.update(
        {
            "property_address": address,
            "price": price,
            "property_value": property_value or price,
            "deposit_input_mode": deposit_mode,
            "deposit_input_value": deposit_value,
            "deposit_pct": deposit_pct,
            "deposit_source": "Cash",
            "stamp_duty": stamp_duty,
            "stamp_duty_source_url": str(stamp_result.get("source_url") or ""),
            "stamp_duty_message": str(stamp_result.get("message") or ""),
            "solicitor_charge": as_number(shared["solicitor_charge"]),
            "inspection_costs": as_number(shared["inspection_costs"]),
            "annual_borrowing_costs": as_number(shared["annual_borrowing_costs"]),
            "building_insurance_annual": as_number(shared["building_insurance_annual"]),
            "landlord_insurance_annual": as_number(shared["landlord_insurance_annual"]),
            "property_manager_rate": as_number(shared["property_manager_rate"]),
            "use_property_manager_rate": use_property_manager_rate,
            "vacancy_allowance_pct": as_number(shared["vacancy_allowance_pct"]),
            "maintenance_allowance_pct": as_number(shared["maintenance_allowance_pct"]),
            "income_tax_rate": as_number(shared["income_tax_rate"]),
            "mortgage_1_rate": 0.0,
            "mortgage_1_amount": 0.0,
            "mortgage_1_years": 0.0,
            "mortgage_1_repayment_type": "P+I",
            "mortgage_2_rate": as_number(shared["loan_rate"]),
            "mortgage_2_amount": max(price - deposit_amount, 0.0),
            "mortgage_2_years": as_number(shared["loan_years"]),
            "mortgage_2_repayment_type": str(shared["repayment_type"]),
            "mortgage_3_rate": 0.0,
            "mortgage_3_amount": 0.0,
            "mortgage_3_years": 0.0,
            "mortgage_3_repayment_type": "P+I",
        }
    )
    return payload


def portfolio_screening_table(
    saved_properties: List[Dict[str, Any]],
    shared: Dict[str, Any],
    property_manager_usage: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    usage_map = property_manager_usage or {}
    for item in saved_properties:
        saved = load_property(str(item["name"]))
        if saved is None:
            continue
        property_name = str(item["name"])
        use_property_manager_rate = as_bool(usage_map.get(property_name), default=True)
        scenario_payload = build_portfolio_screening_payload(
            saved,
            shared,
            use_property_manager_rate=use_property_manager_rate,
        )
        if as_number(scenario_payload.get("price")) <= 0 or as_number(scenario_payload.get("weekly_rent")) <= 0:
            continue
        metrics = calculate_metrics(scenario_payload)
        rows.append(
            {
                "Recommendation": str(metrics["recommendation"]),
                "Use PM rate": use_property_manager_rate,
                "Sold": "Yes" if bool(scenario_payload.get("is_sold")) else "No",
                "Property": property_name,
                "State": str(item["state"]),
                "Price": as_number(scenario_payload.get("price")),
                "Rent / wk": as_number(scenario_payload.get("weekly_rent")),
                "Council / yr": as_number(scenario_payload.get("council_quarterly")) * QUARTERS_PER_YEAR,
                "Water / yr": as_number(scenario_payload.get("water_quarterly")) * QUARTERS_PER_YEAR,
                "Strata / yr": as_number(scenario_payload.get("strata_quarterly")) * QUARTERS_PER_YEAR,
                "Stamp duty": as_number(scenario_payload.get("stamp_duty")),
                "Deposit": float(metrics["deposit_amount"]),
                "Cash upfront": float(metrics["cash_required_upfront"]),
                "Loan needed": float(metrics["total_borrowings"]),
                "Gross yield": float(metrics["gross_yield"]),
                "Net yield": float(metrics["net_yield_before_interest"]),
                "DSCR": float(metrics["dscr"]),
                "Break-even rent / wk": float(metrics["break_even_rent_weekly"]),
                "Pre-tax CF / yr": float(metrics["pre_tax_cashflow"]),
                "Post-tax CF / yr": float(metrics["after_tax_cashflow"]),
                "Overall / 10": float(metrics["overall_score"]),
                "Buy now": "Yes" if str(metrics["recommendation"]) == "BUY" else "No",
            }
        )
    if not rows:
        return pd.DataFrame()
    comparison = pd.DataFrame(rows)
    return comparison.sort_values(
        ["Net yield", "Overall / 10", "Property"],
        ascending=[False, False, True],
    )


def recommendation_cell_style(value: Any) -> str:
    recommendation = str(value).strip().upper()
    if recommendation == "BUY":
        return "background-color: #dcfce7; color: #166534; font-weight: 700;"
    if recommendation == "WATCH":
        return "background-color: #fef3c7; color: #92400e; font-weight: 700;"
    if recommendation == "AVOID":
        return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
    return ""


def recommendation_badge(value: Any) -> str:
    recommendation = str(value).strip().upper()
    if recommendation == "BUY":
        return "🟢 BUY"
    if recommendation == "WATCH":
        return "🟡 WATCH"
    if recommendation == "AVOID":
        return "🔴 AVOID"
    if recommendation == "INCOMPLETE":
        return "⚪ INCOMPLETE"
    return recommendation


def save_portfolio_screener_inputs(shared: Dict[str, Any]) -> None:
    payload = {
        "portfolio_deposit_mode": str(shared["deposit_mode"]),
        "portfolio_deposit_value": shared["deposit_value"],
        "portfolio_loan_rate": shared["loan_rate"],
        "portfolio_loan_years": shared["loan_years"],
        "portfolio_repayment_type": str(shared["repayment_type"]),
        "portfolio_solicitor_charge": shared["solicitor_charge"],
        "portfolio_inspection_costs": shared["inspection_costs"],
        "portfolio_annual_borrowing_costs": shared["annual_borrowing_costs"],
        "portfolio_building_insurance_annual": shared["building_insurance_annual"],
        "portfolio_landlord_insurance_annual": shared["landlord_insurance_annual"],
        "portfolio_property_manager_rate": shared["property_manager_rate"],
        "portfolio_vacancy_allowance_pct": shared["vacancy_allowance_pct"],
        "portfolio_maintenance_allowance_pct": shared["maintenance_allowance_pct"],
        "portfolio_income_tax_rate": shared["income_tax_rate"],
    }
    save_setting("portfolio_screener_inputs", payload)


def persist_portfolio_screener_inputs() -> None:
    sync_portfolio_widgets_to_inputs()
    sync_portfolio_transient_inputs()
    save_portfolio_screener_inputs(portfolio_shared_inputs())
    st.session_state["portfolio_settings_saved_notice"] = True


def section_title(label: str) -> None:
    st.markdown(f"### {label}")


def render_table_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stDataEditor"] [data-testid="stDataFrameColHeader"] {
            display: none;
        }
        div[data-testid="stDataEditor"] [role="columnheader"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_analyst_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --pc-bg: #eef3f8;
            --pc-surface: #ffffff;
            --pc-surface-alt: #f7fafd;
            --pc-ink: #0f172a;
            --pc-muted: #5f6f85;
            --pc-line: #d7e1ec;
            --pc-blue: #1d4ed8;
            --pc-blue-soft: #dbeafe;
            --pc-green: #15803d;
            --pc-amber: #b45309;
            --pc-red: #b91c1c;
            --pc-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 24%),
                linear-gradient(180deg, #f7fbff 0%, var(--pc-bg) 100%);
            color: var(--pc-ink);
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #eff5fb 0%, #e8eef6 100%);
            border-right: 1px solid var(--pc-line);
        }

        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
            color: var(--pc-ink);
            letter-spacing: -0.01em;
        }

        div[data-testid="stTextInput"] > div,
        div[data-testid="stTextArea"] > div,
        div[data-testid="stNumberInput"] > div,
        div[data-testid="stSelectbox"] > div,
        div[data-testid="stFileUploader"] section,
        div[data-testid="stDataFrame"],
        div[data-testid="stMetric"] {
            border-radius: 14px;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input,
        div[data-baseweb="select"] > div {
            background: var(--pc-surface);
            border: 1px solid var(--pc-line);
            color: var(--pc-ink);
            box-shadow: none;
        }

        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stFileUploader"] label {
            color: var(--pc-muted);
            font-size: 0.83rem;
            font-weight: 600;
            letter-spacing: 0.01em;
        }

        button[kind="primary"],
        .stLinkButton a {
            border-radius: 12px !important;
            font-weight: 600 !important;
        }

        button[kind="primary"] {
            background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
            border: none !important;
            box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22) !important;
        }

        button[kind="secondary"] {
            border-radius: 12px !important;
            border: 1px solid var(--pc-line) !important;
            background: var(--pc-surface) !important;
            color: var(--pc-ink) !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--pc-line);
            border-radius: 16px;
            padding: 0.35rem;
            backdrop-filter: blur(10px);
        }

        .stTabs [data-baseweb="tab"] {
            height: 2.5rem;
            border-radius: 12px;
            color: var(--pc-muted);
            font-weight: 600;
            padding: 0 1rem;
        }

        .stTabs [aria-selected="true"] {
            background: var(--pc-surface) !important;
            color: var(--pc-blue) !important;
            box-shadow: var(--pc-shadow);
        }

        div[data-testid="stMetric"] {
            background: var(--pc-surface);
            border: 1px solid var(--pc-line);
            box-shadow: var(--pc-shadow);
            padding: 0.55rem 0.8rem;
        }

        div[data-testid="stMetricLabel"] {
            color: var(--pc-muted);
            font-weight: 600;
        }

        div[data-testid="stMetricValue"] {
            color: var(--pc-ink);
            letter-spacing: -0.03em;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--pc-line);
            overflow: hidden;
            box-shadow: var(--pc-shadow);
        }

        div[data-testid="stDataFrame"] thead tr,
        div[data-testid="stDataEditor"] thead tr {
            background: #244a7c;
        }

        div[data-testid="stDataFrame"] thead th,
        div[data-testid="stDataEditor"] thead th {
            color: #ffffff !important;
            font-weight: 700 !important;
            border-bottom: 1px solid #173252 !important;
        }

        .pc-shell {
            margin-bottom: 1rem;
            padding: 1rem 1.1rem 0.95rem;
            border: 1px solid var(--pc-line);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.82);
            box-shadow: var(--pc-shadow);
            backdrop-filter: blur(12px);
        }

        .pc-page-title {
            font-size: 1.7rem;
            font-weight: 800;
            color: var(--pc-ink);
            letter-spacing: -0.03em;
            margin: 0;
        }

        .pc-page-subtitle {
            margin-top: 0.2rem;
            color: var(--pc-muted);
            font-size: 0.92rem;
        }

        .pc-summary-band {
            position: sticky;
            top: 0.65rem;
            z-index: 30;
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #0f172a 0%, #183b67 100%);
            border: 1px solid rgba(191, 219, 254, 0.2);
            box-shadow: 0 18px 34px rgba(15, 23, 42, 0.22);
            margin-bottom: 1rem;
        }

        .pc-summary-grid {
            display: grid;
            grid-template-columns: 1.4fr repeat(4, minmax(120px, 1fr));
            gap: 0.85rem;
            align-items: center;
        }

        .pc-summary-label {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #93c5fd;
        }

        .pc-summary-value {
            font-size: 1.35rem;
            font-weight: 800;
            color: #f8fbff;
            letter-spacing: -0.03em;
        }

        .pc-summary-meta {
            font-size: 0.83rem;
            color: #cbd5e1;
            margin-top: 0.18rem;
        }

        .pc-card {
            padding: 0.95rem 1rem;
            border: 1px solid var(--pc-line);
            border-radius: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #f9fbfe 100%);
            box-shadow: var(--pc-shadow);
        }

        .pc-card-title {
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--pc-muted);
            margin-bottom: 0.35rem;
        }

        .pc-address {
            font-size: 1.15rem;
            font-weight: 800;
            color: var(--pc-ink);
            letter-spacing: -0.02em;
        }

        .pc-meta {
            font-size: 0.85rem;
            color: var(--pc-muted);
            margin-top: 0.25rem;
        }

        .pc-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.65rem;
        }

        .pc-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.28rem 0.62rem;
            font-size: 0.78rem;
            font-weight: 700;
            background: var(--pc-blue-soft);
            color: var(--pc-blue);
        }

        .pc-status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.15rem 0 0.7rem;
        }

        .pc-status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border-radius: 999px;
            padding: 0.3rem 0.62rem;
            font-size: 0.77rem;
            font-weight: 700;
            border: 1px solid transparent;
        }

        .pc-status-blue {
            background: #dbeafe;
            color: #1d4ed8;
            border-color: #bfdbfe;
        }

        .pc-status-green {
            background: #dcfce7;
            color: #166534;
            border-color: #bbf7d0;
        }

        .pc-status-amber {
            background: #fef3c7;
            color: #92400e;
            border-color: #fde68a;
        }

        .pc-status-slate {
            background: #e2e8f0;
            color: #334155;
            border-color: #cbd5e1;
        }

        .pc-status-red {
            background: #fee2e2;
            color: #991b1b;
            border-color: #fecaca;
        }

        .pc-mini-card {
            padding: 0.78rem 0.9rem;
            border-radius: 14px;
            border: 1px solid var(--pc-line);
            background: #fbfdff;
            box-shadow: var(--pc-shadow);
        }

        .pc-mini-title {
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--pc-muted);
            margin-bottom: 0.3rem;
            font-weight: 700;
        }

        .pc-compact-note {
            color: var(--pc-muted);
            font-size: 0.83rem;
            line-height: 1.45;
        }

        .pc-sidebar-card {
            padding: 0.8rem 0.9rem;
            border-radius: 16px;
            border: 1px solid var(--pc-line);
            background: rgba(255,255,255,0.88);
            box-shadow: var(--pc-shadow);
            margin-bottom: 0.85rem;
        }

        .pc-sidebar-stat-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.45rem;
            margin-top: 0.6rem;
        }

        .pc-sidebar-stat {
            border-radius: 12px;
            padding: 0.55rem 0.6rem;
            background: #f7fafd;
            border: 1px solid var(--pc-line);
        }

        .pc-sidebar-stat strong {
            display: block;
            color: var(--pc-ink);
            font-size: 1rem;
        }

        .pc-sidebar-stat span {
            color: var(--pc-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .pc-report-shell {
            padding: 1rem 1.05rem;
            border-radius: 18px;
            border: 1px solid var(--pc-line);
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, #f8fbff 100%);
            box-shadow: var(--pc-shadow);
            margin-bottom: 0.95rem;
        }

        .pc-report-title {
            font-size: 1.45rem;
            font-weight: 800;
            color: var(--pc-ink);
            letter-spacing: -0.03em;
            margin: 0;
        }

        .pc-report-subtitle {
            color: var(--pc-muted);
            font-size: 0.88rem;
            margin-top: 0.18rem;
        }

        .pc-report-grid {
            display: grid;
            grid-template-columns: 1.6fr repeat(3, minmax(120px, 1fr));
            gap: 0.8rem;
            margin-top: 0.85rem;
        }

        .pc-report-stat {
            border-radius: 14px;
            border: 1px solid var(--pc-line);
            background: #ffffff;
            padding: 0.72rem 0.85rem;
        }

        .pc-report-stat span {
            display: block;
            color: var(--pc-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            margin-bottom: 0.2rem;
        }

        .pc-report-stat strong {
            color: var(--pc-ink);
            font-size: 1.02rem;
        }

        .pc-print-note {
            margin-top: 0.75rem;
            color: var(--pc-muted);
            font-size: 0.82rem;
            line-height: 1.45;
        }

        @media print {
            section[data-testid="stSidebar"],
            header[data-testid="stHeader"],
            .stTabs [data-baseweb="tab-list"],
            button,
            .stDownloadButton,
            .stButton,
            .stLinkButton,
            [data-testid="collapsedControl"] {
                display: none !important;
            }

            .stApp {
                background: #ffffff !important;
            }

            .block-container {
                padding: 0.2in 0.25in !important;
                max-width: 100% !important;
            }

            .pc-shell,
            .pc-summary-band,
            .pc-card,
            .pc-mini-card,
            .pc-recommendation,
            .pc-sidebar-card,
            .pc-report-shell,
            div[data-testid="stMetric"],
            div[data-testid="stDataFrame"] {
                box-shadow: none !important;
                background: #ffffff !important;
                border-color: #cbd5e1 !important;
            }

            .pc-summary-band {
                position: static !important;
            }

            .pc-report-grid,
            .pc-summary-grid,
            .pc-score-strip {
                grid-template-columns: 1fr 1fr !important;
            }
        }

        .pc-score-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.8rem;
        }

        .pc-score-box {
            border-radius: 14px;
            padding: 0.7rem 0.85rem;
            background: #f7fafd;
            border: 1px solid var(--pc-line);
        }

        .pc-score-box strong {
            display: block;
            font-size: 1.1rem;
            color: var(--pc-ink);
        }

        .pc-score-box span {
            color: var(--pc-muted);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .pc-recommendation {
            padding: 1rem 1.05rem;
            border-radius: 18px;
            background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
            border: 1px solid var(--pc-line);
            box-shadow: var(--pc-shadow);
        }

        .pc-recommendation ul {
            margin: 0.7rem 0 0;
            padding-left: 1rem;
            color: var(--pc-muted);
            font-size: 0.86rem;
            line-height: 1.5;
        }

        @media (max-width: 1100px) {
            .pc-summary-grid,
            .pc-score-strip {
                grid-template-columns: 1fr 1fr;
            }
        }

        @media (max-width: 760px) {
            .pc-summary-grid,
            .pc-score-strip {
                grid-template-columns: 1fr;
            }
            .pc-page-title {
                font-size: 1.35rem;
            }
            .pc-summary-band {
                position: static;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_calculation() -> None:
    sync_transient_inputs()
    address = str(st.session_state.get("property_address", "")).strip()
    if address:
        apply_address_components(address)
        if not str(st.session_state.get("save_name", "")).strip():
            st.session_state.save_name = address
    fetch_statement_price_range()
    refresh_stamp_duty()
    st.session_state.calculated_payload = current_payload()
    st.session_state.has_calculated = True


def status_badge_html(label: str, tone: str = "slate") -> str:
    tone_class = {
        "blue": "pc-status-blue",
        "green": "pc-status-green",
        "amber": "pc-status-amber",
        "slate": "pc-status-slate",
        "red": "pc-status-red",
    }.get(tone, "pc-status-slate")
    return f'<span class="pc-status-badge {tone_class}">{label}</span>'


def render_status_badges(badges: List[tuple[str, str]]) -> None:
    if not badges:
        return
    st.markdown(
        f'<div class="pc-status-row">{"".join(status_badge_html(label, tone) for label, tone in badges)}</div>',
        unsafe_allow_html=True,
    )


def listing_status_badges() -> List[tuple[str, str]]:
    badges: List[tuple[str, str]] = []
    listing_url = str(st.session_state.get("listing_url_input", "")).strip()
    listing_text = str(st.session_state.get("listing_text_input", "")).strip()
    import_message = str(st.session_state.get("listing_import_message", "")).strip().lower()
    if "imported" in import_message:
        badges.append(("REA imported", "blue"))
    elif listing_text:
        badges.append(("Manual paste ready", "amber"))
    else:
        badges.append(("Manual entry", "slate"))
    if listing_url.startswith(("https://www.realestate.com.au/", "http://www.realestate.com.au/")):
        badges.append(("REA link attached", "green"))
    return badges


def purchase_status_badges() -> List[tuple[str, str]]:
    badges: List[tuple[str, str]] = []
    if str(st.session_state.get("statement_source_url", "")).strip():
        badges.append(("SOI verified", "green"))
    elif as_number(st.session_state.get("statement_price_low")) > 0 or as_number(st.session_state.get("statement_price_high")) > 0:
        badges.append(("SOI loaded", "blue"))
    else:
        badges.append(("SOI manual / empty", "slate"))

    if str(st.session_state.get("stamp_duty_source_url", "")).strip():
        badges.append(("Stamp duty auto", "green"))
    elif as_number(st.session_state.get("stamp_duty")) > 0:
        badges.append(("Stamp duty manual", "amber"))
    else:
        badges.append(("Stamp duty empty", "slate"))

    deposit_mode = str(st.session_state.get("deposit_input_mode_input", "Percent"))
    badges.append((f"Deposit by {deposit_mode.lower()}", "blue"))
    return badges


def render_top_summary(metrics: Dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="pc-summary-band">
            <div class="pc-summary-grid">
                <div>
                    <div class="pc-summary-label">Feasibility snapshot</div>
                    <div class="pc-summary-value">{metrics['cashflow_label']}</div>
                    <div class="pc-summary-meta">Pre-tax yearly: {currency(metrics['pre_tax_cashflow'])} · After-tax yearly: {currency(metrics['after_tax_cashflow'])}</div>
                </div>
                <div>
                    <div class="pc-summary-label">Gross yield</div>
                    <div class="pc-summary-value">{metrics['gross_yield']:.2f}%</div>
                    <div class="pc-summary-meta">Top-line rent return</div>
                </div>
                <div>
                    <div class="pc-summary-label">Net yield pre interest</div>
                    <div class="pc-summary-value">{metrics['net_yield_before_interest']:.2f}%</div>
                    <div class="pc-summary-meta">After operating costs</div>
                </div>
                <div>
                    <div class="pc-summary-label">Monthly after tax</div>
                    <div class="pc-summary-value">{currency(metrics['monthly_after_tax_cashflow'])}</div>
                    <div class="pc-summary-meta">Approximate monthly position</div>
                </div>
                <div>
                    <div class="pc-summary-label">Break-even rent</div>
                    <div class="pc-summary-value">{currency(metrics['break_even_rent_weekly'])}/wk</div>
                    <div class="pc-summary-meta">Holding-cost threshold</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_property_card(payload: Dict[str, Any]) -> None:
    address = str(payload.get("property_address") or "Unnamed property")
    suburb = str(payload.get("suburb") or "")
    state = str(payload.get("property_state") or "")
    postcode = str(payload.get("postcode") or "")
    locality = " ".join(part for part in [suburb, state, postcode] if part)
    sold_label = "Sold" if bool(payload.get("is_sold")) else "Available"

    st.markdown(
        f"""
        <div class="pc-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;">
                <div>
                    <div class="pc-card-title">Property profile</div>
                    <div class="pc-address">{address}</div>
                    <div class="pc-meta">{locality or "Locality not set"}</div>
                    <div class="pc-pill-row">
                        <span class="pc-pill">{sold_label}</span>
                        <span class="pc-pill">{payload.get("property_type") or "Type not set"}</span>
                        <span class="pc-pill">{property_fact(payload.get("bedrooms"))} bed</span>
                        <span class="pc-pill">{property_fact(payload.get("bathrooms"))} bath</span>
                        <span class="pc-pill">{property_fact(payload.get("car_spaces"))} car</span>
                    </div>
                    <div class="pc-meta" style="margin-top:0.7rem;">
                        {sold_label} ·
                        {payload.get("property_type") or "Type not set"} ·
                        {property_fact(payload.get("bedrooms"))} bed ·
                        {property_fact(payload.get("bathrooms"))} bath ·
                        {property_fact(payload.get("car_spaces"))} car
                    </div>
                </div>
                <div style="text-align:right;min-width:220px;">
                    <div class="pc-card-title">Deal inputs</div>
                    <div style="font-size:1.4rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;">{currency(payload.get("price"))}</div>
                    <div class="pc-meta">Purchase price</div>
                    <div style="font-size:1.1rem;font-weight:700;color:#1d4ed8;margin-top:0.7rem;">{currency(payload.get("weekly_rent"))}/wk</div>
                    <div class="pc-meta">Estimated weekly rent</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics_grid(metrics: Dict[str, Any]) -> None:
    row_one = st.columns(5)
    row_one[0].metric("Gross yield", pct(float(metrics["gross_yield"])))
    row_one[1].metric("Net yield (pre interest)", pct(float(metrics["net_yield_before_interest"])))
    row_one[2].metric("Net yield (post interest)", pct(float(metrics["net_yield_after_interest"])))
    dscr_label = f"{float(metrics['dscr']):.2f}x" if float(metrics["total_loan_repayments"]) else "n/a"
    row_one[3].metric("DSCR", dscr_label)
    row_one[4].metric("Debt ratio", pct(float(metrics["total_debt_ratio"])))

    row_two = st.columns(4)
    row_two[0].metric("Cash required upfront", currency(float(metrics["cash_required_upfront"])))
    row_two[1].metric("Total borrowings", currency(float(metrics["total_borrowings"])))
    row_two[2].metric("Break-even rent", f"{currency(float(metrics['break_even_rent_weekly']))}/wk")
    cash_on_cash_label = (
        pct(float(metrics["cash_on_cash"])) if float(metrics["cash_required_upfront"]) else "n/a"
    )
    row_two[3].metric("Cash-on-cash", cash_on_cash_label)


def render_recommendation_card(metrics: Dict[str, Any]) -> None:
    recommendation = str(metrics["recommendation"])
    color = {
        "BUY": "#22c55e",
        "WATCH": "#facc15",
        "AVOID": "#f97316",
        "INCOMPLETE": "#6b7280",
    }.get(recommendation, "#38bdf8")

    st.markdown(
        f"""
        <div class="pc-recommendation" style="border-color:{color};">
            <div class="pc-card-title">Recommendation</div>
            <div style="font-size:1.65rem;color:{color};font-weight:800;letter-spacing:-0.03em;">{recommendation}</div>
            <div class="pc-score-strip">
                <div class="pc-score-box"><span>Overall</span><strong>{float(metrics['overall_score']):.1f}/10</strong></div>
                <div class="pc-score-box"><span>Risk</span><strong>{float(metrics['risk_score']):.1f}/10</strong></div>
                <div class="pc-score-box"><span>Growth</span><strong>{float(metrics['growth_score']):.1f}/10</strong></div>
                <div class="pc-score-box"><span>Yield</span><strong>{float(metrics['yield_score']):.1f}/10</strong></div>
            </div>
            <ul>
                {''.join(f"<li>{reason}</li>" for reason in metrics['recommendation_reasons'])}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_final_summary_page(payload: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    generated_at = datetime.now().strftime("%d %b %Y %I:%M %p")
    source_badges: List[tuple[str, str]] = []
    if str(payload.get("listing_url") or "").strip():
        source_badges.append(("REA link attached", "blue"))
    if str(payload.get("statement_source_url") or st.session_state.get("statement_source_url", "")).strip():
        source_badges.append(("SOI verified", "green"))
    elif as_number(payload.get("statement_price_low")) > 0 or as_number(payload.get("statement_price_high")) > 0:
        source_badges.append(("SOI loaded", "blue"))
    if str(payload.get("stamp_duty_source_url") or "").strip():
        source_badges.append(("Stamp duty auto", "green"))
    elif as_number(payload.get("stamp_duty")) > 0:
        source_badges.append(("Stamp duty manual", "amber"))

    st.markdown(
        f"""
        <div class="pc-report-shell">
            <div class="pc-report-title">Property Feasibility Summary</div>
            <div class="pc-report-subtitle">Share-ready analyst summary for investor review and PDF export.</div>
            <div class="pc-report-grid">
                <div class="pc-report-stat">
                    <span>Property</span>
                    <strong>{str(payload.get("property_address") or "Property address not set")}</strong>
                </div>
                <div class="pc-report-stat">
                    <span>Recommendation</span>
                    <strong>{str(metrics.get("recommendation", "INCOMPLETE"))}</strong>
                </div>
                <div class="pc-report-stat">
                    <span>Generated</span>
                    <strong>{generated_at}</strong>
                </div>
                <div class="pc-report-stat">
                    <span>Purchase price</span>
                    <strong>{currency(payload.get("price"))}</strong>
                </div>
            </div>
            <div class="pc-print-note">Use this page for investor sharing, browser print, or PDF export. The report uses the same live feasibility values as the analysis tab.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_status_badges(source_badges)
    share_col_1, share_col_2 = st.columns([1, 1.2], gap="medium")
    with share_col_1:
        if st.session_state.has_calculated:
            render_pdf_download(payload, metrics, button_key="pdf_download_summary")
    with share_col_2:
        st.markdown(
            """
            <div class="pc-mini-card" style="margin-bottom:0.75rem;">
                <div class="pc-mini-title">Print view</div>
                <div class="pc-compact-note">Use your browser print action from this tab for a cleaner paper/share layout. Sidebar, tab headers, and app buttons are hidden in print.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    render_top_summary(metrics)
    top_left, top_right = st.columns([1.45, 1], gap="medium")
    with top_left:
        render_property_card(payload)
        render_metrics_grid(metrics)
    with top_right:
        render_recommendation_card(metrics)

    summary_col_1, summary_col_2 = st.columns([1.15, 1], gap="medium")
    with summary_col_1:
        st.markdown(
            """
            <div class="pc-mini-card" style="margin-bottom:0.75rem;">
                <div class="pc-mini-title">Acquisition snapshot</div>
                <div class="pc-compact-note">Compact funding view for the purchase, deposit, buying costs, and total borrowings.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            acquisition_table(metrics).style.format({"Amount": currency}),
            use_container_width=True,
            hide_index=True,
        )

    with summary_col_2:
        st.markdown(
            """
            <div class="pc-mini-card" style="margin-bottom:0.75rem;">
                <div class="pc-mini-title">Cashflow snapshot</div>
                <div class="pc-compact-note">The final operating view in yearly, monthly, and weekly form for fast investor review.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        snapshot_df = pd.DataFrame(
            [
                {"Metric": "Pre-tax cash flow (yearly)", "Value": currency(float(metrics["pre_tax_cashflow"]))},
                {"Metric": "Post-tax cash flow (yearly)", "Value": currency(float(metrics["after_tax_cashflow"]))},
                {"Metric": "Pre-tax cash flow (monthly)", "Value": currency(float(metrics["monthly_pre_tax_cashflow"]))},
                {"Metric": "Post-tax cash flow (monthly)", "Value": currency(float(metrics["monthly_after_tax_cashflow"]))},
                {"Metric": "Pre-tax cash flow (weekly)", "Value": currency(float(metrics["weekly_pre_tax_cashflow"]))},
                {"Metric": "Post-tax cash flow (weekly)", "Value": currency(float(metrics["weekly_after_tax_cashflow"]))},
                {"Metric": "Net yield before interest", "Value": pct(float(metrics["net_yield_before_interest"]))},
                {"Metric": "Net yield after interest", "Value": pct(float(metrics["net_yield_after_interest"]))},
            ]
        )
        st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

    insight_col_1, insight_col_2 = st.columns([1, 1.1], gap="medium")
    with insight_col_1:
        st.markdown(
            """
            <div class="pc-mini-card" style="margin-bottom:0.75rem;">
                <div class="pc-mini-title">Risk and return profile</div>
                <div class="pc-compact-note">Core rating signals from the current scenario.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        profile_df = pd.DataFrame(
            [
                {"Metric": "Risk score", "Value": f"{float(metrics['risk_score']):.1f}/10"},
                {"Metric": "Growth score", "Value": f"{float(metrics['growth_score']):.1f}/10"},
                {"Metric": "Yield score", "Value": f"{float(metrics['yield_score']):.1f}/10"},
                {"Metric": "Overall score", "Value": f"{float(metrics['overall_score']):.1f}/10"},
                {"Metric": "Break-even rent", "Value": f"{currency(float(metrics['break_even_rent_weekly']))}/wk"},
                {"Metric": "Total debt ratio", "Value": pct(float(metrics["total_debt_ratio"]))},
                {"Metric": "Cash-on-cash", "Value": pct(float(metrics["cash_on_cash"])) if float(metrics["cash_required_upfront"]) else "n/a"},
                {"Metric": "Funding gap / surplus", "Value": currency(float(metrics["funding_gap"]))},
            ]
        )
        st.dataframe(profile_df, use_container_width=True, hide_index=True)

    with insight_col_2:
        st.markdown(
            """
            <div class="pc-mini-card" style="margin-bottom:0.75rem;">
                <div class="pc-mini-title">Loan structure</div>
                <div class="pc-compact-note">Compact mortgage view with amount, rate, term, repayment type, and annual servicing cost.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            loan_table(metrics["loans"]).style.format(
                {
                    "Term (yrs)": "{:.0f}",
                    "Rate": "{:.2%}",
                    "Amount": currency,
                    "Annual repayment": currency,
                    "Annual interest": currency,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown(
        """
        <div class="pc-mini-card" style="margin:0.3rem 0 0.75rem;">
            <div class="pc-mini-title">Summary charts</div>
            <div class="pc-compact-note">A concise analyst-style visual on cashflow components and five-year property/equity movement.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    chart_left, chart_right = st.columns(2, gap="medium")
    with chart_left:
        cashflow_df = annual_expense_table(metrics, payload)
        chart_df = cashflow_df[
            ~cashflow_df["Category"].isin(["Pre-tax cash flow", "Estimated tax effect", "After-tax cash flow"])
        ].copy()
        chart_df["Direction"] = chart_df["Annual amount"].apply(lambda value: "Income" if value >= 0 else "Cost")
        cashflow_chart = px.bar(
            chart_df,
            x="Category",
            y="Annual amount",
            color="Direction",
            color_discrete_map={"Income": "#1d4ed8", "Cost": "#b91c1c"},
            title="Annual cashflow components",
        )
        cashflow_chart.update_layout(showlegend=False, xaxis_title="", yaxis_title="AUD", margin={"t": 48, "l": 8, "r": 8, "b": 8})
        st.plotly_chart(cashflow_chart, use_container_width=True)
    with chart_right:
        projection = five_year_projection(payload, metrics)
        projection_chart = px.line(
            projection,
            x="Year",
            y=["Property value", "Loan balance", "Estimated equity"],
            markers=True,
            title="Five-year value and equity",
            color_discrete_map={
                "Property value": "#1d4ed8",
                "Loan balance": "#c2410c",
                "Estimated equity": "#15803d",
            },
        )
        projection_chart.update_layout(hovermode="x unified", legend_title_text="", yaxis_title="AUD", margin={"t": 48, "l": 8, "r": 8, "b": 8})
        projection_chart.update_yaxes(tickprefix="$", tickformat=",.0f")
        st.plotly_chart(projection_chart, use_container_width=True)


def render_tabs(payload: Dict[str, Any]) -> None:
    tab_details, tab_purchase, tab_rent, tab_finance, tab_analysis, tab_final_summary, tab_export = st.tabs(
        [
            "Property details",
            "Purchase & costs",
            "Rent & expenses",
            "Finance",
            "Analysis & charts",
            "Final summary",
            "Save & export",
        ]
    )

    with tab_details:
        render_status_badges(listing_status_badges())
        left_col, right_col = st.columns([1.35, 1], gap="medium")
        with left_col:
            st.markdown(
                """
                <div class="pc-mini-card" style="margin-bottom:0.85rem;">
                    <div class="pc-mini-title">Import workflow</div>
                    <div class="pc-compact-note">Paste the REA link or copied listing text, then confirm the core property profile in one compact block.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.text_input("Property address", key="property_address")
            details_col_1, details_col_2, details_col_3, details_col_4 = st.columns(4)
            details_col_1.text_input("Suburb", key="suburb")
            details_col_2.text_input("State", key="property_state")
            details_col_3.text_input("Postcode", key="postcode")
            details_col_4.text_input("Property type", key="property_type")
            st.checkbox("Property sold", key="is_sold")

            facts_col_1, facts_col_2, facts_col_3, facts_col_4 = st.columns(4)
            facts_col_1.number_input("Bedrooms", key="bedrooms", min_value=0.0, step=1.0)
            facts_col_2.number_input("Bathrooms", key="bathrooms", min_value=0.0, step=1.0)
            facts_col_3.number_input("Car spaces", key="car_spaces", min_value=0.0, step=1.0)
            facts_col_4.number_input("Land size sqm", key="land_size_sqm", min_value=0.0, step=1.0)

            st.text_area("Listing summary", key="listing_summary", height=95)
            st.text_input("REA listing URL", key="listing_url_input")
            st.text_area("Copied REA listing details", key="listing_text_input", height=110)
            import_col_1, import_col_2, import_col_3 = st.columns(3)
            import_col_1.button("Import from URL", on_click=run_listing_import, args=("link",), use_container_width=True)
            import_col_2.button("Import from pasted text", on_click=run_listing_import, args=("paste",), use_container_width=True)
            if str(st.session_state.get("listing_url_input", "")).strip().startswith(
                ("https://www.realestate.com.au/", "http://www.realestate.com.au/")
            ):
                import_col_3.link_button("Open REA listing", str(st.session_state["listing_url_input"]), use_container_width=True)
            if str(st.session_state.get("listing_import_message", "")).strip():
                st.info(str(st.session_state["listing_import_message"]))

        with right_col:
            st.markdown(
                """
                <div class="pc-mini-card" style="margin-bottom:0.85rem;">
                    <div class="pc-mini-title">Address & verification</div>
                    <div class="pc-compact-note">Use the address finder for incomplete entries and keep SOI verification visible beside the imported listing details.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.session_state.address_search_results:
                options = [str(item["formatted_address"]) for item in st.session_state.address_search_results]
                if st.session_state.selected_address not in options:
                    st.session_state.selected_address = options[0]
            finder_col_1, finder_col_2 = st.columns([2, 1])
            finder_col_1.text_input("Find suburb or address", key="address_search_query")
            finder_col_2.button("Find address", on_click=run_address_finder, use_container_width=True)
            if st.session_state.address_search_results:
                match_col_1, match_col_2 = st.columns([2, 1])
                match_col_1.selectbox(
                    "Address matches",
                    options=[str(item["formatted_address"]) for item in st.session_state.address_search_results],
                    key="selected_address",
                )
                match_col_2.button("Use selected address", on_click=apply_selected_address, use_container_width=True)
            if str(st.session_state.get("address_finder_message", "")).strip():
                st.caption(str(st.session_state["address_finder_message"]))

            st.file_uploader(
                "REA Statement of Information PDF",
                type=["pdf"],
                key="soi_pdf_upload",
                help="The PDF must match the selected property address and stay under 10 MB.",
            )
            soi_col_1, soi_col_2 = st.columns(2)
            soi_col_1.button("Search verified REA SOI", on_click=fetch_statement_price_range, args=(True,), use_container_width=True)
            soi_col_2.button("Import verified SOI PDF", on_click=import_uploaded_soi, use_container_width=True)
            if str(st.session_state.get("statement_lookup_message", "")).strip():
                st.info(str(st.session_state["statement_lookup_message"]))
            if str(st.session_state.get("statement_source_url", "")).strip():
                st.link_button("Open SOI source", str(st.session_state["statement_source_url"]), use_container_width=True)

    with tab_purchase:
        render_status_badges(purchase_status_badges())
        purchase_left, purchase_right = st.columns([1.2, 1], gap="medium")
        with purchase_left:
            st.markdown(
                """
                <div class="pc-mini-card" style="margin-bottom:0.85rem;">
                    <div class="pc-mini-title">Acquisition inputs</div>
                    <div class="pc-compact-note">Keep the live deal numbers tight here so funding, cash required, and stamp duty all stay in sync.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            purchase_col_1, purchase_col_2, purchase_col_3 = st.columns(3)
            purchase_col_1.number_input("Purchase price", key="price", min_value=0.0, step=1000.0)
            purchase_col_2.selectbox(
                "Deposit mode",
                ["Percent", "Dollar"],
                key="deposit_input_mode_input",
                on_change=sync_deposit_input_mode,
            )
            purchase_col_3.number_input("Deposit value", key="deposit_input_value", min_value=0.0)

            costs_col_1, costs_col_2, costs_col_3 = st.columns(3)
            costs_col_1.number_input("Stamp duty", key="stamp_duty", min_value=0.0)
            costs_col_2.number_input("Solicitor / conveyancer", key="solicitor_charge", min_value=0.0)
            costs_col_3.number_input("Inspection costs", key="inspection_costs", min_value=0.0)
            if str(st.session_state.get("stamp_duty_source_url", "")).strip():
                st.link_button("Open stamp duty source", str(st.session_state["stamp_duty_source_url"]), use_container_width=True)
            if str(st.session_state.get("stamp_duty_message", "")).strip():
                st.caption(str(st.session_state["stamp_duty_message"]))

        with purchase_right:
            st.markdown(
                """
                <div class="pc-mini-card" style="margin-bottom:0.85rem;">
                    <div class="pc-mini-title">Market references</div>
                    <div class="pc-compact-note">Keep your target buy number beside the visible SOI and REA ranges so the price decision stays anchored.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.number_input("Property value", key="property_value", min_value=0.0)
            ref_col_1, ref_col_2 = st.columns(2)
            ref_col_1.number_input("SOI price low", key="statement_price_low", min_value=0.0)
            ref_col_2.number_input("SOI price high", key="statement_price_high", min_value=0.0)
            rea_ref_col_1, rea_ref_col_2 = st.columns(2)
            rea_ref_col_1.number_input("REA price low", key="listing_price_low", min_value=0.0)
            rea_ref_col_2.number_input("REA price high", key="listing_price_high", min_value=0.0)

    with tab_rent:
        st.markdown(
            """
            <div class="pc-card" style="margin-bottom:0.9rem;">
                <div class="pc-card-title">Income and holding costs</div>
                <div class="pc-meta">This tab is tuned for quick scanning: rent, allowances, rates, insurance, and growth assumptions are grouped together so you can stress-test inputs fast.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("Rent & holding costs")
        rent_col_1, rent_col_2 = st.columns(2)
        rent_col_1.number_input("Weekly rent", key="weekly_rent", min_value=0.0)
        rent_col_2.number_input("Vacancy allowance (%)", key="vacancy_allowance_pct", min_value=0.0)

        growth_col_1, growth_col_2, growth_col_3 = st.columns(3)
        growth_col_1.number_input("Maintenance allowance (%)", key="maintenance_allowance_pct", min_value=0.0)
        growth_col_2.number_input("Rent growth (%)", key="rent_growth_pct", min_value=0.0)
        growth_col_3.number_input("Expense inflation (%)", key="expense_inflation_pct", min_value=0.0)
        st.number_input("Property growth (%)", key="property_growth_pct", min_value=0.0)

        rates_col_1, rates_col_2, rates_col_3 = st.columns(3)
        rates_col_1.number_input("Council (quarterly)", key="council_quarterly", min_value=0.0)
        rates_col_1.number_input("Water (quarterly)", key="water_quarterly", min_value=0.0)
        rates_col_2.number_input("Strata (quarterly)", key="strata_quarterly", min_value=0.0)
        rates_col_2.number_input("Building insurance (annual)", key="building_insurance_annual", min_value=0.0)
        rates_col_3.number_input("Landlord insurance (annual)", key="landlord_insurance_annual", min_value=0.0)
        rates_col_3.number_input("Property manager rate (%)", key="property_manager_rate", min_value=0.0)

    with tab_finance:
        st.markdown(
            """
            <div class="pc-card" style="margin-bottom:0.9rem;">
                <div class="pc-card-title">Funding structure</div>
                <div class="pc-meta">Use this as your analyst workspace for loan sizing, repayment type, and debt sensitivity. Blank loan terms still default to 30 years for P+I calculations.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("Funding & loans")
        st.selectbox("Deposit source", ["Cash", "Equity"], key="deposit_source_input")
        funding_message = suggested_funding_message(
            as_number(st.session_state.get("price")),
            resolve_deposit_values(
                as_number(st.session_state.get("price")),
                str(st.session_state.get("deposit_input_mode_input", "Percent")),
                st.session_state.get("deposit_input_value"),
            )[1],
            as_number(st.session_state.get("stamp_duty"))
            + as_number(st.session_state.get("solicitor_charge"))
            + as_number(st.session_state.get("inspection_costs")),
            str(st.session_state.get("deposit_source_input", "Cash")),
        )
        st.markdown(
            f"""
            <div class="pc-mini-card" style="margin-bottom:0.85rem;">
                <div class="pc-mini-title">Funding note</div>
                <div class="pc-compact-note">{funding_message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        finance_left, finance_right = st.columns([1.25, 1], gap="medium")
        with finance_left:
            for mortgage_number in (1, 2, 3):
                st.markdown(f"**Loan {mortgage_number}**")
                loan_col_1, loan_col_2, loan_col_3, loan_col_4 = st.columns(4)
                loan_col_1.number_input("Amount", key=f"mortgage_{mortgage_number}_amount", min_value=0.0)
                loan_col_2.number_input("Rate (%)", key=f"mortgage_{mortgage_number}_rate", min_value=0.0)
                loan_col_3.number_input("Term (years)", key=f"mortgage_{mortgage_number}_years", min_value=0.0)
                loan_col_4.selectbox("Type", ["P+I", "I only"], key=f"mortgage_{mortgage_number}_repayment_type_input")
            st.number_input("Annual borrowing / package costs", key="annual_borrowing_costs", min_value=0.0)

        with finance_right:
            st.markdown("#### Management, tax, and risk")
            tax_col_1, tax_col_2 = st.columns(2)
            tax_col_1.number_input("Depreciation estimate", key="depreciation_estimate", min_value=0.0)
            tax_col_2.number_input("Income", key="income", min_value=0.0)
            st.number_input("Income tax rate (%)", key="income_tax_rate", min_value=0.0)

            risk_col_1, risk_col_2 = st.columns(2)
            with risk_col_1:
                st.slider("Vacancy risk", 1, 10, key="vacancy_risk")
                st.slider("Liquidity risk", 1, 10, key="liquidity_risk")
                st.slider("Finance difficulty", 1, 10, key="finance_difficulty")
                st.slider("Body corporate risk", 1, 10, key="body_corporate_risk")
            with risk_col_2:
                st.slider("Regional risk", 1, 10, key="regional_risk")
                st.slider("Special levy risk", 1, 10, key="special_levy_risk")
                st.slider("Capital growth potential", 1, 10, key="capital_growth_potential")
                st.slider("Tenant demand", 1, 10, key="tenant_demand")

    with tab_analysis:
        st.button("Calculate", type="primary", on_click=run_calculation)
        if st.session_state.has_calculated:
            calculated_payload = dict(st.session_state.calculated_payload)
            metrics = calculate_metrics(calculated_payload)
            render_top_summary(metrics)
            overview_col, recommendation_col = st.columns([1.45, 1], gap="medium")
            with overview_col:
                render_property_card(calculated_payload)
                render_metrics_grid(metrics)
            with recommendation_col:
                render_recommendation_card(metrics)
            st.divider()
            render_charts(metrics, calculated_payload)
            render_tables(metrics, calculated_payload)
        else:
            st.info("Enter the property details, then click Calculate to generate the feasibility values.")

    with tab_final_summary:
        if st.session_state.has_calculated:
            calculated_payload = dict(st.session_state.calculated_payload)
            metrics = calculate_metrics(calculated_payload)
            render_final_summary_page(calculated_payload, metrics)
        else:
            st.info("Calculate the feasibility first to open the final summary page.")

    with tab_export:
        st.subheader("Save / Export")
        st.text_input("Save name", key="save_name_input_export")
        if st.button("Save property", use_container_width=True):
            export_payload = save_ready_payload()
            save_name = str(st.session_state.get("save_name_input_export", "")).strip() or str(
                export_payload.get("property_address") or "Property"
            ).strip()
            if save_name:
                save_property(
                    name=save_name,
                    address=str(export_payload.get("property_address") or ""),
                    state=parse_state_from_address(str(export_payload.get("property_address") or "")),
                    payload=export_payload,
                )
                queue_payload_apply(export_payload, save_name, preserve_calculation=True)
                st.rerun()
            else:
                st.error("Add a save name or property address first.")

        st.divider()
        st.subheader("Export PDF")
        if st.session_state.has_calculated:
            render_pdf_download(
                dict(st.session_state.calculated_payload),
                calculate_metrics(dict(st.session_state.calculated_payload)),
                button_key="pdf_download_export",
            )
        else:
            st.info("Calculate the feasibility first to export the property report.")


def render_sidebar(saved_properties: List[Dict[str, Any]]) -> None:
    with st.sidebar:
        st.radio(
            "Workspace",
            options=["Property workspace", "Portfolio screener"],
            key="active_page",
            horizontal=False,
        )
        state_groups = grouped_properties(saved_properties)
        favorite_count = sum(1 for item in saved_properties if bool(item.get("is_favorite")))
        st.markdown(
            f"""
            <div class="pc-sidebar-card">
                <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#5f6f85;font-weight:700;">Portfolio browser</div>
                <div style="font-size:1.35rem;font-weight:800;color:#0f172a;letter-spacing:-0.03em;">Saved Properties</div>
                <div style="font-size:0.85rem;color:#5f6f85;">Search, load, and compare saved deals from a denser left-nav workspace.</div>
                <div class="pc-sidebar-stat-row">
                    <div class="pc-sidebar-stat"><span>Deals</span><strong>{len(saved_properties)}</strong></div>
                    <div class="pc-sidebar-stat"><span>States</span><strong>{len(state_groups)}</strong></div>
                    <div class="pc-sidebar-stat"><span>Favs</span><strong>{favorite_count}</strong></div>
                    <div class="pc-sidebar-stat"><span>Active</span><strong>{1 if st.session_state.loaded_property_name else 0}</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state.get("save_name_input", "") != st.session_state.save_name:
            st.session_state.save_name_input = st.session_state.save_name
        st.text_input("Save name", key="save_name_input")
        st.session_state.save_name = str(st.session_state.save_name_input)

        save_col, reset_col = st.columns(2)
        with save_col:
            if st.button("Save", use_container_width=True):
                sidebar_payload = save_ready_payload()
                save_name = str(st.session_state.save_name_input).strip() or str(
                    sidebar_payload["property_address"]
                ).strip()
                if save_name:
                    save_property(
                        name=save_name,
                        address=str(sidebar_payload["property_address"]),
                        state=parse_state_from_address(str(sidebar_payload["property_address"])),
                        payload=sidebar_payload,
                    )
                    queue_payload_apply(sidebar_payload, save_name, preserve_calculation=True)
                    st.rerun()
                else:
                    st.error("Add a save name or property address first.")
        with reset_col:
            if st.button("New", use_container_width=True, on_click=reset_to_defaults):
                st.rerun()

        if st.session_state.loaded_property_name:
            st.markdown(
                f"""
                <div class="pc-sidebar-card">
                    <div class="pc-mini-title">Loaded property</div>
                    <div style="font-size:0.95rem;font-weight:700;color:#0f172a;">{st.session_state.loaded_property_name}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Delete loaded", use_container_width=True, on_click=delete_loaded_property_and_reset):
                st.rerun()

        st.divider()
        if not saved_properties:
            st.info("No saved properties yet.")
            return

        st.text_input("Search saved properties", key="saved_property_filter", placeholder="Search by name or address")
        property_filter = str(st.session_state.get("saved_property_filter", "")).strip().lower()
        filtered_groups: Dict[str, List[Dict[str, Any]]] = {}
        for state, items in state_groups.items():
            matching_items = [
                item for item in items
                if not property_filter
                or property_filter in str(item["name"]).lower()
                or property_filter in str(item["address"]).lower()
            ]
            if matching_items:
                filtered_groups[state] = matching_items

        if not filtered_groups:
            st.info("No saved properties match that search.")
            return

        favorite_items = [
            item for item in saved_properties
            if bool(item.get("is_favorite"))
            and (
                not property_filter
                or property_filter in str(item["name"]).lower()
                or property_filter in str(item["address"]).lower()
            )
        ]
        if favorite_items:
            with st.expander(f"Favorites ({len(favorite_items)})", expanded=True):
                for item in favorite_items:
                    render_saved_property_row(item, "favorites")

        for state, items in filtered_groups.items():
            with st.expander(f"{state} ({len(items)})", expanded=state == str(parse_state_from_address(str(st.session_state.get('property_address', ''))))):
                for item in items:
                    render_saved_property_row(item, f"state_{state}")


def render_inputs() -> tuple[Dict[str, float | str], bool, bool]:
    render_table_styles()

    section_title("REA Listing Import")
    st.markdown("**Import from link**")
    st.text_input(
        "realestate.com.au listing URL",
        key="listing_url_input",
        placeholder="https://www.realestate.com.au/property-...",
    )
    import_col, open_col = st.columns(2)
    import_col.button(
        "Try link import",
        on_click=run_listing_import,
        args=("link",),
        use_container_width=True,
    )
    listing_url = str(st.session_state.get("listing_url_input", "")).strip()
    if listing_url.startswith(("https://www.realestate.com.au/", "http://www.realestate.com.au/")):
        open_col.link_button("Open REA listing", listing_url, use_container_width=True)

    st.markdown("**Import from copied listing details**")
    st.caption(
        "On phone or desktop: open the REA listing, copy the address, price and property details, "
        "then paste them below. Labels such as 3 beds, 2 baths and 1 parking are detected automatically."
    )
    st.text_area(
        "Copied REA listing details",
        key="listing_text_input",
        height=180,
        placeholder=(
            "Paste copied listing details here\n\n"
            "Example: 44/66 Julia Street, Portland VIC 3305 | $239,900 | "
            "3 bedrooms | 2 bathrooms | 1 parking space"
        ),
    )
    paste_col, clear_col = st.columns([3, 1])
    paste_col.button(
        "Import pasted details",
        on_click=run_listing_import,
        args=("paste",),
        type="primary",
        use_container_width=True,
    )
    clear_col.button("Clear", on_click=clear_listing_text, use_container_width=True)

    listing_import_message = str(st.session_state.get("listing_import_message", "")).strip()
    if listing_import_message:
        if "blocked" in listing_import_message.lower():
            st.warning(listing_import_message)
        elif "imported" in listing_import_message.lower():
            st.success(listing_import_message)
        else:
            st.info(listing_import_message)

    section_title("Address Finder")
    st.text_input("Address finder", key="address_search_query")
    finder_col, use_col = st.columns(2)
    finder_col.button("Find address", on_click=run_address_finder, use_container_width=True)
    if st.session_state.address_search_results:
        options = [str(item["formatted_address"]) for item in st.session_state.address_search_results]
        if st.session_state.selected_address not in options:
            st.session_state.selected_address = options[0]
        st.selectbox("Address matches", options=options, key="selected_address")
        use_col.button("Use selected address", on_click=apply_selected_address, use_container_width=True)
    if str(st.session_state.address_finder_message).strip():
        st.caption(str(st.session_state.address_finder_message))

    st.markdown("**Verified Statement of Information (VIC)**")
    st.caption(
        "Automatic REA lookup is accepted only when the source document matches the exact property address. "
        "If REA blocks it, download the Statement of Information PDF from the listing and upload it here."
    )
    st.file_uploader(
        "REA Statement of Information PDF",
        type=["pdf"],
        key="soi_pdf_upload",
        help="The PDF must contain the same address selected for this property and be no larger than 10 MB.",
    )
    soi_search_col, soi_import_col = st.columns(2)
    soi_search_col.button(
        "Search verified REA SOI",
        on_click=fetch_statement_price_range,
        args=(True,),
        use_container_width=True,
    )
    soi_import_col.button(
        "Import verified SOI PDF",
        on_click=import_uploaded_soi,
        use_container_width=True,
    )
    if str(st.session_state.statement_lookup_message).strip():
        message = str(st.session_state.statement_lookup_message)
        if message.startswith("Verified"):
            st.success(message)
        else:
            st.info(message)

    editor_sections = input_editor_sections()
    facts_rows = editor_sections["facts_editor"]
    purchase_rows = editor_sections["purchase_editor"]
    rent_rates_rows = editor_sections["rent_rates_editor"]
    finance_rows = editor_sections["finance_editor"]
    tax_rows = editor_sections["tax_editor"]

    split_clicked = False
    calculate_clicked = False
    with st.form("property_inputs_form", clear_on_submit=False):
        left_col, right_col = st.columns(2, gap="medium")
        with left_col:
            render_editable_section("Property Details", "facts_editor", facts_rows)
            st.checkbox("Property sold", key="is_sold")
            st.markdown("**Purchase**")
            render_table_like_select_row("Deposit input", "deposit_input_mode_input", ["Percent", "Dollar"])
            render_editable_section("", "purchase_editor", purchase_rows, show_title=False)
            if str(st.session_state.statement_source_url).strip():
                st.link_button("Open SOI link", st.session_state.statement_source_url, use_container_width=True)
                st.text_input("SOI link", value=str(st.session_state.statement_source_url), disabled=True)
            if str(st.session_state.stamp_duty_message).strip():
                st.caption(str(st.session_state.stamp_duty_message))
            render_editable_section("Rent & Rates", "rent_rates_editor", rent_rates_rows)

        with right_col:
            st.selectbox("Deposit source", options=["Cash", "Equity"], key="deposit_source_input")
            repayment_type_cols = st.columns(3)
            repayment_type_cols[0].selectbox(
                "Mortgage 1 type",
                options=["P+I", "I only"],
                key="mortgage_1_repayment_type_input",
            )
            repayment_type_cols[1].selectbox(
                "Mortgage 2 type",
                options=["P+I", "I only"],
                key="mortgage_2_repayment_type_input",
            )
            repayment_type_cols[2].selectbox(
                "Mortgage 3 type",
                options=["P+I", "I only"],
                key="mortgage_3_repayment_type_input",
            )
            render_editable_section("Finance", "finance_editor", finance_rows)
            st.caption("For P+I loans, blank mortgage years default to 30 years. Choose I only to use interest-only repayments instead.")
            st.caption(
                "Suggested split uses deposit + buying costs for Mortgage 1 when deposit source is Equity, "
                "and the remaining purchase price for Mortgage 2."
            )
            render_editable_section("Management & Tax", "tax_editor", tax_rows)
            st.info("Income is kept as a reference field. Tax calculations use the manual tax-rate input above.")
            st.markdown("**Risk & Growth Assessment**")
            risk_left, risk_right = st.columns(2)
            with risk_left:
                st.slider("Vacancy risk", 1, 10, key="vacancy_risk")
                st.slider("Liquidity risk", 1, 10, key="liquidity_risk")
                st.slider("Finance difficulty", 1, 10, key="finance_difficulty")
                st.slider("Body corporate risk", 1, 10, key="body_corporate_risk")
            with risk_right:
                st.slider("Regional risk", 1, 10, key="regional_risk")
                st.slider("Special levy risk", 1, 10, key="special_levy_risk")
                st.slider("Capital growth potential", 1, 10, key="capital_growth_potential")
                st.slider("Tenant demand", 1, 10, key="tenant_demand")
            st.caption("Risk inputs: 1 is low risk and 10 is high risk. Growth potential and tenant demand: 10 is strongest.")

        payload = latest_input_payload(editor_sections)

        deposit_amount = resolve_deposit_values(
            as_number(payload["price"]),
            str(payload["deposit_input_mode"]),
            payload["deposit_input_value"],
        )[1]
        buying_costs = (
            as_number(payload["stamp_duty"])
            + as_number(payload["solicitor_charge"])
            + as_number(payload["inspection_costs"])
        )
        suggested = suggested_loan_split(
            as_number(payload["price"]),
            deposit_amount,
            buying_costs,
            str(st.session_state.deposit_source_input),
        )
        funding_message = suggested_funding_message(
            as_number(payload["price"]),
            deposit_amount,
            buying_costs,
            str(st.session_state.deposit_source_input),
        )

        action_col, calc_col = st.columns(2)
        with action_col:
            split_clicked = st.form_submit_button("Use suggested funding split", use_container_width=True)
        with calc_col:
            calculate_clicked = st.form_submit_button("Calculate", type="primary", use_container_width=True)
        st.caption(funding_message)

    if not st.session_state.save_name.strip():
        st.session_state.save_name = str(payload["property_address"])

    if split_clicked:
        update_editor_draft_values(
            "finance_editor",
            finance_rows,
            {
                "mortgage_1_amount": suggested["mortgage_1_amount"],
                "mortgage_2_amount": suggested["mortgage_2_amount"],
                "mortgage_3_amount": suggested["mortgage_3_amount"],
            },
        )
        st.session_state.deposit_input_mode = str(payload["deposit_input_mode"])

    return payload, calculate_clicked, split_clicked


def render_summary(metrics: Dict[str, float | str | List[Loan]]) -> None:
    row_one = st.columns(4)
    row_one[0].metric("Pre-tax cash flow (yearly)", currency(float(metrics["pre_tax_cashflow"])))
    row_one[1].metric("Post-tax cash flow (yearly)", currency(float(metrics["after_tax_cashflow"])))
    row_one[2].metric("Gross yield", pct(float(metrics["gross_yield"])))
    row_one[3].metric("Cash flow", str(metrics["cashflow_label"]))

    row_two = st.columns(5)
    row_two[0].metric("Net yield before interest", pct(float(metrics["net_yield_before_interest"])))
    row_two[1].metric("Net yield after interest", pct(float(metrics["net_yield_after_interest"])))
    row_two[2].metric("Cash required upfront", currency(float(metrics["cash_required_upfront"])))
    row_two[3].metric("Total borrowings", currency(float(metrics["total_borrowings"])))
    row_two[4].metric("Break-even rent", f"{currency(float(metrics['break_even_rent_weekly']))}/wk")

    if abs(float(metrics["funding_gap"])) >= 1:
        if float(metrics["funding_gap"]) > 0:
            st.warning(f"Funding gap detected: {currency(float(metrics['funding_gap']))} still needs to be funded.")
        else:
            st.success(f"Funding surplus detected: {currency(abs(float(metrics['funding_gap'])))} above the required deal funds.")


def property_fact(value: Any, suffix: str = "") -> str:
    number = as_number(value)
    if number <= 0:
        return "-"
    display = str(int(number)) if number.is_integer() else f"{number:g}"
    return f"{display}{suffix}"


def render_property_overview(payload: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    with st.container(border=True):
        heading_col, price_col, rent_col = st.columns([2, 1, 1])
        with heading_col:
            st.markdown(f"### {str(payload.get('property_address') or 'Property details')} ")
            facts = " | ".join(
                [
                    str(payload.get("property_type") or "Property type not set"),
                    f"{property_fact(payload.get('bedrooms'))} bed",
                    f"{property_fact(payload.get('bathrooms'))} bath",
                    f"{property_fact(payload.get('car_spaces'))} car",
                ]
            )
            st.caption(facts)
            locality = " ".join(
                part
                for part in [
                    str(payload.get("suburb") or ""),
                    str(payload.get("property_state") or ""),
                    str(payload.get("postcode") or ""),
                ]
                if part
            )
            if locality:
                st.caption(locality)
        price_col.metric("Purchase price", currency(as_number(payload.get("price"))))
        rent_col.metric("Estimated rent", f"{currency(as_number(payload.get('weekly_rent')))}/wk")

        summary = str(payload.get("listing_summary") or "").strip()
        if summary:
            st.caption(summary)
        listing_url = str(payload.get("listing_url") or "").strip()
        if listing_url.startswith(("https://", "http://")):
            st.link_button("Open realestate.com.au listing", listing_url)


def render_recommendation(metrics: Dict[str, Any]) -> None:
    recommendation = str(metrics.get("recommendation", "INCOMPLETE"))
    score_line = f"{recommendation} - overall investment score {float(metrics.get('overall_score', 0.0)):.1f}/10"
    if recommendation == "BUY":
        st.success(score_line)
    elif recommendation == "WATCH":
        st.warning(score_line)
    elif recommendation == "AVOID":
        st.error(score_line)
    else:
        st.info("Add a purchase price and rent to generate a recommendation.")

    score_cols = st.columns(4)
    score_cols[0].metric("Risk score", f"{float(metrics.get('risk_score', 0.0)):.1f}/10", help="Lower is better")
    score_cols[1].metric("Growth score", f"{float(metrics.get('growth_score', 0.0)):.1f}/10")
    score_cols[2].metric("Yield score", f"{float(metrics.get('yield_score', 0.0)):.1f}/10")
    score_cols[3].metric("Overall score", f"{float(metrics.get('overall_score', 0.0)):.1f}/10")
    for reason in metrics.get("recommendation_reasons", []):
        st.markdown(f"- {reason}")


def render_pdf_download(payload: Dict[str, Any], metrics: Dict[str, Any], button_key: str = "pdf_download") -> None:
    loans = list(metrics.get("loans", []))
    loan_schedules = [amortization_schedule(loan) for loan in loans]
    comparison = deposit_comparison_table(payload)
    projection = five_year_projection(payload, metrics)
    try:
        current_pdf_report = importlib.reload(pdf_report)
        pdf_data = current_pdf_report.build_property_report(
            payload,
            metrics,
            loan_schedules,
            comparison,
            projection,
        )
    except Exception as exc:
        st.error(f"PDF report could not be generated: {exc}")
        return

    download_col, _ = st.columns([1, 3])
    with download_col:
        st.download_button(
            "Export property report (PDF)",
            data=pdf_data,
            file_name=current_pdf_report.report_filename(str(payload.get("property_address") or "property")),
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key=button_key,
        )


def render_charts(metrics: Dict[str, float | str | List[Loan]], payload: Dict[str, float | str]) -> None:
    cashflow_df = annual_expense_table(metrics, payload)
    chart_df = cashflow_df[
        ~cashflow_df["Category"].isin(["Pre-tax cash flow", "Estimated tax effect", "After-tax cash flow"])
    ].copy()
    chart_df["Direction"] = chart_df["Annual amount"].apply(lambda value: "Income" if value >= 0 else "Cost")

    fig = px.bar(
        chart_df,
        x="Category",
        y="Annual amount",
        color="Direction",
        color_discrete_map={"Income": "#0f766e", "Cost": "#b91c1c"},
        title="Annual cash flow components",
    )
    fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Annual amount ($)")
    st.plotly_chart(fig, use_container_width=True)


def render_projection(payload: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    projection = five_year_projection(payload, metrics)
    value_chart = px.line(
        projection,
        x="Year",
        y=["Property value", "Loan balance", "Estimated equity"],
        markers=True,
        title="Five-year property value, debt and equity projection",
        color_discrete_map={
            "Property value": "#07859d",
            "Loan balance": "#c2410c",
            "Estimated equity": "#0f766e",
        },
    )
    value_chart.update_layout(hovermode="x unified", legend_title_text="", yaxis_title="AUD")
    value_chart.update_yaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(value_chart, width="stretch")

    cashflow_chart = px.bar(
        projection[projection["Year"] > 0],
        x="Year",
        y=["Pre-tax cash flow", "After-tax cash flow"],
        barmode="group",
        title="Projected annual cash flow",
        color_discrete_map={"Pre-tax cash flow": "#07859d", "After-tax cash flow": "#0f766e"},
    )
    cashflow_chart.update_layout(legend_title_text="", yaxis_title="AUD")
    cashflow_chart.update_yaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(cashflow_chart, width="stretch")

    monetary_columns = [column for column in projection.columns if column != "Year"]
    st.dataframe(
        projection.style.format({column: currency for column in monetary_columns}),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Projection uses the entered rent growth, expense inflation and property growth assumptions. "
        "It is an indicative scenario, not a valuation forecast."
    )


def render_risk_analysis(payload: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    render_recommendation(metrics)
    risk_rows = [
        ["Vacancy risk", payload.get("vacancy_risk"), "Lower is better"],
        ["Liquidity risk", payload.get("liquidity_risk"), "Lower is better"],
        ["Finance difficulty", payload.get("finance_difficulty"), "Lower is better"],
        ["Body corporate risk", payload.get("body_corporate_risk"), "Lower is better"],
        ["Regional risk", payload.get("regional_risk"), "Lower is better"],
        ["Special levy risk", payload.get("special_levy_risk"), "Lower is better"],
        ["Capital growth potential", payload.get("capital_growth_potential"), "Higher is better"],
        ["Tenant demand", payload.get("tenant_demand"), "Higher is better"],
    ]
    st.dataframe(
        pd.DataFrame(risk_rows, columns=["Assessment", "Input / 10", "Direction"]),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Overall score weighting: yield 35%, growth 25%, risk quality 25%, cash-flow strength 15%. "
        "BUY requires an overall score of at least 7, risk no higher than 6, and no material funding gap."
    )


def render_tables(metrics: Dict[str, float | str | List[Loan]], payload: Dict[str, float | str]) -> None:
    summary_tab, cashflow_tab, projection_tab, finance_tab, risk_tab, sensitivity_tab, deposit_tab, saved_tab = st.tabs(
        ["Deal summary", "Cash flow", "5-year projection", "Finance", "Risk & recommendation", "Sensitivity", "Deposit compare", "Saved compare"]
    )

    with summary_tab:
        cash_on_cash_value = (
            pct(float(metrics["cash_on_cash"])) if float(metrics["cash_required_upfront"]) else "n/a (equity funded)"
        )
        st.dataframe(
            acquisition_table(metrics).style.format({"Amount": currency}),
            use_container_width=True,
            hide_index=True,
        )
        summary_items = pd.DataFrame(
            [
                {"Metric": "Net yield before interest", "Value": pct(float(metrics["net_yield_before_interest"]))},
                {"Metric": "Net yield after interest", "Value": pct(float(metrics["net_yield_after_interest"]))},
                {"Metric": "Total debt ratio", "Value": pct(float(metrics["total_debt_ratio"]))},
                {"Metric": "Monthly pre-tax cash flow", "Value": currency(float(metrics["monthly_pre_tax_cashflow"]))},
                {"Metric": "Monthly after-tax cash flow", "Value": currency(float(metrics["monthly_after_tax_cashflow"]))},
                {"Metric": "Weekly pre-tax cash flow", "Value": currency(float(metrics["weekly_pre_tax_cashflow"]))},
                {"Metric": "Weekly after-tax cash flow", "Value": currency(float(metrics["weekly_after_tax_cashflow"]))},
                {"Metric": "Cash-on-cash return", "Value": cash_on_cash_value},
            ]
        )
        st.dataframe(summary_items, use_container_width=True, hide_index=True)

    with cashflow_tab:
        st.dataframe(
            annual_expense_table(metrics, payload).style.format({"Annual amount": currency}),
            use_container_width=True,
            hide_index=True,
        )

    with projection_tab:
        render_projection(payload, metrics)

    with finance_tab:
        st.dataframe(
            loan_table(metrics["loans"]).style.format(
                {
                    "Term (yrs)": "{:.0f}",
                    "Rate": "{:.2%}",
                    "Amount": currency,
                    "Annual repayment": currency,
                    "Annual interest": currency,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        render_amortization_charts(metrics["loans"])

    with risk_tab:
        render_risk_analysis(payload, metrics)

    with sensitivity_tab:
        sensitivity_df = sensitivity_table(payload)
        styled = sensitivity_df.style.format(
            {column: currency for column in sensitivity_df.columns if column != "Rate shift"}
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.caption("Sensitivity values show annual after-tax cash flow after changing rent and all loan rates.")

    with deposit_tab:
        comparison_df = deposit_comparison_table(payload)
        if comparison_df.empty:
            st.info("Enter a purchase price, then click Calculate to compare LVR scenarios.")
        else:
            st.dataframe(
                comparison_df.style.format(
                    {
                        "Deposit ($)": currency,
                        "Base loan ($)": currency,
                        "Indicative LMI ($)": currency,
                        "Loan incl. LMI ($)": currency,
                        "Actual LVR incl. LMI": "{:.1f}%",
                        "Cash upfront ($)": currency,
                        "Annual interest ($)": currency,
                        "Pre-tax cash flow ($)": currency,
                        "After-tax cash flow ($)": currency,
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Assumes the deposit is funded in cash and any LMI is capitalised into the main loan for comparison purposes."
            )
            st.caption(
                "Indicative LMI only: Helia says LMI generally applies below a 20% deposit and is typically around 1% to 2% "
                f"of the loan, but the actual premium varies by lender, borrower, and property. [Helia LMI estimator]({LMI_SOURCE_URL})"
            )

    with saved_tab:
        comparison = saved_property_comparison_table()
        if comparison.empty:
            st.info("Save at least one calculated property to compare investment options.")
        else:
            st.dataframe(
                comparison.style.format(
                    {
                        "Price": currency,
                        "Weekly rent": currency,
                        "Gross yield": "{:.2f}%",
                        "Net yield": "{:.2f}%",
                        "Pre-tax cash flow": currency,
                        "Cash required": currency,
                        "Risk / 10": "{:.1f}",
                        "Overall / 10": "{:.1f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


def main() -> None:
    st.set_page_config(page_title="Property Scout", page_icon="🏠", layout="wide")
    init_db()
    ensure_state()
    consume_pending_payload_apply()
    consume_pending_active_page()
    render_analyst_theme()

    saved_properties = list_properties()
    render_sidebar(saved_properties)

    st.markdown(
        """
        <div class="pc-shell">
            <div class="pc-page-title">Property Scout</div>
            <div class="pc-page-subtitle">
                Compact analyst workspace for screening Australian residential deals.
                Import the listing, verify the address and SOI, model the funding, then review the full feasibility pack.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if str(st.session_state.get("active_page", "Property workspace")) == "Portfolio screener":
        render_portfolio_screener_page(saved_properties)
    else:
        payload = current_payload()
        render_tabs(payload)


if __name__ == "__main__":
    main()
