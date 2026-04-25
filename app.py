"""app.py — PawPal+ Three-Pane Dashboard (Polished Edition)

Layout:
  Left   → Sidebar  (Management & Admin)
  Middle → Col 65%  (Result Canvas — Gantt Plan)
  Right  → Col 35%  (Agent Assistant Chat)

Fixes applied vs previous version:
  #1  .streamlit/config.toml instructions embedded as comment
  #2  Chat empty-state centering (min-height instead of height:100%)
  #3  Gantt "no start_time" contextual hint
  #4  Block-container horizontal padding aligned with hero
  #5  KPI cards wrapped in a grouped status-bar card
  #6  Generate Schedule button full-width
  #7  Right pane full dark-card wrapping
  #8  Sidebar select dropdown popover dark styling
  #9  st.spinner on schedule generation
  #10 Persistent guardrail banner (session-state flagged)
  #11 Darker priority badge backgrounds for contrast
  #12 Gantt axis step=1 with alternating label visibility
  #13 Shorter chat placeholder text
  #14 Clear chat button in agent pane header
  #16 Removed unused timedelta import
  #17 Orchestrator only created once; owner-pointer refreshed each run
  #18 Gantt bar width clamped to prevent overflow past 22:00
"""

import json
import os
import re
from datetime import date, datetime

import anthropic
import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler
from agent.orchestrator import PawPalOrchestrator

# ── Page config ───────────────────────────────────────────────────────────
# FIX #1: tunnel stability — also create .streamlit/config.toml with:
#   [server]
#   enableCORS = false
#   enableXsrfProtection = false
#   [browser]
#   serverAddress = "brown-points-smoke.loca.lt"
#   serverPort = 443
st.set_page_config(
    page_title="PawPal+ | Smart Pet Care",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design system ─────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap');

:root {
    --navy:        #101B35;
    --navy-mid:    #1A2E55;
    --coral:       #FF6B35;
    --coral-dark:  #E8531E;
    --teal:        #2EC4B6;
    --teal-dark:   #1EA89B;
    --slate:       #F5F7FA;
    --border:      #E2E8F0;
    --text:        #0F172A;
    --muted:       #64748B;
    --white:       #FFFFFF;
}

/* ── Base ─────────────────────────────────────────────────────────────── */
html, body, [class*="css"], .stApp,
.stMarkdown, .stText, button, input, select, textarea {
    font-family: 'DM Sans', system-ui, sans-serif !important;
}
code, pre, .stCode { font-family: 'DM Mono', monospace !important; }
.stApp { background-color: var(--slate); }

/* FIX #4: consistent horizontal padding aligns content with hero header */
.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 3rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}

/* Allow sticky positioning */
.stApp, section.main, .main .block-container { overflow: visible !important; }

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden; }

/* ── Sidebar — dark navy ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--navy) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] > div:first-child {
    background-color: var(--navy) !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stCaption { color: #64748B !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #F1F5F9 !important; }

[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,107,53,0.10) !important;
    color: #FB923C !important;
    border: 1px solid rgba(255,107,53,0.30) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.18s ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,107,53,0.22) !important;
}

[data-testid="stSidebar"] .stTextInput > div > div > input,
[data-testid="stSidebar"] .stNumberInput > div > div > input {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(255,255,255,0.10) !important;
    color: #E2E8F0 !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] .stTextInput > div > div > input::placeholder,
[data-testid="stSidebar"] .stNumberInput > div > div > input::placeholder {
    color: #475569 !important;
}
[data-testid="stSidebar"] .stTextInput > div > div > input:focus,
[data-testid="stSidebar"] .stNumberInput > div > div > input:focus {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.12) !important;
    background: rgba(255,255,255,0.09) !important;
}

/* FIX #8: Sidebar select — menu popover dark */
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(255,255,255,0.10) !important;
    color: #E2E8F0 !important;
    border-radius: 8px !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] {
    background: #1A2E55 !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 8px !important;
}
[data-baseweb="popover"] [data-baseweb="option"] {
    color: #CBD5E1 !important;
    background: transparent !important;
}
[data-baseweb="popover"] [data-baseweb="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] {
    background: rgba(255,107,53,0.15) !important;
    color: #FB923C !important;
}

[data-testid="stSidebar"] [data-testid="stForm"] {
    background: rgba(255,255,255,0.03) !important;
    border-color: rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
}
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.07) !important; }
[data-testid="stSidebar"] .stCheckbox label span { color: #94A3B8 !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.03) !important;
    border-color: rgba(255,255,255,0.07) !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: #94A3B8 !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.18s ease !important;
    cursor: pointer !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--coral) 0%, var(--coral-dark) 100%) !important;
    color: #fff !important;
    border: none !important;
    box-shadow: 0 4px 14px rgba(255,107,53,0.38) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 22px rgba(255,107,53,0.52) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"]:active { transform: translateY(0) !important; }

.stButton > button[kind="secondary"] {
    background: var(--white) !important;
    color: var(--coral) !important;
    border: 1.5px solid var(--coral) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: #FFF5F1 !important;
    transform: translateY(-1px) !important;
}

.stFormSubmitButton > button {
    background: linear-gradient(135deg, var(--teal) 0%, var(--teal-dark) 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    box-shadow: 0 3px 10px rgba(46,196,182,0.32) !important;
    transition: all 0.18s ease !important;
}
.stFormSubmitButton > button:hover {
    box-shadow: 0 5px 18px rgba(46,196,182,0.48) !important;
    transform: translateY(-1px) !important;
}

/* Small ghost button for clear-chat */
.btn-ghost > button {
    background: rgba(255,255,255,0.07) !important;
    color: #94A3B8 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 6px !important;
    font-size: 0.72rem !important;
    padding: 0.25rem 0.6rem !important;
}
.btn-ghost > button:hover {
    background: rgba(255,255,255,0.13) !important;
    color: #CBD5E1 !important;
    border-color: rgba(255,255,255,0.22) !important;
}

/* ── Text inputs (main area) ──────────────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 8px !important;
    border: 1.5px solid var(--border) !important;
    background: var(--white) !important;
    color: var(--text) !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.12) !important;
    outline: none !important;
}

/* ── Progress bar ─────────────────────────────────────────────────────── */
[data-testid="stProgressBarValue"] {
    background: linear-gradient(90deg, var(--coral) 0%, var(--teal) 100%) !important;
    border-radius: 999px !important;
}

/* ── Expanders ────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--white) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    margin-bottom: 0.5rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: var(--text) !important;
    padding: 0.875rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { color: var(--coral) !important; }

/* ── Metric cards ─────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--white) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
    transition: box-shadow 0.18s ease !important;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08) !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
    color: var(--muted) !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: var(--text) !important;
}

/* ── Alerts ───────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 4px !important;
}

/* ── Chat messages ────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
    margin-bottom: 0.5rem !important;
}
[data-testid="stChatMessage"] p { color: #CBD5E1 !important; }
[data-testid="stChatMessage"] strong { color: #F1F5F9 !important; }

/* ── Forms (main area) ────────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: #FAFBFF !important;
    padding: 1.25rem !important;
}

/* ── Tables ───────────────────────────────────────────────────────────── */
[data-testid="stTable"] table {
    border-radius: 8px !important;
    border: 1px solid var(--border) !important;
    overflow: hidden !important;
    font-size: 0.875rem !important;
}
[data-testid="stTable"] th {
    background: #F8FAFC !important;
    color: var(--muted) !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stTable"] tr:hover td { background: #FFF8F5 !important; }

/* ── Status widget ────────────────────────────────────────────────────── */
[data-testid="stStatus"] {
    border-radius: 10px !important;
    border: 1px solid var(--border) !important;
}

hr { border-color: var(--border) !important; margin: 1.25rem 0 !important; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────

PRIORITY_MAP = {"low": 1, "medium": 3, "high": 5}


def _priority_badge(p: int) -> str:
    if p >= 5: return "High"
    if p >= 3: return "Medium"
    return "Low"


# FIX #11: Darker badge backgrounds for better contrast on white
def _priority_badge_html(p: int) -> str:
    if p >= 5:
        return (
            '<span style="display:inline-block;background:#FECACA;color:#991B1B;'
            'padding:2px 9px;border-radius:999px;font-size:0.68rem;font-weight:700;'
            'letter-spacing:0.04em;">HIGH</span>'
        )
    if p >= 3:
        return (
            '<span style="display:inline-block;background:#FDE68A;color:#92400E;'
            'padding:2px 9px;border-radius:999px;font-size:0.68rem;font-weight:700;'
            'letter-spacing:0.04em;">MED</span>'
        )
    return (
        '<span style="display:inline-block;background:#A7F3D0;color:#065F46;'
        'padding:2px 9px;border-radius:999px;font-size:0.68rem;font-weight:700;'
        'letter-spacing:0.04em;">LOW</span>'
    )


def _sidebar_section(icon: str, title: str, subtitle: str = "") -> str:
    sub_html = (
        f'<div style="color:#475569;font-size:0.72rem;margin-top:2px;">{subtitle}</div>'
        if subtitle else ""
    )
    return (
        f'<div style="display:flex;align-items:center;gap:0.55rem;'
        f'margin-bottom:0.75rem;margin-top:0.25rem;">'
        f'<div style="width:26px;height:26px;background:rgba(255,107,53,0.14);'
        f'border:1px solid rgba(255,107,53,0.28);border-radius:7px;flex-shrink:0;'
        f'display:flex;align-items:center;justify-content:center;font-size:0.82rem;">'
        f'{icon}</div>'
        f'<div>'
        f'<div style="font-weight:700;color:#CBD5E1;font-size:0.88rem;line-height:1.2;">'
        f'{title}</div>'
        f'{sub_html}'
        f'</div></div>'
    )


def _page_header(owner: Owner, total_due: int, total_mins: int) -> str:
    n_pets = len(owner.pets)
    return (
        '<div style="background:linear-gradient(135deg,#101B35 0%,#1A2E55 55%,#152B50 100%);'
        'border-radius:14px;padding:0.75rem 1.5rem;border:1px solid rgba(255,255,255,0.06);'
        'box-shadow:0 4px 24px rgba(0,0,0,0.28);position:sticky;top:0;z-index:999;'
        'margin-bottom:1.25rem;overflow:hidden;">'
        '<div style="position:absolute;right:-0.5rem;top:50%;transform:translateY(-50%);'
        'font-size:8rem;opacity:0.04;pointer-events:none;line-height:1;">🐾</div>'
        '<div style="position:relative;z-index:1;display:flex;align-items:center;gap:1.25rem;">'
        '<div style="background:rgba(255,107,53,0.15);border:1px solid rgba(255,107,53,0.40);'
        'border-radius:12px;width:44px;height:44px;flex-shrink:0;'
        'display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🐾</div>'
        '<div>'
        '<h1 style="margin:0;color:#FFFFFF;font-size:1.55rem;font-weight:800;'
        'letter-spacing:-0.03em;line-height:1.1;">'
        'PawPal<span style="color:#FF6B35;">+</span></h1>'
        '<p style="margin:0.15rem 0 0;color:#64748B;font-size:0.78rem;">'
        'AI-powered scheduling\u00a0\u00b7\u00a0conflict detection\u00a0\u00b7\u00a0safety guardrail'
        '</p></div>'
        '<div style="margin-left:auto;display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;">'
        '<span style="background:rgba(46,196,182,0.12);border:1px solid rgba(46,196,182,0.35);'
        'color:#2EC4B6;font-size:0.68rem;font-weight:700;letter-spacing:0.04em;'
        'padding:3px 9px;border-radius:999px;">HAIKU-4.5 &amp; SONNET-4.6</span>'
        '<span style="background:rgba(255,107,53,0.12);border:1px solid rgba(255,107,53,0.35);'
        'color:#FF6B35;font-size:0.68rem;font-weight:700;letter-spacing:0.04em;'
        'padding:3px 9px;border-radius:999px;">REACT AGENT</span>'
        f'<span style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);'
        f'color:#94A3B8;font-size:0.68rem;font-weight:600;padding:3px 9px;border-radius:999px;">'
        f'{n_pets}\u00a0pet{"s" if n_pets != 1 else ""}\u00a0\u00b7\u00a0{total_due}\u00a0due'
        f'\u00a0\u00b7\u00a0{total_mins}\u00a0min</span>'
        '</div></div></div>'
    )


# ── Gantt helpers ─────────────────────────────────────────────────────────

_DAY_START_H = 6    # 06:00
_DAY_END_H   = 22   # 22:00
_DAY_RANGE_M = (_DAY_END_H - _DAY_START_H) * 60   # 960 minutes


# FIX #12: Gantt axis — tick every hour, label every 2 hours
def _gantt_axis() -> str:
    ticks = ""
    for h in range(_DAY_START_H, _DAY_END_H + 1):
        pct = (h - _DAY_START_H) / (_DAY_END_H - _DAY_START_H) * 100
        show_label = (h % 2 == 0)
        label_html = (
            f'<span style="font-size:0.58rem;color:#94A3B8;'
            f'font-family:\'DM Mono\',monospace;">{h:02d}:00</span>'
            if show_label else ""
        )
        ticks += (
            f'<div style="position:absolute;left:{pct:.2f}%;'
            f'display:flex;flex-direction:column;align-items:center;gap:2px;">'
            f'<div style="width:1px;height:6px;background:#CBD5E1;"></div>'
            f'{label_html}'
            f'</div>'
        )
    ruler = '<div style="position:absolute;top:6px;left:0;right:0;height:1px;background:#E2E8F0;"></div>'
    return (
        f'<div style="position:relative;height:22px;margin-bottom:6px;">'
        f'{ruler}{ticks}'
        f'</div>'
    )


# FIX #18: Bar width clamped; FIX #3: contextual hint when no start_time
def _gantt_bar(
    task_name: str,
    start_str: str | None,
    duration: int,
    is_required: bool,
    is_skipped: bool = False,
) -> str:
    lock = "🔒 " if is_required else ""
    label = f"{lock}{task_name} ({duration}m)"

    if is_skipped:
        return (
            f'<div style="font-size:0.78rem;color:#94A3B8;padding:5px 10px;'
            f'background:#F1F5F9;border-radius:6px;border:1px dashed #CBD5E1;'
            f'margin-bottom:4px;">⏭\u00a0{label}\u00a0—\u00a0skipped (budget full)</div>'
        )

    if start_str is None:
        return (
            f'<div style="font-size:0.78rem;color:#94A3B8;padding:5px 10px;'
            f'background:#F8FAFC;border-radius:6px;border:1px dashed #CBD5E1;'
            f'margin-bottom:4px;display:flex;align-items:center;gap:6px;">'
            f'<span style="font-size:0.7rem;">⏱</span>'
            f'<span>{label}</span>'
            f'<span style="margin-left:auto;font-size:0.65rem;color:#CBD5E1;">'
            f'Assign a start time to show on Gantt</span>'
            f'</div>'
        )

    try:
        t = datetime.strptime(start_str, "%H:%M")
        start_min = t.hour * 60 + t.minute
    except ValueError:
        start_min = _DAY_START_H * 60

    end_min    = start_min + duration
    left_pct   = max(0.0, (start_min - _DAY_START_H * 60) / _DAY_RANGE_M * 100)
    # FIX #18: clamp so bar never overflows the 22:00 boundary
    width_pct  = max(0.5, duration / _DAY_RANGE_M * 100)
    width_pct  = min(width_pct, 100.0 - left_pct)
    if left_pct >= 100:
        left_pct, width_pct = 99.0, 0.5

    color      = "#FF6B35" if is_required else "#2EC4B6"
    end_str    = f"{end_min // 60:02d}:{end_min % 60:02d}"

    return (
        f'<div style="position:relative;height:30px;background:#F8FAFC;'
        f'border-radius:6px;border:1px solid #E2E8F0;overflow:hidden;margin-bottom:5px;">'
        f'<div style="position:absolute;left:{left_pct:.2f}%;width:{width_pct:.2f}%;'
        f'height:100%;background:{color};border-radius:5px;opacity:0.88;'
        f'display:flex;align-items:center;padding:0 8px;box-sizing:border-box;overflow:hidden;">'
        f'<span style="color:#fff;font-size:0.72rem;font-weight:600;white-space:nowrap;'
        f'overflow:hidden;text-overflow:ellipsis;">{label}</span>'
        f'</div>'
        f'<span style="position:absolute;right:6px;top:50%;transform:translateY(-50%);'
        f'font-size:0.62rem;color:#94A3B8;font-family:\'DM Mono\',monospace;'
        f'pointer-events:none;">{start_str}–{end_str}</span>'
        f'</div>'
    )


# ── Session state ─────────────────────────────────────────────────────────

def _init_session():
    if "owner_data" not in st.session_state:
        if os.path.exists("data/data.json"):
            st.session_state.owner_data = Owner.load_from_json("data/data.json")
        else:
            default_pet = Pet(name="Mochi", species="dog", age=3)
            default_owner = Owner(name="Jordan", available_time_mins=60)
            default_owner.pets.append(default_pet)
            st.session_state.owner_data = default_owner

    defaults = {
        "owner_name":         st.session_state.owner_data.name,
        "available_time":     st.session_state.owner_data.available_time_mins,
        "schedule_result":    None,
        "pending_complete":   None,
        "last_completed":     None,
        "chat_history":       [],
        "guardrail_result":   None,
        "guardrail_banner":   False,   # persistent banner; dismissed by user or auto-reset (FIX #7)
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # FIX #17: create orchestrator only once; always sync the owner pointer
    if "orchestrator" not in st.session_state:
        _client = anthropic.Anthropic()
        st.session_state.orchestrator = PawPalOrchestrator(
            owner=st.session_state.owner_data,
            client=_client,
        )
    else:
        # Refresh the live owner reference without rebuilding the object
        st.session_state.orchestrator.owner = st.session_state.owner_data
        st.session_state.orchestrator.tools.owner = st.session_state.owner_data


_init_session()

# ── Pending task completion ───────────────────────────────────────────────
# FIX #4: use task index (not name) to handle duplicate task names on same pet
if st.session_state.pending_complete is not None:
    _pname, _tidx = st.session_state.pending_complete
    for _pet in st.session_state.owner_data.pets:
        if _pet.name == _pname:
            if _tidx < len(_pet.tasks):
                _task = _pet.tasks[_tidx]
                if not _task.is_completed:
                    _pet.complete_task(_task)
                    st.session_state.last_completed = _task.name
            break
    st.session_state.pending_complete = None
    st.session_state.schedule_result  = None

# ── Pre-compute metrics ───────────────────────────────────────────────────
orchestrator: PawPalOrchestrator = st.session_state.orchestrator
owner = st.session_state.owner_data
today = date.today()

total_due = sum(
    1 for pet in owner.pets
    for t in pet.tasks
    if t.due_date <= today and not t.is_completed
)
total_required_due = sum(
    1 for pet in owner.pets
    for t in pet.tasks
    if t.is_required and t.due_date <= today and not t.is_completed
)
total_mins = sum(
    t.duration for pet in owner.pets
    for t in pet.tasks
    if t.due_date <= today and not t.is_completed
)

# ══════════════════════════════════════════════════════════════════════════
# LEFT PANE — Sidebar
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo / brand
    st.markdown(
        '<div style="padding:0 0 1.25rem;border-bottom:1px solid rgba(255,255,255,0.07);'
        'margin-bottom:1.25rem;">'
        '<div style="display:flex;align-items:center;gap:0.75rem;">'
        '<div style="width:36px;height:36px;background:rgba(255,107,53,0.15);'
        'border:1px solid rgba(255,107,53,0.35);border-radius:9px;'
        'display:flex;align-items:center;justify-content:center;font-size:1.1rem;">🐾</div>'
        '<div>'
        '<div style="color:#F1F5F9;font-weight:700;font-size:0.95rem;">'
        'PawPal<span style="color:#FB923C;">+</span></div>'
        '<div style="color:#334155;font-size:0.7rem;margin-top:1px;">Management Console</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )

    # ── Owner Settings ──────────────────────────────────────────────────
    st.markdown(_sidebar_section("👤", "Owner Settings"), unsafe_allow_html=True)
    owner_name_val    = st.text_input("Owner name", key="owner_name")
    available_time_val = st.number_input(
        "Available time (minutes)", min_value=0, max_value=480, key="available_time"
    )
    st.session_state.owner_data.name               = owner_name_val
    st.session_state.owner_data.available_time_mins = int(available_time_val)

    if st.button("💾  Save Data", use_container_width=True):
        st.session_state.owner_data.save_to_json("data/data.json")
        st.success("Saved to data/data.json")

    st.divider()

    # ── Add Pet ──────────────────────────────────────────────────────────
    st.markdown(_sidebar_section("🐕", "Add a Pet", "Register a new pet"), unsafe_allow_html=True)
    with st.form("add_pet_form", clear_on_submit=True):
        new_pet_name    = st.text_input("Name")
        c1, c2 = st.columns(2)
        with c1:
            new_pet_species = st.selectbox("Species", ["dog", "cat", "rabbit", "fish", "bird", "other"])
        with c2:
            new_pet_age = st.number_input("Age (yrs)", min_value=0, max_value=30, value=1)
        if st.form_submit_button("Add Pet", use_container_width=True):
            if new_pet_name.strip():
                np = Pet(name=new_pet_name.strip(), species=new_pet_species, age=int(new_pet_age))
                st.session_state.owner_data.pets.append(np)
                st.session_state.schedule_result = None
                st.success(f"'{np.name}' added!")
            else:
                st.warning("Please enter a pet name.")

    st.divider()

    # ── Add Task ─────────────────────────────────────────────────────────
    st.markdown(_sidebar_section("📋", "Add a Task", "Assign a task to a pet"), unsafe_allow_html=True)
    owner_sb = st.session_state.owner_data
    if not owner_sb.pets:
        st.markdown(
            '<p style="color:#475569;font-size:0.8rem;padding:0.25rem 0;">'
            'Add a pet first to start adding tasks.</p>',
            unsafe_allow_html=True,
        )
    else:
        with st.form("add_task_form", clear_on_submit=False):
            selected_pet = st.selectbox("Assign to pet", [p.name for p in owner_sb.pets])
            task_title   = st.text_input("Task title", value="Morning walk")
            ta, tb = st.columns(2)
            with ta:
                duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
            with tb:
                priority_label = st.selectbox("Priority", ["low", "medium", "high"], index=2)
            tc, td = st.columns(2)
            with tc:
                frequency = st.selectbox("Frequency", ["one-off", "daily", "weekly"])
            with td:
                is_required = st.checkbox("Required")
            # FIX #5/#8: start-time validation + due-date field
            te, tf = st.columns(2)
            with te:
                start_time_raw = st.text_input("Start time (HH:MM)", value="", placeholder="09:00")
            with tf:
                due_date_val = st.date_input("Due date", value=date.today())

            if st.form_submit_button("Add Task", use_container_width=True):
                if task_title.strip():
                    st_val = start_time_raw.strip() or None
                    if st_val and not re.match(r"^\d{2}:\d{2}$", st_val):
                        st.error("Start time must be HH:MM (e.g. 09:00).")
                    else:
                        new_task = Task(
                            name=task_title.strip(),
                            duration=int(duration),
                            priority=PRIORITY_MAP[priority_label],
                            is_required=is_required,
                            frequency=frequency,
                            start_time=st_val,
                            due_date=due_date_val,
                        )
                        tgt_pet = next(p for p in owner_sb.pets if p.name == selected_pet)
                        tgt_pet.tasks.append(new_task)
                        st.session_state.schedule_result = None
                        st.success(f"'{new_task.name}' added to {tgt_pet.name}.")
                else:
                    st.warning("Please enter a task title.")

    # ── System Status footer ─────────────────────────────────────────────
    st.divider()
    st.markdown(
        '<div style="background:rgba(46,196,182,0.08);border:1px solid rgba(46,196,182,0.25);'
        'border-radius:10px;padding:0.75rem 1rem;">'
        '<div style="display:flex;align-items:center;gap:0.5rem;">'
        '<span style="font-size:1.1rem;">🛡️</span>'
        '<div>'
        '<div style="color:#2EC4B6;font-weight:700;font-size:0.8rem;">Safety Guardrail: Active</div>'
        '<div style="color:#475569;font-size:0.68rem;margin-top:1px;">Required tasks are always protected</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )

    with st.expander("🗂  Guardrail Audit Log"):
        log_path = "data/guardrail_violations.jsonl"
        if os.path.exists(log_path):
            records = []
            with open(log_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            if records:
                st.dataframe(records[-5:], use_container_width=True)
            else:
                st.markdown('<p style="color:#64748B;font-size:0.8rem;">No violations yet.</p>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#64748B;font-size:0.8rem;">Log not found.</p>',
                        unsafe_allow_html=True)

    with st.expander("ℹ️  About"):
        st.markdown(
            '<p style="color:#475569;font-size:0.75rem;line-height:1.6;margin:0;">'
            'PawPal+ uses a ReAct agent loop with Claude to resolve schedule conflicts '
            'and enforce safety guardrails on every optimization run.</p>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════
# STICKY PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════
st.markdown(_page_header(owner, total_due, total_mins), unsafe_allow_html=True)

# FIX #10: persistent guardrail banner shown until user dismisses
# FIX #7: reset banner silently if guardrail_result was cleared (prevents permanent lock)
if st.session_state.guardrail_banner:
    gr = st.session_state.guardrail_result
    msg = gr.as_ui_message() if gr else ""
    if not msg:
        st.session_state.guardrail_banner = False
    else:
        col_msg, col_x = st.columns([9, 1])
        with col_msg:
            st.warning(f"🛡️ **Guardrail correction applied** — {msg}", icon="⚠️")
        with col_x:
            if st.button("✕", key="dismiss_banner", help="Dismiss"):
                st.session_state.guardrail_banner = False
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════
# DUAL-PANE WORKSPACE
# ══════════════════════════════════════════════════════════════════════════
canvas_col, agent_col = st.columns([0.65, 0.35], gap="large")


# ══════════════════════════════════════════════════════════════════════════
# MIDDLE PANE — Result Canvas
# ══════════════════════════════════════════════════════════════════════════
with canvas_col:

    # FIX #5: KPIs wrapped in a unified status-bar card
    st.markdown(
        '<div style="background:#fff;border:1px solid #E2E8F0;border-radius:12px;'
        'padding:1rem 1.25rem;box-shadow:0 1px 4px rgba(0,0,0,0.04);margin-bottom:1rem;">'
        '<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.1em;color:#94A3B8;margin-bottom:0.6rem;">📊 Daily Overview</div>',
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pets",         len(owner.pets))
    m2.metric("Due / Overdue", total_due)
    m3.metric("Required",     total_required_due)
    m4.metric("Budget (min)", owner.available_time_mins)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Agentic Optimization ─────────────────────────────────────────────
    st.markdown(
        '<div style="background:linear-gradient(135deg,#101B35 0%,#1B2E54 100%);'
        'border-radius:12px;padding:0.9rem 1.25rem 0.75rem;margin-bottom:0.75rem;'
        'border:1px solid rgba(255,107,53,0.18);box-shadow:0 4px 20px rgba(0,0,0,0.18);">'
        '<div style="display:flex;align-items:center;gap:0.75rem;">'
        '<div style="width:34px;height:34px;background:rgba(255,107,53,0.14);'
        'border:1px solid rgba(255,107,53,0.32);border-radius:9px;flex-shrink:0;'
        'display:flex;align-items:center;justify-content:center;font-size:1rem;">🤖</div>'
        '<div>'
        '<div style="color:#F1F5F9;font-weight:700;font-size:0.9rem;">Agentic Optimization</div>'
        '<div style="color:#475569;font-size:0.72rem;margin-top:2px;">'
        'ReAct loop · Conflict resolution · Safety guardrail check</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )

    if st.button("🤖  Optimize Schedule & Resolve Conflicts", type="primary", use_container_width=True):
        orchestrator.clear_trace()
        st.session_state.guardrail_result  = None
        st.session_state.guardrail_banner  = False
        with st.status("Agent is thinking…", expanded=True) as status:
            resolve_result   = orchestrator.resolve_schedule_conflicts()
            guardrail_result = orchestrator.run_final_guardrail(resolve_result["schedule"])
            st.session_state.guardrail_result = guardrail_result

            if guardrail_result.guardrail_triggered:
                st.session_state.guardrail_banner = True
                st.toast(
                    f"🛡️ Guardrail restored {guardrail_result.violation_count} required task(s)!",
                    icon="🛡️",
                )

            if resolve_result["conflicts_resolved"]:
                lbl = "✓ Done — all conflicts resolved!"
            elif resolve_result["escalated"]:
                lbl = (
                    f"Done — escalated after {resolve_result['steps_taken']} step(s). "
                    "Some conflicts may remain."
                )
            else:
                lbl = f"Done — {resolve_result['steps_taken']} step(s) taken."
            status.update(label=lbl, state="complete", expanded=False)
        # FIX #1/#2: refresh Gantt from latest owner state; also applies guardrail corrections
        st.session_state.schedule_result = Scheduler(owner).generate_schedule()

    st.divider()

    # ── Daily Plan / Gantt ───────────────────────────────────────────────
    st.markdown(
        '<div style="font-weight:700;color:#0F172A;font-size:0.95rem;margin-bottom:0.75rem;">'
        '🗓️  Gantt Daily Plan</div>',
        unsafe_allow_html=True,
    )

    # FIX #6: Generate Schedule button full-width
    if st.button("▶  Generate Schedule", type="secondary", use_container_width=True):
        if not owner.pets or not owner.get_all_tasks():
            st.warning("Add at least one pet with at least one task first.")
        else:
            # FIX #9: spinner for perceived performance
            with st.spinner("Building your schedule…"):
                st.session_state.schedule_result = Scheduler(owner).generate_schedule()

    if st.session_state.last_completed:
        st.success(f"✓ '{st.session_state.last_completed}' marked complete!")
        st.session_state.last_completed = None

    result = st.session_state.schedule_result

    if result is not None:
        # Reasoning / deficit alert
        if "Time Deficit" in result.reasoning:
            st.error(f"⚠️  {result.reasoning}")
        else:
            st.info(result.reasoning)

        # Time budget bar
        budget    = owner.available_time_mins
        time_used = result.total_time_used
        if budget > 0:
            over = f" (+{time_used - budget} over)" if time_used > budget else ""
            st.progress(
                min(time_used / budget, 1.0),
                text=f"Time used: {time_used} / {budget} min{over}",
            )
        else:
            st.progress(0.0, text="No time budget set.")

        # Conflict warnings from sweep-line
        for task_a, task_b in Scheduler(owner).detect_conflicts(result.scheduled_tasks):
            st.warning(
                f"**Overlap:** _{task_a.name}_ ends at **{task_a.end_time}** "
                f"but _{task_b.name}_ starts at **{task_b.start_time}**."
            )

        # ── Gantt chart ──────────────────────────────────────────────────
        if result.scheduled_tasks:
            # Detect whether any task has a start_time to show context hint
            timed_count = sum(1 for t in result.scheduled_tasks if t.start_time)
            if timed_count == 0:
                # FIX #3: helpful hint when no start times are assigned
                st.markdown(
                    '<div style="background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;'
                    'padding:0.6rem 1rem;font-size:0.8rem;color:#92400E;margin:0.5rem 0;">'
                    '💡 <strong>Tip:</strong> Assign start times (HH:MM) in the sidebar task form '
                    'to see tasks plotted as bars on the Gantt timeline.'
                    '</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div style="margin:0.75rem 0 0.25rem;font-size:0.65rem;font-weight:700;'
                'text-transform:uppercase;letter-spacing:0.1em;color:#94A3B8;">'
                'Timeline (06:00 – 22:00)</div>',
                unsafe_allow_html=True,
            )

            gantt_html = '<div style="padding:0.25rem 0 0.5rem;">' + _gantt_axis()
            task_pet_map: dict[int, Pet] = {
                id(task): pet for pet in owner.pets for task in pet.tasks
            }
            for task in result.scheduled_tasks:
                gantt_html += _gantt_bar(
                    task.name, task.start_time, task.duration,
                    task.is_required, is_skipped=False,
                )
            gantt_html += "</div>"
            st.markdown(gantt_html, unsafe_allow_html=True)

            # ── Task list with mark-complete ─────────────────────────────
            st.markdown(
                '<div style="margin:0.75rem 0 0.25rem;font-size:0.65rem;font-weight:700;'
                'text-transform:uppercase;letter-spacing:0.1em;color:#94A3B8;">'
                'Scheduled Tasks</div>',
                unsafe_allow_html=True,
            )
            _hs = ("font-size:0.65rem;font-weight:700;text-transform:uppercase;"
                   "letter-spacing:0.08em;color:#94A3B8;")
            h1, h2, h3, h4 = st.columns([3.5, 1.2, 1.5, 2])
            h1.markdown(f'<span style="{_hs}">Task</span>', unsafe_allow_html=True)
            h2.markdown(f'<span style="{_hs}">Min</span>',  unsafe_allow_html=True)
            h3.markdown(f'<span style="{_hs}">Priority</span>', unsafe_allow_html=True)
            h4.markdown("")

            for i, task in enumerate(result.scheduled_tasks):
                pet = task_pet_map.get(id(task))
                c1, c2, c3, c4 = st.columns([3.5, 1.2, 1.5, 2])
                lock = "\u00a0🔒" if task.is_required else ""
                c1.markdown(
                    f'<span style="font-weight:600;color:#0F172A;font-size:0.85rem;">'
                    f'{task.name}{lock}</span>',
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f'<span style="color:#64748B;font-size:0.85rem;">{task.duration}</span>',
                    unsafe_allow_html=True,
                )
                c3.markdown(_priority_badge_html(task.priority), unsafe_allow_html=True)
                # FIX #4: store pet-task index so duplicate task names complete correctly
                if pet is not None:
                    _pet_task_idx = next(
                        (idx for idx, t in enumerate(pet.tasks) if t is task), None
                    )
                    if _pet_task_idx is not None and c4.button(
                        "✓ Done", key=f"complete_{i}", use_container_width=True
                    ):
                        st.session_state.pending_complete = (pet.name, _pet_task_idx)
                        st.rerun()

        # Skipped tasks
        if result.skipped_tasks:
            with st.expander(f"⏭  {len(result.skipped_tasks)} task(s) skipped — over budget"):
                skip_html = '<div style="padding:4px 0;">'
                for t in result.skipped_tasks:
                    skip_html += _gantt_bar(
                        t.name, t.start_time, t.duration,
                        t.is_required, is_skipped=True,
                    )
                skip_html += "</div>"
                st.markdown(skip_html, unsafe_allow_html=True)

    else:
        # Empty state
        st.markdown(
            '<div style="background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:12px;'
            'padding:2.5rem;text-align:center;color:#94A3B8;margin-top:1rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📅</div>'
            '<div style="font-weight:600;color:#64748B;margin-bottom:0.35rem;font-size:0.95rem;">'
            'No schedule yet</div>'
            '<div style="font-size:0.8rem;">'
            'Click <strong>▶ Generate Schedule</strong> or describe a task to the AI Agent →'
            '</div></div>',
            unsafe_allow_html=True,
        )

    # ── Agent Reasoning expander ─────────────────────────────────────────
    if orchestrator.agent_trace:
        with st.expander("🛠️  Agent Reasoning & ReAct Log"):
            for ts in orchestrator.agent_trace:
                dot_color = "#FF6B35" if ts.action_tool != "(end_turn)" else "#94A3B8"
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;gap:0.65rem;'
                    f'margin-bottom:0.5rem;">'
                    f'<div style="min-width:22px;height:22px;background:{dot_color};color:#fff;'
                    f'border-radius:50%;display:flex;align-items:center;justify-content:center;'
                    f'font-size:0.68rem;font-weight:700;flex-shrink:0;margin-top:2px;">'
                    f'{ts.step}</div>'
                    f'<code style="background:#F1F5F9;color:#0F172A;border-radius:5px;'
                    f'padding:2px 8px;font-size:0.76rem;font-weight:600;'
                    f'border:1px solid #E2E8F0;">{ts.action_tool}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Thought:** {ts.thought}")
                if ts.action_input:
                    st.json(ts.action_input)
                st.markdown("**Observation:**")
                st.json(ts.observation)
                st.divider()

    # Performance report
    if orchestrator.run_metrics.total_calls > 0:
        with st.expander("📊  Performance & Cache Report"):
            st.markdown(orchestrator.run_metrics.format_summary())


# ══════════════════════════════════════════════════════════════════════════
# RIGHT PANE — Agent Assistant Chat
# FIX #7: Entire pane wrapped in a persistent dark card
# ══════════════════════════════════════════════════════════════════════════
with agent_col:
    # Dark card wrapper — open
    st.markdown(
        '<div style="background:linear-gradient(180deg,#0D1929 0%,#101B35 100%);'
        'border:1px solid rgba(255,255,255,0.06);border-radius:14px;'
        'padding:1rem 1.25rem 0.5rem;">',
        unsafe_allow_html=True,
    )

    # Pane header row
    hdr_left, hdr_right = st.columns([3, 1])
    with hdr_left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.6rem;'
            'padding-bottom:0.75rem;border-bottom:1px solid rgba(255,255,255,0.07);'
            'margin-bottom:0.75rem;">'
            '<div style="width:30px;height:30px;background:rgba(255,107,53,0.14);'
            'border:1px solid rgba(255,107,53,0.30);border-radius:8px;'
            'display:flex;align-items:center;justify-content:center;font-size:0.95rem;">💬</div>'
            '<div>'
            '<div style="color:#E2E8F0;font-weight:700;font-size:0.88rem;">AI Agent</div>'
            '<div style="color:#475569;font-size:0.68rem;margin-top:1px;">NL task entry · HAIKU-4.5</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
    # FIX #14: Clear chat button
    with hdr_right:
        st.markdown('<div class="btn-ghost">', unsafe_allow_html=True)
        if st.button("🗑 Clear", key="clear_chat", help="Clear chat history", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<p style="color:#475569;font-size:0.76rem;line-height:1.55;margin:0 0 0.75rem;">'
        'Describe a task in plain English. The agent parses it and adds it automatically.'
        '</p>',
        unsafe_allow_html=True,
    )

    # Scrollable chat history
    # FIX #2: min-height on inner div so empty state centres correctly
    chat_box = st.container(height=560)
    with chat_box:
        if not st.session_state.chat_history:
            st.markdown(
                '<div style="min-height:520px;display:flex;flex-direction:column;'
                'align-items:center;justify-content:center;padding:2rem 1rem;text-align:center;">'
                '<div style="font-size:2.5rem;margin-bottom:0.75rem;opacity:0.3;">💬</div>'
                '<div style="color:#475569;font-size:0.8rem;line-height:1.6;">'
                'No messages yet.<br>'
                'Type a task description below to get started.'
                '</div></div>',
                unsafe_allow_html=True,
            )
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    # Per-message ReAct trace nested in expander
                    if msg.get("trace"):
                        with st.expander("🛠 View Agent Reasoning"):
                            for step in msg["trace"]:
                                st.markdown(
                                    f'<code style="background:rgba(255,255,255,0.08);'
                                    f'color:#CBD5E1;padding:2px 8px;border-radius:5px;'
                                    f'font-size:0.76rem;border:1px solid rgba(255,255,255,0.12);">'
                                    f'{step["action_tool"]}</code>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(f"**Thought:** {step['thought']}")
                                st.json(step.get("observation", {}))

    # Hint text
    st.markdown(
        '<div style="margin-top:0.4rem;color:#334155;font-size:0.68rem;'
        'padding-bottom:0.5rem;">'
        '↓ Type in the chat box below</div>',
        unsafe_allow_html=True,
    )

    # Dark card wrapper — close
    st.markdown("</div>", unsafe_allow_html=True)


# ── Floating chat input ───────────────────────────────────────────────────
# FIX #13: shorter placeholder text to avoid clipping on narrow column
if prompt := st.chat_input("Describe a task in plain English…"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    trace_before = len(orchestrator.agent_trace)
    parse_result = orchestrator.parse_nl_task(prompt)
    new_trace    = [t.as_dict() for t in orchestrator.agent_trace[trace_before:]]
    # FIX #6: remove NL-parse steps from main optimization trace to avoid accumulation
    del orchestrator.agent_trace[trace_before:]

    if parse_result.success:
        task_name     = (parse_result.task_dict or {}).get("name", "task")
        response_text = (
            f"Done! Task **{task_name}** has been added. "
            "Hit **▶ Generate Schedule** to see it in the Gantt view, or "
            "**🤖 Optimize Schedule** to auto-resolve any conflicts."
        )
        # FIX #3: clear stale Gantt (mirrors what the sidebar Add Task form does)
        st.session_state.schedule_result = None
        # FIX #10: nudge user to persist the new task
        st.toast("Task added! Click 💾 Save Data in the sidebar to persist it.", icon="💾")
    elif parse_result.needs_clarification:
        response_text = f"Could you clarify: {parse_result.clarification_question}"
    else:
        response_text = f"I wasn't able to process that — {parse_result.error}"

    st.session_state.chat_history.append({
        "role":    "PawPal Agent",
        "content": response_text,
        "trace":   new_trace,
    })
    st.rerun()