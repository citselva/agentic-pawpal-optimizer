import json
import os
from datetime import date

import anthropic
import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler
from agent.orchestrator import PawPalOrchestrator

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PawPal+ | Smart Pet Care",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design system ─────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Base typography ──────────────────────────────── */
html, body, [class*="css"], .stApp,
.stMarkdown, .stText, button, input, select, textarea {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Page background ──────────────────────────────── */
.stApp { background-color: #F5F7FA; }

/* ── Hide Streamlit chrome ────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* ── Sidebar: dark navy ───────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #101B35 !important;
    border-right: none !important;
}
[data-testid="stSidebar"] > div:first-child {
    background-color: #101B35 !important;
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption { color: #64748B !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4 { color: #F1F5F9 !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,107,53,0.10) !important;
    color: #FB923C !important;
    border: 1px solid rgba(255,107,53,0.30) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.18s ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,107,53,0.20) !important;
    border-color: rgba(255,107,53,0.55) !important;
    transform: none !important;
}
[data-testid="stSidebar"] [data-testid="stDataFrame"] {
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}

/* ── Main content padding ─────────────────────────── */
.main .block-container {
    padding-top: 0.75rem !important;
    padding-bottom: 3rem !important;
}

/* ── All buttons ──────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.01em !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.18s ease !important;
    cursor: pointer !important;
}
/* Primary — coral gradient */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #FF6B35 0%, #E8531E 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: 0 4px 14px rgba(255,107,53,0.38) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 22px rgba(255,107,53,0.52) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 2px 8px rgba(255,107,53,0.30) !important;
}
/* Secondary — outlined coral */
.stButton > button[kind="secondary"] {
    background: #FFFFFF !important;
    color: #FF6B35 !important;
    border: 1.5px solid #FF6B35 !important;
}
.stButton > button[kind="secondary"]:hover {
    background: #FFF5F1 !important;
    transform: translateY(-1px) !important;
}
/* Default */
.stButton > button:not([kind="primary"]):not([kind="secondary"]) {
    background: #FFFFFF !important;
    color: #374151 !important;
    border: 1.5px solid #E2E8F0 !important;
}
.stButton > button:not([kind="primary"]):not([kind="secondary"]):hover {
    border-color: #FF6B35 !important;
    color: #FF6B35 !important;
    transform: translateY(-1px) !important;
}

/* ── Form submit buttons — teal ───────────────────── */
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #2EC4B6 0%, #1EA89B 100%) !important;
    color: #FFFFFF !important;
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

/* ── Text inputs ──────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 8px !important;
    border: 1.5px solid #E2E8F0 !important;
    background: #FFFFFF !important;
    color: #0F172A !important;
    font-size: 0.9rem !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #FF6B35 !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.12) !important;
    outline: none !important;
}

/* ── Selectbox ────────────────────────────────────── */
.stSelectbox [data-baseweb="select"] > div {
    border-radius: 8px !important;
    border: 1.5px solid #E2E8F0 !important;
    background: #FFFFFF !important;
    transition: border-color 0.18s ease !important;
}
.stSelectbox [data-baseweb="select"] > div:focus-within {
    border-color: #FF6B35 !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.12) !important;
}

/* ── Progress bar ─────────────────────────────────── */
[data-testid="stProgressBarValue"] {
    background: linear-gradient(90deg, #FF6B35 0%, #2EC4B6 100%) !important;
    border-radius: 999px !important;
}

/* ── Expanders ────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    margin-bottom: 0.5rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #0F172A !important;
    padding: 0.875rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { color: #FF6B35 !important; }

/* ── Metric cards ─────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #64748B !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
}

/* ── Alert / banners ──────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 4px !important;
}

/* ── Chat messages ────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    margin-bottom: 0.5rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}

/* ── Forms ────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    background: #FAFBFF !important;
    padding: 1.25rem !important;
}

/* ── Tables ───────────────────────────────────────── */
[data-testid="stTable"] table {
    border-radius: 8px !important;
    border: 1px solid #E2E8F0 !important;
    overflow: hidden !important;
    font-size: 0.875rem !important;
}
[data-testid="stTable"] th {
    background: #F8FAFC !important;
    color: #64748B !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stTable"] tr:hover td { background: #FFF8F5 !important; }

/* ── Dataframe ────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    overflow: hidden !important;
    border: 1px solid #E2E8F0 !important;
}

/* ── Horizontal rule ──────────────────────────────── */
hr {
    border-color: #E2E8F0 !important;
    margin: 1.25rem 0 !important;
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

# ── HTML helpers ──────────────────────────────────────────────────────────

def _section_header(icon: str, title: str, subtitle: str = "") -> str:
    sub = (
        f'<p style="margin:0.2rem 0 0;color:#64748B;font-size:0.78rem;font-weight:400;">{subtitle}</p>'
        if subtitle else ""
    )
    return f"""
    <div style="display:flex;align-items:center;gap:0.65rem;margin-bottom:0.9rem;">
        <div style="
            width:30px;height:30px;background:#FFF0EB;border-radius:7px;flex-shrink:0;
            display:flex;align-items:center;justify-content:center;font-size:0.9rem;
        ">{icon}</div>
        <div>
            <div style="font-weight:700;color:#0F172A;font-size:0.95rem;
                letter-spacing:-0.01em;line-height:1.2;">{title}</div>
            {sub}
        </div>
    </div>
    """


def _priority_badge(p: int) -> str:
    """Plain-text label for st.table / st.dataframe cells."""
    if p >= 5:
        return "High"
    if p >= 3:
        return "Medium"
    return "Low"


def _priority_badge_html(p: int) -> str:
    """Pill badge rendered via st.markdown(unsafe_allow_html=True)."""
    if p >= 5:
        return (
            '<span style="display:inline-block;background:#FEE2E2;color:#991B1B;'
            'padding:3px 10px;border-radius:999px;font-size:0.7rem;font-weight:700;'
            'letter-spacing:0.04em;">HIGH</span>'
        )
    if p >= 3:
        return (
            '<span style="display:inline-block;background:#FEF3C7;color:#92400E;'
            'padding:3px 10px;border-radius:999px;font-size:0.7rem;font-weight:700;'
            'letter-spacing:0.04em;">MED</span>'
        )
    return (
        '<span style="display:inline-block;background:#D1FAE5;color:#065F46;'
        'padding:3px 10px;border-radius:999px;font-size:0.7rem;font-weight:700;'
        'letter-spacing:0.04em;">LOW</span>'
    )


PRIORITY_MAP = {"low": 1, "medium": 3, "high": 5}

# ── Session State ─────────────────────────────────────────────────────────
if "owner_data" not in st.session_state:
    if os.path.exists("data/data.json"):
        st.session_state.owner_data = Owner.load_from_json("data/data.json")
    else:
        default_pet = Pet(name="Mochi", species="dog", age=3)
        default_owner = Owner(name="Jordan", available_time_mins=60)
        default_owner.pets.append(default_pet)
        st.session_state.owner_data = default_owner

if "owner_name" not in st.session_state:
    st.session_state.owner_name = st.session_state.owner_data.name

if "available_time" not in st.session_state:
    st.session_state.available_time = st.session_state.owner_data.available_time_mins

if "schedule_result" not in st.session_state:
    st.session_state.schedule_result = None

if "pending_complete" not in st.session_state:
    st.session_state.pending_complete = None

if "last_completed" not in st.session_state:
    st.session_state.last_completed = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "guardrail_result" not in st.session_state:
    st.session_state.guardrail_result = None

if "show_guardrail_logs" not in st.session_state:
    st.session_state.show_guardrail_logs = False

if "orchestrator" not in st.session_state:
    _client = anthropic.Anthropic()
    st.session_state.orchestrator = PawPalOrchestrator(
        owner=st.session_state.owner_data,
        client=_client,
    )

# ── Process pending task completion before rendering ──────────────────────
if st.session_state.pending_complete is not None:
    pet_name, task_name = st.session_state.pending_complete
    for pet in st.session_state.owner_data.pets:
        if pet.name == pet_name:
            for task in pet.tasks:
                if task.name == task_name and not task.is_completed:
                    pet.complete_task(task)
                    st.session_state.last_completed = task_name
                    break
    st.session_state.pending_complete = None
    st.session_state.schedule_result = None

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:0 0 1.25rem;border-bottom:1px solid rgba(255,255,255,0.07);
        margin-bottom:1.5rem;">
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <div style="width:36px;height:36px;background:rgba(255,107,53,0.15);
                border:1px solid rgba(255,107,53,0.35);border-radius:9px;
                display:flex;align-items:center;justify-content:center;font-size:1.1rem;">
                🐾
            </div>
            <div>
                <div style="color:#F1F5F9;font-weight:700;font-size:0.95rem;
                    letter-spacing:-0.01em;">PawPal<span style='color:#FB923C;'>+</span></div>
                <div style="color:#334155;font-size:0.7rem;margin-top:1px;">Developer Console</div>
            </div>
        </div>
    </div>
    <p style="color:#334155;font-size:0.68rem;font-weight:700;text-transform:uppercase;
        letter-spacing:0.12em;margin:0 0 0.65rem;">🛡️ Safety & Audit</p>
    """, unsafe_allow_html=True)

    if st.button(
        "View Guardrail Logs",
        use_container_width=True,
        key="toggle_logs_btn",
    ):
        st.session_state.show_guardrail_logs = not st.session_state.show_guardrail_logs

    if st.session_state.show_guardrail_logs:
        log_path = "data/guardrail_violations.jsonl"
        if os.path.exists(log_path):
            records = []
            with open(log_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            if records:
                st.dataframe(records, use_container_width=True)
            else:
                st.markdown(
                    '<p style="color:#64748B;font-size:0.8rem;padding:0.5rem 0;">'
                    'No violations logged yet.</p>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<p style="color:#64748B;font-size:0.8rem;padding:0.5rem 0;">'
                'Log file not found.</p>',
                unsafe_allow_html=True,
            )

    st.markdown("""
    <div style="margin-top:2rem;padding-top:1.25rem;border-top:1px solid rgba(255,255,255,0.06);">
        <p style="color:#334155;font-size:0.68rem;font-weight:700;text-transform:uppercase;
            letter-spacing:0.12em;margin:0 0 0.5rem;">About</p>
        <p style="color:#475569;font-size:0.75rem;line-height:1.6;margin:0;">
            PawPal+ uses a ReAct agent loop with Claude to resolve schedule conflicts
            and enforce safety guardrails on every optimization run.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ── Hero header ───────────────────────────────────────────────────────────
st.markdown("""
<div style="
    background: linear-gradient(135deg, #101B35 0%, #1A2E55 55%, #152B50 100%);
    border-radius: 16px;
    padding: 1.65rem 2rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.06);
">
    <div style="
        position:absolute;right:-0.5rem;top:50%;transform:translateY(-50%);
        font-size:9rem;opacity:0.05;pointer-events:none;user-select:none;line-height:1;
    ">🐾</div>
    <div style="position:relative;z-index:1;display:flex;align-items:center;gap:1.25rem;">
        <div style="
            background:rgba(255,107,53,0.15);border:1px solid rgba(255,107,53,0.40);
            border-radius:13px;width:54px;height:54px;flex-shrink:0;
            display:flex;align-items:center;justify-content:center;font-size:1.8rem;
        ">🐾</div>
        <div>
            <h1 style="margin:0;color:#FFFFFF;font-size:1.85rem;font-weight:800;
                letter-spacing:-0.03em;line-height:1.1;">
                PawPal<span style="color:#FF6B35;">+</span>
            </h1>
            <p style="margin:0.3rem 0 0;color:#64748B;font-size:0.85rem;font-weight:400;">
                AI-powered pet care scheduling &nbsp;·&nbsp; conflict detection &nbsp;·&nbsp; safety guardrails
            </p>
        </div>
        <div style="margin-left:auto;display:flex;gap:0.5rem;flex-wrap:wrap;">
            <span style="background:rgba(46,196,182,0.12);border:1px solid rgba(46,196,182,0.35);
                color:#2EC4B6;font-size:0.72rem;font-weight:700;letter-spacing:0.04em;
                padding:4px 10px;border-radius:999px;">HAIKU-4.5 &amp; SONNET-4.6</span>
            <span style="background:rgba(255,107,53,0.12);border:1px solid rgba(255,107,53,0.35);
                color:#FF6B35;font-size:0.72rem;font-weight:700;letter-spacing:0.04em;
                padding:4px 10px;border-radius:999px;">REACT AGENT</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Agentic Chat ──────────────────────────────────────────────────────────
orchestrator: PawPalOrchestrator = st.session_state.orchestrator

st.markdown("""
<div style="
    background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;
    padding:1rem 1.25rem 0.5rem;margin-bottom:0.5rem;
    box-shadow:0 1px 4px rgba(0,0,0,0.04);
">
    <div style="display:flex;align-items:center;gap:0.6rem;
        padding-bottom:0.75rem;border-bottom:1px solid #F1F5F9;margin-bottom:0.25rem;">
        <span style="font-size:1.1rem;">💬</span>
        <span style="font-weight:700;color:#0F172A;font-size:0.95rem;
            letter-spacing:-0.01em;">Natural-Language Task Entry</span>
        <span style="margin-left:auto;background:#FFF0EB;color:#FF6B35;
            font-size:0.68rem;font-weight:700;letter-spacing:0.05em;
            padding:3px 9px;border-radius:999px;">AI AGENT</span>
    </div>
    <p style="margin:0.5rem 0 0;color:#94A3B8;font-size:0.8rem;">
        Describe a task in plain English — the agent extracts and schedules it automatically.
    </p>
</div>
""", unsafe_allow_html=True)

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("e.g. 'Add a 45 min walk for Buddy at 7am tomorrow'"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    parse_result = orchestrator.parse_nl_task(prompt)

    if parse_result.success:
        task_name = (parse_result.task_dict or {}).get("name", "task")
        response_text = (
            f"Done! Task **{task_name}** has been added to the schedule. "
            "Run **Optimize Schedule** to resolve any conflicts."
        )
    elif parse_result.needs_clarification:
        response_text = f"Could you clarify: {parse_result.clarification_question}"
    else:
        response_text = f"I wasn't able to process that — {parse_result.error}"

    st.session_state.chat_history.append({"role": "PawPal Agent", "content": response_text})
    with st.chat_message("PawPal Agent"):
        st.markdown(response_text)

st.markdown("<div style='margin-bottom:1.25rem;'></div>", unsafe_allow_html=True)

# ── Two-column layout ─────────────────────────────────────────────────────
col_left, col_right = st.columns([2, 3], gap="large")

# ── LEFT COLUMN ───────────────────────────────────────────────────────────
with col_left:

    # Owner Settings
    st.markdown(_section_header("👤", "Owner Settings"), unsafe_allow_html=True)
    owner_name = st.text_input("Owner name", key="owner_name")
    available_time = st.number_input(
        "Available time (minutes)", min_value=0, max_value=480, key="available_time"
    )
    st.session_state.owner_data.name = owner_name
    st.session_state.owner_data.available_time_mins = int(available_time)

    if st.button("💾  Save Data", use_container_width=True):
        st.session_state.owner_data.save_to_json("data/data.json")
        st.success("Saved to data/data.json")

    st.divider()

    # Add Pet
    st.markdown(
        _section_header("🐕", "Add a Pet", "Register a new pet to the schedule"),
        unsafe_allow_html=True,
    )
    with st.form("add_pet_form", clear_on_submit=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            new_pet_name = st.text_input("Name")
        with p2:
            new_pet_species = st.selectbox("Species", ["dog", "cat", "other"])
        with p3:
            new_pet_age = st.number_input("Age (yrs)", min_value=0, max_value=30, value=1)
        submitted_pet = st.form_submit_button("Add Pet", use_container_width=True)

    if submitted_pet:
        if new_pet_name.strip():
            new_pet = Pet(
                name=new_pet_name.strip(),
                species=new_pet_species,
                age=int(new_pet_age),
            )
            st.session_state.owner_data.pets.append(new_pet)
            st.session_state.schedule_result = None
            st.success(f"'{new_pet.name}' added!")
        else:
            st.warning("Please enter a pet name.")

    st.divider()

    # Add Task
    st.markdown(
        _section_header("📋", "Add a Task", "Manually create a task and assign it to a pet"),
        unsafe_allow_html=True,
    )
    owner = st.session_state.owner_data
    if not owner.pets:
        st.markdown("""
        <div style="background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:10px;
            padding:1rem;text-align:center;color:#94A3B8;font-size:0.85rem;">
            Add a pet first to start adding tasks.
        </div>
        """, unsafe_allow_html=True)
    else:
        with st.form("add_task_form", clear_on_submit=True):
            pet_names = [p.name for p in owner.pets]
            selected_pet_name = st.selectbox("Assign to pet", pet_names)

            t1, t2, t3 = st.columns(3)
            with t1:
                task_title = st.text_input("Task title", value="Morning walk")
            with t2:
                duration = st.number_input(
                    "Duration (min)", min_value=1, max_value=240, value=20
                )
            with t3:
                priority_label = st.selectbox("Priority", ["low", "medium", "high"], index=2)

            t4, t5 = st.columns(2)
            with t4:
                frequency = st.selectbox("Frequency", ["one-off", "daily", "weekly"])
            with t5:
                is_required = st.checkbox("Mark as required")

            submitted_task = st.form_submit_button("Add Task", use_container_width=True)

        if submitted_task:
            if task_title.strip():
                new_task = Task(
                    name=task_title.strip(),
                    duration=int(duration),
                    priority=PRIORITY_MAP[priority_label],
                    is_required=is_required,
                    frequency=frequency,
                )
                target_pet = next(p for p in owner.pets if p.name == selected_pet_name)
                target_pet.tasks.append(new_task)
                st.session_state.schedule_result = None
                st.success(f"'{new_task.name}' added to {target_pet.name}.")
            else:
                st.warning("Please enter a task title.")

# ── RIGHT COLUMN ──────────────────────────────────────────────────────────
with col_right:
    owner = st.session_state.owner_data
    today = date.today()

    # Quick-stats metrics row
    total_due = sum(
        len([t for t in pet.tasks if t.due_date <= today and not t.is_completed])
        for pet in owner.pets
    )
    total_required_due = sum(
        len([
            t for t in pet.tasks
            if t.is_required and t.due_date <= today and not t.is_completed
        ])
        for pet in owner.pets
    )
    total_mins = sum(
        t.duration
        for pet in owner.pets
        for t in pet.tasks
        if t.due_date <= today and not t.is_completed
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pets", len(owner.pets))
    m2.metric("Tasks Due", total_due)
    m3.metric("Required", total_required_due)
    m4.metric("Total Mins", total_mins)

    st.markdown("<div style='margin-bottom:1rem;'></div>", unsafe_allow_html=True)

    # Pet summary
    st.markdown(
        _section_header("📅", "Today's Pet Summary"),
        unsafe_allow_html=True,
    )

    if not owner.pets:
        st.markdown("""
        <div style="background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:10px;
            padding:1.5rem;text-align:center;color:#94A3B8;font-size:0.875rem;">
            No pets yet. Add one using the form on the left.
        </div>
        """, unsafe_allow_html=True)
    else:
        for pet in owner.pets:
            due_tasks = [t for t in pet.tasks if t.due_date <= today and not t.is_completed]
            badge_color = "#FEE2E2" if due_tasks else "#D1FAE5"
            badge_text_color = "#991B1B" if due_tasks else "#065F46"
            badge_label = f"{len(due_tasks)} due" if due_tasks else "all done"
            label = (
                f"{pet.get_summary()}  —  "
                f'<span style="background:{badge_color};color:{badge_text_color};'
                f'padding:1px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;">'
                f'{badge_label}</span>'
            )
            with st.expander(pet.get_summary(), expanded=False):
                if not due_tasks:
                    st.markdown(
                        '<p style="color:#10B981;font-size:0.85rem;margin:0;">✓ All tasks complete for today!</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.table(
                        [
                            {
                                "Task": t.name,
                                "Duration (min)": t.duration,
                                "Priority": _priority_badge(t.priority),
                                "Frequency": t.frequency,
                                "Required": "✓" if t.is_required else "",
                            }
                            for t in due_tasks
                        ]
                    )

    st.divider()

    # Optimization panel
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #101B35 0%, #1B2E54 100%);
        border-radius: 14px;
        padding: 1.25rem 1.5rem 0.9rem;
        margin-bottom: 0.9rem;
        border: 1px solid rgba(255,107,53,0.18);
        box-shadow: 0 4px 20px rgba(0,0,0,0.18);
    ">
        <div style="display:flex;align-items:center;gap:0.8rem;">
            <div style="
                width:38px;height:38px;background:rgba(255,107,53,0.14);
                border:1px solid rgba(255,107,53,0.32);border-radius:9px;flex-shrink:0;
                display:flex;align-items:center;justify-content:center;font-size:1.15rem;
            ">🤖</div>
            <div>
                <div style="color:#F1F5F9;font-weight:700;font-size:0.95rem;
                    letter-spacing:-0.01em;">Agentic Optimization</div>
                <div style="color:#475569;font-size:0.78rem;margin-top:2px;">
                    ReAct loop · Conflict resolution · Safety guardrail check
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(
        "🤖  Optimize Schedule & Resolve Conflicts",
        type="primary",
        use_container_width=True,
    ):
        orchestrator.clear_trace()
        st.session_state.guardrail_result = None
        with st.status("Agent is thinking...", expanded=True) as status:
            resolve_result = orchestrator.resolve_schedule_conflicts()
            guardrail_result = orchestrator.run_final_guardrail(resolve_result["schedule"])
            st.session_state.guardrail_result = guardrail_result
            if resolve_result["conflicts_resolved"]:
                status_label = "✓ Done — all conflicts resolved!"
            elif resolve_result["escalated"]:
                status_label = (
                    f"Done — escalated after {resolve_result['steps_taken']} step(s). "
                    "Some conflicts may remain."
                )
            else:
                status_label = f"Done — {resolve_result['steps_taken']} step(s) taken."
            status.update(label=status_label, state="complete", expanded=False)

    # Safety notification (same render pass as button)
    guardrail = st.session_state.guardrail_result
    if guardrail is not None and guardrail.guardrail_triggered:
        st.error(guardrail.as_ui_message())

    # Reasoning trace
    if orchestrator.agent_trace:
        with st.expander("🔍  View Agent Reasoning Trace"):
            for ts in orchestrator.agent_trace:
                dot_color = "#FF6B35" if ts.action_tool != "(end_turn)" else "#94A3B8"
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:flex-start;gap:0.7rem;
                        margin-bottom:0.5rem;">
                        <div style="
                            min-width:26px;height:26px;background:{dot_color};color:#FFFFFF;
                            border-radius:50%;display:flex;align-items:center;
                            justify-content:center;font-size:0.72rem;font-weight:700;
                            flex-shrink:0;margin-top:2px;
                        ">{ts.step}</div>
                        <code style="background:#F1F5F9;color:#0F172A;border-radius:5px;
                            padding:2px 8px;font-size:0.8rem;font-weight:600;
                            border:1px solid #E2E8F0;">{ts.action_tool}</code>
                    </div>
                    """,
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
        with st.expander("📊  Performance & Cost Report"):
            st.markdown(orchestrator.run_metrics.format_summary())

    st.divider()

    # Daily Plan
    st.markdown(
        _section_header("🗓️", "Daily Plan", "Two-phase tiered scheduler across all pets and tasks"),
        unsafe_allow_html=True,
    )

    if st.button("Generate Schedule", type="secondary", use_container_width=True):
        if not owner.pets or not owner.get_all_tasks():
            st.warning("Add at least one pet with at least one task first.")
        else:
            scheduler = Scheduler(owner)
            st.session_state.schedule_result = scheduler.generate_schedule()

    if st.session_state.last_completed:
        st.success(f"✓ '{st.session_state.last_completed}' marked complete!")
        st.session_state.last_completed = None

    result = st.session_state.schedule_result
    if result is not None:

        # Executive summary banner
        if "Time Deficit" in result.reasoning:
            st.error(f"⚠️ {result.reasoning}")
        else:
            st.info(result.reasoning)

        # Time budget progress bar
        budget = owner.available_time_mins
        time_used = result.total_time_used
        if budget > 0:
            progress_val = min(time_used / budget, 1.0)
            over = f" (+{time_used - budget} over)" if time_used > budget else ""
            st.progress(
                progress_val,
                text=f"Time used: {time_used} / {budget} min{over}",
            )
        else:
            st.progress(0.0, text="No time budget set.")

        # Conflict warnings
        conflicts = Scheduler(owner).detect_conflicts(result.scheduled_tasks)
        for task_a, task_b in conflicts:
            st.warning(
                f"**Overlap:** _{task_a.name}_ ends at **{task_a.end_time}** "
                f"but _{task_b.name}_ starts at **{task_b.start_time}**."
            )

        # Schedule task table
        if result.scheduled_tasks:
            st.markdown("""
            <div style="margin:1rem 0 0.25rem;">
                <span style="font-size:0.7rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.09em;color:#94A3B8;">Scheduled Tasks</span>
            </div>
            """, unsafe_allow_html=True)

            # Header row
            _hs = "font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#94A3B8;"
            h_name, h_dur, h_pri, h_start, h_action = st.columns([3, 1.2, 1.5, 1.2, 2])
            h_name.markdown(f'<span style="{_hs}">Task</span>', unsafe_allow_html=True)
            h_dur.markdown(f'<span style="{_hs}">Duration</span>', unsafe_allow_html=True)
            h_pri.markdown(f'<span style="{_hs}">Priority</span>', unsafe_allow_html=True)
            h_start.markdown(f'<span style="{_hs}">Start</span>', unsafe_allow_html=True)
            h_action.markdown("")

            task_pet_map: dict[int, Pet] = {}
            for pet in owner.pets:
                for task in pet.tasks:
                    task_pet_map[id(task)] = pet

            for i, task in enumerate(result.scheduled_tasks):
                pet = task_pet_map.get(id(task))
                c_name, c_dur, c_pri, c_start, c_action = st.columns([3, 1.2, 1.5, 1.2, 2])

                lock = (
                    ' <span style="color:#FF6B35;font-size:0.75rem;">🔒</span>'
                    if task.is_required else ""
                )
                c_name.markdown(
                    f'<span style="font-weight:600;color:#0F172A;font-size:0.875rem;">'
                    f'{task.name}{lock}</span>',
                    unsafe_allow_html=True,
                )
                c_dur.markdown(
                    f'<span style="color:#64748B;font-size:0.875rem;">{task.duration} min</span>',
                    unsafe_allow_html=True,
                )
                c_pri.markdown(_priority_badge_html(task.priority), unsafe_allow_html=True)
                c_start.markdown(
                    f'<span style="font-family:monospace;color:#475569;font-size:0.875rem;">'
                    f'{task.start_time or "—"}</span>',
                    unsafe_allow_html=True,
                )
                if pet is not None:
                    if c_action.button("✓ Done", key=f"complete_{i}", use_container_width=True):
                        st.session_state.pending_complete = (pet.name, task.name)
                        st.rerun()

        # Skipped tasks
        if result.skipped_tasks:
            with st.expander(
                f"⏭  {len(result.skipped_tasks)} task(s) skipped — exceeded time budget"
            ):
                st.dataframe(
                    [
                        {
                            "Name": t.name,
                            "Duration (min)": t.duration,
                            "Priority": _priority_badge(t.priority),
                        }
                        for t in result.skipped_tasks
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
