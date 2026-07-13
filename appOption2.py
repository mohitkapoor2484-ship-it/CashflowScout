from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import re
import importlib
from dataclasses import dataclass
from typing import Any, Dict, List

from address_finder import find_addresses
from listing_import import import_rea_listing
from stamp_duty import calculate_stamp_duty
from statement_lookup import extract_statement_pdf, lookup_statement_of_information
from storage import init_db, save_property, load_property, delete_property, list_properties
import pdf_report

# ---------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------

WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
QUARTERS_PER_YEAR = 4

STATE_CODES = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"}

LMI_SOURCE_URL = "https://www.helia.com.au/the-hub/calculators-estimators/lmi-fee-estimator"

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

# ---------------------------------------------------------
# LOAN CLASS
# ---------------------------------------------------------

@dataclass
class Loan:
    name: str
    rate_pct: float
    amount: float
    term_years: float
    repayment_type: str

    @property
    def annual_interest(self) -> float:
        return max(self.amount, 0) * max(self.rate_pct, 0) / 100

    @property
    def effective_term_years(self) -> float:
        return max(self.term_years or 30, 0)

    @property
    def annual_repayment(self) -> float:
        amount = max(self.amount, 0)
        rate = max(self.rate_pct, 0)
        if self.repayment_type == "I only":
            return self.annual_interest

        if amount <= 0:
            return 0

        if rate <= 0:
            return amount / self.effective_term_years

        monthly_rate = rate / 100 / 12
        n = int(self.effective_term_years * 12)
        monthly = amount * monthly_rate / (1 - (1 + monthly_rate) ** -n)
        return monthly * 12
# ---------------------------------------------------------
# SESSION STATE INITIALISATION
# ---------------------------------------------------------

def ensure_state():
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

    st.session_state.setdefault("has_calculated", False)
    st.session_state.setdefault("calculated_payload", {})

    st.session_state.setdefault("stamp_duty_auto_signature", "")


# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def as_number(v):
    try:
        return float(v)
    except:
        return 0.0

def safe_divide(a, b):
    return a / b if b else 0.0

def currency(v):
    if v is None:
        return "$0"
    try:
        v = float(v)
    except:
        return "$0"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"

def property_fact(v):
    if v is None:
        return "-"
    try:
        if float(v).is_integer():
            return str(int(v))
        return str(v)
    except:
        return str(v)


# ---------------------------------------------------------
# ADDRESS PARSING
# ---------------------------------------------------------

def parse_state_from_address(address: str) -> str:
    parts = re.split(r"[ ,]+", address.upper())
    for p in reversed(parts):
        if p in STATE_CODES:
            return p
    return ""

def should_resolve_address(address: str) -> bool:
    has_state = parse_state_from_address(address) in STATE_CODES
    has_postcode = bool(re.search(r"\b\d{4}\b", address))
    return not (has_state and has_postcode)

def resolve_property_address(address: str) -> str:
    if not should_resolve_address(address):
        return address
    results = find_addresses(address, limit=1)
    if not results:
        return address
    return results[0]["formatted_address"]

def address_components(address: str):
    state = parse_state_from_address(address)
    postcode_match = re.search(r"\b(\d{4})\b", address)
    postcode = postcode_match.group(1) if postcode_match else ""
    parts = address.split(",")
    suburb = parts[-2].strip().title() if len(parts) >= 2 else ""
    return {
        "suburb": suburb,
        "property_state": state,
        "postcode": postcode,
    }

def apply_address_components(address: str):
    comps = address_components(address)
    for k, v in comps.items():
        if v:
            st.session_state[k] = v


# ---------------------------------------------------------
# ADDRESS FINDER
# ---------------------------------------------------------

def run_address_finder():
    q = st.session_state.address_search_query.strip()
    st.session_state.address_finder_message = ""
    st.session_state.address_search_results = []
    st.session_state.selected_address = ""

    if not q:
        st.session_state.address_finder_message = "Enter a suburb or address."
        return

    try:
        results = find_addresses(q)
    except Exception as e:
        st.session_state.address_finder_message = f"Error: {e}"
        return

    if not results:
        st.session_state.address_finder_message = "No matches found."
        return

    st.session_state.address_search_results = results
    st.session_state.selected_address = results[0]["formatted_address"]
    st.session_state.address_finder_message = f"{len(results)} match(es) found."


def apply_selected_address():
    addr = st.session_state.selected_address.strip()
    if not addr:
        return
    st.session_state.property_address = addr
    apply_address_components(addr)
    st.session_state.save_name = addr
    fetch_statement_price_range()
    refresh_stamp_duty()


# ---------------------------------------------------------
# LISTING IMPORT
# ---------------------------------------------------------

def run_listing_import(mode="link"):
    url = st.session_state.get("listing_url_input", "").strip()
    text = st.session_state.get("listing_text_input", "").strip()

    pasted = text if mode == "paste" else ""

    result = import_rea_listing(url, pasted)
    fields = result.get("fields", {})

    for k, v in fields.items():
        if k in DEFAULTS and v not in (None, ""):
            st.session_state[k] = v

    resolved_url = fields.get("listing_url") or url
    st.session_state.listing_url = resolved_url
    st.session_state.listing_url_input = resolved_url
    st.session_state.listing_text = text
    st.session_state.listing_import_message = result.get("message", "")

    addr = st.session_state.get("property_address", "").strip()
    if addr:
        apply_address_components(addr)
        st.session_state.save_name = addr
        fetch_statement_price_range()
        refresh_stamp_duty()


# ---------------------------------------------------------
# STATEMENT OF INFORMATION (SOI)
# ---------------------------------------------------------

def fetch_statement_price_range(force=False):
    addr = st.session_state.property_address.strip()
    if not addr:
        return

    if should_resolve_address(addr):
        try:
            resolved = resolve_property_address(addr)
            st.session_state.property_address = resolved
            addr = resolved
        except:
            pass

    state = parse_state_from_address(addr)
    if state != "VIC":
        st.session_state.statement_lookup_message = "SOI only applies to VIC."
        return

    try:
        result = lookup_statement_of_information(addr, st.session_state.listing_url)
    except Exception as e:
        st.session_state.statement_lookup_message = f"SOI lookup failed: {e}"
        return

    if not result["found"]:
        st.session_state.statement_lookup_message = result["message"]
        return

    st.session_state.statement_price_low = float(result["low"])
    st.session_state.statement_price_high = float(result["high"])
    st.session_state.statement_source_url = result["source_url"]
    st.session_state.statement_lookup_message = result["message"]

    midpoint = (float(result["low"]) + float(result["high"])) / 2
    st.session_state.price = midpoint
    st.session_state.property_value = midpoint
    refresh_stamp_duty()


def import_uploaded_soi():
    uploaded = st.session_state.get("soi_pdf_upload")
    if not uploaded:
        st.session_state.statement_lookup_message = "Upload a PDF first."
        return

    addr = st.session_state.property_address.strip()
    result = extract_statement_pdf(uploaded.getvalue(), addr, uploaded.name)
    st.session_state.statement_lookup_message = result["message"]

    if not result["found"]:
        return

    st.session_state.statement_price_low = float(result["low"])
    st.session_state.statement_price_high = float(result["high"])
    st.session_state.statement_source_url = ""

    midpoint = (float(result["low"]) + float(result["high"])) / 2
    st.session_state.price = midpoint
    st.session_state.property_value = midpoint
    refresh_stamp_duty()


# ---------------------------------------------------------
# STAMP DUTY
# ---------------------------------------------------------

def refresh_stamp_duty():
    price = as_number(st.session_state.price)
    addr = st.session_state.property_address.strip()
    if price <= 0 or not addr:
        st.session_state.stamp_duty = None
        st.session_state.stamp_duty_message = ""
        return

    result = calculate_stamp_duty(price, addr)
    st.session_state.stamp_duty = result["duty"] if result["supported"] else None
    st.session_state.stamp_duty_source_url = result["source_url"]
    st.session_state.stamp_duty_message = result["message"]


# ---------------------------------------------------------
# DEPOSIT LOGIC
# ---------------------------------------------------------

def resolve_deposit_values(price, mode, value):
    value = as_number(value)
    if mode == "Dollar":
        deposit_amount = value
        deposit_pct = safe_divide(value, price) * 100 if price else 0
    else:
        deposit_pct = value
        deposit_amount = price * deposit_pct / 100
    return deposit_pct, deposit_amount

def sync_deposit_input_mode():
    old = st.session_state.deposit_input_mode
    new = st.session_state.deposit_input_mode_input
    if old == new:
        return

    price = as_number(st.session_state.price)
    source_value = st.session_state.deposit_input_value
    pct, amt = resolve_deposit_values(price, old, source_value)

    if new == "Dollar":
        st.session_state.deposit_input_value = amt
    else:
        st.session_state.deposit_input_value = pct

    st.session_state.deposit_input_mode = new


# ---------------------------------------------------------
# MAIN METRICS ENGINE
# ---------------------------------------------------------

def calculate_metrics(payload: dict):
    price = as_number(payload["price"])
    deposit_pct, deposit_amount = resolve_deposit_values(
        price,
        payload["deposit_input_mode"],
        payload["deposit_input_value"],
    )

    stamp = as_number(payload["stamp_duty"])
    solicitor = as_number(payload["solicitor_charge"])
    inspect = as_number(payload["inspection_costs"])
    buying_costs = stamp + solicitor + inspect

    weekly_rent = as_number(payload["weekly_rent"])
    annual_rent = weekly_rent * WEEKS_PER_YEAR

    vacancy = annual_rent * as_number(payload["vacancy_allowance_pct"]) / 100
    effective_rent = annual_rent - vacancy

    council = as_number(payload["council_quarterly"]) * 4
    water = as_number(payload["water_quarterly"]) * 4
    strata = as_number(payload["strata_quarterly"]) * 4
    insurance = as_number(payload["building_insurance_annual"]) + as_number(payload["landlord_insurance_annual"])
    maintenance = annual_rent * as_number(payload["maintenance_allowance_pct"]) / 100
    pm_fee = effective_rent * as_number(payload["property_manager_rate"]) / 100

    fixed_costs = council + water + strata + insurance
    operating_expenses = fixed_costs + maintenance + pm_fee

    loans = [
        Loan("Loan 1", as_number(payload["mortgage_1_rate"]), as_number(payload["mortgage_1_amount"]),
             as_number(payload["mortgage_1_years"]), payload["mortgage_1_repayment_type"]),
        Loan("Loan 2", as_number(payload["mortgage_2_rate"]), as_number(payload["mortgage_2_amount"]),
             as_number(payload["mortgage_2_years"]), payload["mortgage_2_repayment_type"]),
        Loan("Loan 3", as_number(payload["mortgage_3_rate"]), as_number(payload["mortgage_3_amount"]),
             as_number(payload["mortgage_3_years"]), payload["mortgage_3_repayment_type"]),
    ]

    total_interest = sum(l.annual_interest for l in loans)
    total_repayments = sum(l.annual_repayment for l in loans)

    annual_borrowing_costs = as_number(payload["annual_borrowing_costs"])

    total_cash_expenses = (
        vacancy + operating_expenses + annual_borrowing_costs + total_repayments
    )

    pre_tax_cf = annual_rent - total_cash_expenses

    taxable = effective_rent - (operating_expenses + annual_borrowing_costs + total_interest + as_number(payload["depreciation_estimate"]))
    tax_effect = -taxable * as_number(payload["income_tax_rate"]) / 100
    after_tax_cf = pre_tax_cf + tax_effect

    property_value = as_number(payload["property_value"]) or price
    gross_yield = safe_divide(annual_rent, property_value) * 100
    net_yield_pre = safe_divide(effective_rent - operating_expenses, property_value) * 100
    net_yield_post = safe_divide(effective_rent - operating_expenses - total_interest, property_value) * 100

    total_borrowings = sum(l.amount for l in loans)
    debt_ratio = safe_divide(total_borrowings, property_value) * 100

    break_even = safe_divide(
        fixed_costs + annual_borrowing_costs + total_repayments,
        WEEKS_PER_YEAR * max(0.01, (1 - as_number(payload["vacancy_allowance_pct"]) / 100)),
    )

    risk_inputs = [
        as_number(payload["vacancy_risk"]),
        as_number(payload["liquidity_risk"]),
        as_number(payload["finance_difficulty"]),
        as_number(payload["body_corporate_risk"]),
        as_number(payload["regional_risk"]),
        as_number(payload["special_levy_risk"]),
    ]
    risk_score = sum(risk_inputs) / len(risk_inputs)

    growth_score = (
        as_number(payload["capital_growth_potential"]) * 0.65 +
        as_number(payload["tenant_demand"]) * 0.35
    )

    yield_score = min(max(net_yield_pre * 1.5, 0), 10)
    cashflow_margin = safe_divide(pre_tax_cf, annual_rent) * 100 if annual_rent else -10
    cashflow_score = min(max(5 + cashflow_margin / 2, 0), 10)

    overall = (
        yield_score * 0.35 +
        growth_score * 0.25 +
        (10 - risk_score) * 0.25 +
        cashflow_score * 0.15
    )

    if price <= 0 or annual_rent <= 0:
        rec = "INCOMPLETE"
    elif overall >= 7 and risk_score <= 6:
        rec = "BUY"
    elif overall >= 5:
        rec = "WATCH"
    else:
        rec = "AVOID"

    reasons = [
        f"Net yield before interest: {net_yield_pre:.2f}%",
        f"Annual pre‑tax cashflow: {currency(pre_tax_cf)}",
    ]
    if risk_score > 6:
        reasons.append(f"Risk score high: {risk_score:.1f}/10")
    if growth_score >= 7:
        reasons.append(f"Strong growth score: {growth_score:.1f}/10")

    return {
        "annual_rent": annual_rent,
        "effective_rent": effective_rent,
        "vacancy": vacancy,
        "operating_expenses": operating_expenses,
        "total_interest": total_interest,
        "total_repayments": total_repayments,
        "pre_tax_cashflow": pre_tax_cf,
        "after_tax_cashflow": after_tax_cf,
        "gross_yield": gross_yield,
        "net_yield_before_interest": net_yield_pre,
        "net_yield_after_interest": net_yield_post,
        "total_borrowings": total_borrowings,
        "total_debt_ratio": debt_ratio,
        "break_even_rent_weekly": break_even,
        "cashflow_label": (
            "Positive cashflow" if pre_tax_cf > 0 else
            "Neutral cashflow" if pre_tax_cf == 0 else
            "Negative cashflow"
        ),
        "risk_score": risk_score,
        "growth_score": growth_score,
        "yield_score": yield_score,
        "cashflow_score": cashflow_score,
        "overall_score": overall,
        "recommendation": rec,
        "recommendation_reasons": reasons,
        "loans": loans,
        "cash_required_upfront": deposit_amount + buying_costs,
    }
# ---------------------------------------------------------
# PREMIUM UI COMPONENTS
# ---------------------------------------------------------

def render_top_summary(metrics: dict):
    st.markdown(
        f"""
        <div style="
            padding:16px 20px;
            border-radius:14px;
            background:linear-gradient(135deg,#020617,#0f172a);
            border:1px solid #1e293b;
            margin-bottom:18px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-size:13px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.08em;">
                        Cashflow snapshot
                    </div>
                    <div style="font-size:22px;color:#e5e7eb;font-weight:600;">
                        {metrics['cashflow_label']}
                    </div>
                    <div style="font-size:13px;color:#9ca3af;margin-top:4px;">
                        Pre‑tax: {currency(metrics['pre_tax_cashflow'])} · After‑tax: {currency(metrics['after_tax_cashflow'])}
                    </div>
                </div>
                <div style="display:flex;gap:18px;">
                    <div style="text-align:right;">
                        <div style="font-size:11px;color:#9ca3af;">Gross yield</div>
                        <div style="font-size:18px;color:#22c55e;font-weight:600;">{metrics['gross_yield']:.2f}%</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:11px;color:#9ca3af;">Net yield (pre interest)</div>
                        <div style="font-size:18px;color:#e5e7eb;font-weight:600;">{metrics['net_yield_before_interest']:.2f}%</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_property_card(payload: dict):
    addr = payload.get("property_address") or "Unnamed property"
    suburb = payload.get("suburb") or ""
    state = payload.get("property_state") or ""
    postcode = payload.get("postcode") or ""
    locality = " ".join([p for p in [suburb, state, postcode] if p])

    st.markdown(
        f"""
        <div style="
            padding:18px 20px;
            border-radius:14px;
            background:#020617;
            border:1px solid #1f2937;
            margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;">
                <div>
                    <div style="font-size:18px;color:#e5e7eb;font-weight:600;">{addr}</div>
                    <div style="font-size:13px;color:#9ca3af;margin-top:2px;">{locality or "Locality not set"}</div>
                    <div style="font-size:12px;color:#6b7280;margin-top:6px;">
                        {payload.get("property_type") or "Type not set"} · 
                        {property_fact(payload.get("bedrooms"))} bed · 
                        {property_fact(payload.get("bathrooms"))} bath · 
                        {property_fact(payload.get("car_spaces"))} car
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:11px;color:#9ca3af;">Price</div>
                    <div style="font-size:18px;color:#e5e7eb;font-weight:600;">{currency(payload.get("price"))}</div>
                    <div style="font-size:11px;color:#9ca3af;margin-top:6px;">Rent (est.)</div>
                    <div style="font-size:16px;color:#22c55e;font-weight:500;">{currency(payload.get("weekly_rent"))}/wk</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics_grid(metrics: dict):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gross yield", f"{metrics['gross_yield']:.2f}%")
    c2.metric("Net yield (pre interest)", f"{metrics['net_yield_before_interest']:.2f}%")
    c3.metric("Net yield (post interest)", f"{metrics['net_yield_after_interest']:.2f}%")
    c4.metric("Debt ratio", f"{metrics['total_debt_ratio']:.2f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Cash required upfront", currency(metrics["cash_required_upfront"]))
    c6.metric("Total borrowings", currency(metrics["total_borrowings"]))
    c7.metric("Break‑even rent", f"{currency(metrics['break_even_rent_weekly'])}/wk")
    coc = (
        f"{metrics['cashflow_score']:.2f}%"
        if metrics["cash_required_upfront"] > 0
        else "n/a"
    )
    c8.metric("Cash‑on‑cash", coc)


def render_recommendation_card(metrics: dict):
    rec = metrics["recommendation"]
    color = {
        "BUY": "#22c55e",
        "WATCH": "#facc15",
        "AVOID": "#f97316",
        "INCOMPLETE": "#6b7280",
    }.get(rec, "#38bdf8")

    st.markdown(
        f"""
        <div style="
            padding:18px 20px;
            border-radius:14px;
            background:#020617;
            border:1px solid {color};
            margin-top:12px;">
            <div style="font-size:12px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.08em;">
                Recommendation
            </div>
            <div style="font-size:22px;color:{color};font-weight:600;margin-top:4px;">
                {rec}
            </div>
            <div style="font-size:12px;color:#9ca3af;margin-top:6px;">
                Score {metrics['overall_score']:.1f}/10 · Risk {metrics['risk_score']:.1f}/10 · Growth {metrics['growth_score']:.1f}/10
            </div>
            <ul style="font-size:12px;color:#9ca3af;margin-top:10px;padding-left:18px;">
                {''.join(f"<li>{r}</li>" for r in metrics['recommendation_reasons'])}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# PREMIUM TABS UI
# ---------------------------------------------------------

def render_tabs(payload: dict):
    tab_details, tab_purchase, tab_rent, tab_finance, tab_analysis, tab_export = st.tabs(
        [
            "Property details",
            "Purchase & costs",
            "Rent & expenses",
            "Finance",
            "Analysis & charts",
            "Save & export",
        ]
    )

    # --- PROPERTY DETAILS ---
    with tab_details:
        st.subheader("Property & listing")
        st.text_input("Property address", key="property_address")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Suburb", key="suburb")
        c2.text_input("State", key="property_state")
        c3.text_input("Postcode", key="postcode")

        st.text_input("Property type", key="property_type")
        b1, b2, b3 = st.columns(3)
        b1.number_input("Bedrooms", key="bedrooms", min_value=0.0, step=1.0)
        b2.number_input("Bathrooms", key="bathrooms", min_value=0.0, step=1.0)
        b3.number_input("Car spaces", key="car_spaces", min_value=0.0, step=1.0)

        st.text_area("Listing summary", key="listing_summary", height=120)
        st.text_input("REA listing URL", key="listing_url_input")
        st.text_area("Copied REA listing details", key="listing_text_input", height=140)

        cA, cB = st.columns(2)
        cA.button("Import from URL", on_click=run_listing_import, args=("link",), use_container_width=True)
        cB.button("Import from pasted text", on_click=run_listing_import, args=("paste",), use_container_width=True)

        if st.session_state.listing_import_message:
            st.info(st.session_state.listing_import_message)

    # --- PURCHASE ---
    with tab_purchase:
        st.subheader("Purchase & costs")
        p1, p2, p3 = st.columns(3)
        p1.number_input("Purchase price", key="price", min_value=0.0, step=1000.0)
        p2.selectbox("Deposit mode", ["Percent", "Dollar"], key="deposit_input_mode_input", on_change=sync_deposit_input_mode)
        p3.number_input("Deposit value", key="deposit_input_value", min_value=0.0)

        p4, p5, p6 = st.columns(3)
        p4.number_input("Stamp duty", key="stamp_duty", min_value=0.0)
        p5.number_input("Solicitor / conveyancer", key="solicitor_charge", min_value=0.0)
        p6.number_input("Inspection costs", key="inspection_costs", min_value=0.0)

        st.number_input("Property value", key="property_value", min_value=0.0)

    # --- RENT ---
    with tab_rent:
        st.subheader("Rent & holding costs")
        r1, r2 = st.columns(2)
        r1.number_input("Weekly rent", key="weekly_rent", min_value=0.0)
        r2.number_input("Vacancy allowance (%)", key="vacancy_allowance_pct", min_value=0.0)

        r3, r4, r5 = st.columns(3)
        r3.number_input("Council (quarterly)", key="council_quarterly", min_value=0.0)
        r3.number_input("Water (quarterly)", key="water_quarterly", min_value=0.0)

        r4.number_input("Strata (quarterly)", key="strata_quarterly", min_value=0.0)
        r4.number_input("Building insurance (annual)", key="building_insurance_annual", min_value=0.0)

        r5.number_input("Landlord insurance (annual)", key="landlord_insurance_annual", min_value=0.0)
        r5.number_input("Maintenance allowance (%)", key="maintenance_allowance_pct", min_value=0.0)

        st.subheader("Growth assumptions")
        g1, g2, g3 = st.columns(3)
        g1.number_input("Rent growth (%)", key="rent_growth_pct", min_value=0.0)
        g2.number_input("Expense inflation (%)", key="expense_inflation_pct", min_value=0.0)
        g3.number_input("Property growth (%)", key="property_growth_pct", min_value=0.0)

    # --- FINANCE ---
    with tab_finance:
        st.subheader("Funding & loans")
        st.selectbox("Deposit source", ["Cash", "Equity"], key="deposit_source_input")

        st.markdown("**Loan 1**")
        f1, f2, f3, f4 = st.columns(4)
        f1.number_input("Amount", key="mortgage_1_amount", min_value=0.0)
        f2.number_input("Rate (%)", key="mortgage_1_rate", min_value=0.0)
        f3.number_input("Term (years)", key="mortgage_1_years", min_value=0.0)
        f4.selectbox("Type", ["P+I", "I only"], key="mortgage_1_repayment_type_input")

        st.markdown("**Loan 2**")
        f5, f6, f7, f8 = st.columns(4)
        f5.number_input("Amount", key="mortgage_2_amount", min_value=0.0)
        f6.number_input("Rate (%)", key="mortgage_2_rate", min_value=0.0)
        f7.number_input("Term (years)", key="mortgage_2_years", min_value=0.0)
        f8.selectbox("Type", ["P+I", "I only"], key="mortgage_2_repayment_type_input")

        st.markdown("**Loan 3**")
        f9, f10, f11, f12 = st.columns(4)
        f9.number_input("Amount", key="mortgage_3_amount", min_value=0.0)
        f10.number_input("Rate (%)", key="mortgage_3_rate", min_value=0.0)
        f11.number_input("Term (years)", key="mortgage_3_years", min_value=0.0)
        f12.selectbox("Type", ["P+I", "I only"], key="mortgage_3_repayment_type_input")

    # --- ANALYSIS ---
    with tab_analysis:
        if st.button("Calculate analysis", type="primary"):
            payload = current_payload()
            st.session_state.calculated_payload = calculate_metrics(payload)
            st.session_state.has_calculated = True

        if st.session_state.has_calculated:
            metrics = st.session_state.calculated_payload
            render_top_summary(metrics)
            render_property_card(payload)
            render_metrics_grid(metrics)
            render_recommendation_card(metrics)

    # --- EXPORT ---
    with tab_export:
        st.subheader("Save / Export")
        st.text_input("Save name", key="save_name_input_export")
        if st.button("Save property", use_container_width=True):
            payload = current_payload()
            name = st.session_state.save_name_input or payload.get("property_address") or "Property"
            save_property(
                name=name,
                address=str(payload.get("property_address") or ""),
                state=parse_state_from_address(str(payload.get("property_address") or "")),
                payload=payload,
            )
            st.success(f"Saved {name}")

        st.divider()
        st.subheader("Export PDF")
        if st.button("Generate PDF report", use_container_width=True):
            try:
                pdf = pdf_report.build_property_report(
                    payload,
                    st.session_state.calculated_payload,
                    [],
                    pd.DataFrame(),
                    pd.DataFrame(),
                )
                st.download_button(
                    "Download PDF",
                    data=pdf,
                    file_name="property_report.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"PDF generation failed: {e}")
# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------

def current_payload():
    return {k: st.session_state.get(k, DEFAULTS[k]) for k in DEFAULTS}


def main():
    st.set_page_config(page_title="Cashflow Scout", page_icon="🏠", layout="wide")
    init_db()
    ensure_state()

    # Sidebar
    with st.sidebar:
        st.markdown("### Saved properties")
        saved = list_properties()
        if saved:
            for item in saved:
                if st.button(item["name"], use_container_width=True):
                    loaded = load_property(item["name"])
                    if loaded:
                        apply_payload_to_state(loaded["payload"], item["name"])
                        st.rerun()
        else:
            st.caption("No saved properties yet.")

        st.divider()
        st.text_input("Save name", key="save_name_input")
        if st.button("Save current", use_container_width=True):
            payload = current_payload()
            name = st.session_state.save_name_input or payload.get("property_address") or "Property"
            save_property(
                name=name,
                address=str(payload.get("property_address") or ""),
                state=parse_state_from_address(str(payload.get("property_address") or "")),
                payload=payload,
            )
            st.success(f"Saved {name}")
            st.session_state.loaded_property_name = name
            st.rerun()

    # Main Title
    st.title("🏠 Cashflow Scout – Premium Investment Dashboard")

    # Render UI Tabs
    payload = current_payload()
    render_tabs(payload)

    # If calculated, show summary at bottom
    if st.session_state.has_calculated:
        metrics = st.session_state.calculated_payload
        st.divider()
        st.subheader("Summary")
        render_top_summary(metrics)
        render_property_card(payload)
        render_metrics_grid(metrics)
        render_recommendation_card(metrics)


def apply_payload_to_state(payload: Dict[str, Any], property_name: str) -> None:
    for key, default_value in DEFAULTS.items():
        st.session_state[key] = payload.get(key, default_value)

    # Deposit handling
    if "deposit_input_value" not in payload:
        st.session_state.deposit_input_value = payload.get("deposit_pct", DEFAULTS["deposit_input_value"])
    if "deposit_input_mode" not in payload:
        st.session_state.deposit_input_mode = "Percent"

    st.session_state.deposit_input_mode_input = st.session_state.deposit_input_mode
    st.session_state.deposit_source_input = st.session_state.deposit_source

    # Mortgage types
    st.session_state.mortgage_1_repayment_type_input = st.session_state.mortgage_1_repayment_type
    st.session_state.mortgage_2_repayment_type_input = st.session_state.mortgage_2_repayment_type
    st.session_state.mortgage_3_repayment_type_input = st.session_state.mortgage_3_repayment_type

    # Listing fields
    st.session_state.listing_url_input = st.session_state.listing_url
    st.session_state.listing_text_input = st.session_state.listing_text
    st.session_state.listing_import_message = ""

    # Save/load state
    st.session_state.save_name = property_name
    st.session_state.loaded_property_name = property_name

    # SOI + stamp duty
    st.session_state.last_soi_lookup_address = str(st.session_state.property_address).strip()
    st.session_state.stamp_duty_auto_signature = ""
    st.session_state.has_calculated = False
    st.session_state.calculated_payload = {}

    # Clear editors
    for key in ["facts_editor", "purchase_editor", "rent_rates_editor", "finance_editor", "tax_editor"]:
        st.session_state.pop(key, None)
        st.session_state.pop(f"{key}_draft", None)


# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    main()
