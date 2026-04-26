import json
import os
import re
from datetime import date, datetime

import anthropic
import streamlit as st
import streamlit.components.v1 as components
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
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap');

@keyframes chatEntrance {
    0% { opacity: 0; transform: translateY(20px) scale(0.97); filter: blur(5px); }
    100% { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
}

:root {
    --navy:       #101B35;
    --coral:      #FF6B35;
    --coral-dark: #E8531E;
    --teal:       #2EC4B6;
    --teal-dark:  #1EA89B;
    --slate:      #F5F7FA;
    --border:     #E2E8F0;
    --text:       #0F172A;
    --muted:      #64748B;
    --white:      #FFFFFF;
}

html, body, [class*="css"], .stApp,
.stMarkdown, .stText, button, input, select, textarea {
    font-family: 'DM Sans', system-ui, sans-serif !important;
}
code, pre, .stCode { font-family: 'DM Mono', monospace !important; }
.stApp { background-color: var(--slate); }
.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 3rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}
.stApp, section.main, .main .block-container,
[data-testid="stAppViewContainer"], [data-testid="stAppViewBlockContainer"], [data-testid="stHorizontalBlock"] {
    overflow: visible !important;
}
#MainMenu, footer { visibility: hidden; }


/* ════════════════════════════════════════════════════════════════════
   SIDEBAR — dark navy #101B35
   FIX [6][7][8]: ALL Streamlit-generated labels must be overridden
   ════════════════════════════════════════════════════════════════════ */

[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {
    background-color: var(--navy) !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}

/* Every label Streamlit renders inside the sidebar */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] label p,
[data-testid="stSidebar"] label span,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] .stRadio label span,
[data-testid="stSidebar"] .stCheckbox label span,
[data-testid="stSidebar"] small {
    color: #CBD5E1 !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #F1F5F9 !important; }

/* Sidebar buttons - only apply subtle style to secondary (default) buttons */
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background: rgba(255,107,53,0.12) !important;
    color: #FB923C !important;
    border: 1px solid rgba(255,107,53,0.35) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.18s ease !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background: rgba(255,107,53,0.24) !important;
    color: #FFFFFF !important;
}

/* Sidebar text/number inputs */
[data-testid="stSidebar"] .stTextInput div,
[data-testid="stSidebar"] .stNumberInput div {
    background-color: transparent !important;
}
[data-testid="stSidebar"] .stTextInput div[data-baseweb="base-input"],
[data-testid="stSidebar"] .stNumberInput div[data-baseweb="base-input"] {
    background-color: rgba(255,255,255,0.09) !important;
    border: 1.5px solid rgba(255,255,255,0.18) !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input {
    color: #F1F5F9 !important;
    background-color: transparent !important;
}
[data-testid="stSidebar"] .stTextInput input::placeholder,
[data-testid="stSidebar"] .stNumberInput input::placeholder {
    color: #64748B !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] .stTextInput div[data-baseweb="base-input"]:focus-within,
[data-testid="stSidebar"] .stNumberInput div[data-baseweb="base-input"]:focus-within {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.15) !important;
    background-color: rgba(255,255,255,0.13) !important;
}
[data-testid="stSidebar"] .stNumberInput button {
    color: #94A3B8 !important;
    background: rgba(255,255,255,0.07) !important;
    border-color: rgba(255,255,255,0.12) !important;
}
[data-testid="stSidebar"] .stNumberInput button:hover {
    color: #E2E8F0 !important;
    background: rgba(255,255,255,0.14) !important;
}

/* Sidebar select */
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] span {
    background: rgba(255,255,255,0.09) !important;
    border-color: rgba(255,255,255,0.18) !important;
    color: #E2E8F0 !important;
    border-radius: 8px !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] {
    background: #1A2E55 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
}
[data-baseweb="popover"] [data-baseweb="option"] {
    color: #CBD5E1 !important;
    background: transparent !important;
}
[data-baseweb="popover"] [data-baseweb="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] {
    background: rgba(255,107,53,0.18) !important;
    color: #FB923C !important;
}

[data-testid="stSidebar"] [data-testid="stForm"] {
    background: rgba(255,255,255,0.03) !important;
    border-color: rgba(255,255,255,0.09) !important;
    border-radius: 10px !important;
}
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.09) !important; }

[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border-color: rgba(255,255,255,0.09) !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {
    color: #CBD5E1 !important;
}

/* Removed Date Input CSS to fix border gap glitch */


/* ════════════════════════════════════════════════════════════════════
   BUTTONS — main area
   ════════════════════════════════════════════════════════════════════ */

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

/* Ghost button styling for Clear Button in right pane */
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stColumn"]:nth-of-type(2) button {
    background: rgba(255,255,255,0.12) !important;
    color: #E2E8F0 !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 6px !important;
    font-size: 0.72rem !important;
    padding: 0.25rem 0.6rem !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
}
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stColumn"]:nth-of-type(2) button div[data-testid="stMarkdownContainer"] {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 100% !important;
}
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stColumn"]:nth-of-type(2) button p {
    text-align: center !important;
    margin: 0 !important;
}
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stColumn"]:nth-of-type(2) button:hover {
    background: rgba(255,255,255,0.22) !important;
    color: #FFFFFF !important;
    border-color: rgba(255,255,255,0.40) !important;
}


/* ════════════════════════════════════════════════════════════════════
   MAIN AREA — inputs on white bg
   ════════════════════════════════════════════════════════════════════ */

.main .stTextInput input,
.main .stNumberInput input {
    border-radius: 8px !important;
    border: 1.5px solid var(--border) !important;
    background: var(--white) !important;
    color: var(--text) !important;
}
.main .stTextInput input:focus,
.main .stNumberInput input:focus {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 3px rgba(255,107,53,0.12) !important;
}
.main .stTextInput input::placeholder,
.main .stNumberInput input::placeholder { color: var(--muted) !important; opacity: 1 !important; }
.main label, .main label p, .main label span { color: var(--text) !important; }
.main .stSelectbox [data-baseweb="select"] > div { background: var(--white) !important; border-color: var(--border) !important; color: var(--text) !important; border-radius: 8px !important; }
[data-testid="stDateInput"] > div > div { background: var(--white) !important; border-color: var(--border) !important; border-radius: 8px !important; }
[data-testid="stDateInput"] input { color: var(--text) !important; }
[data-testid="stDateInput"] input::placeholder { color: var(--muted) !important; }
.main .stCheckbox label p, .main .stCheckbox label span { color: var(--text) !important; }
.main .stNumberInput button { color: var(--muted) !important; border-color: var(--border) !important; }
.main .stNumberInput button:hover { color: var(--text) !important; }


/* ════════════════════════════════════════════════════════════════════
   PROGRESS / METRICS / EXPANDERS / ALERTS / FORMS / TABLES
   ════════════════════════════════════════════════════════════════════ */

[data-testid="stProgressBarValue"] {
    background: linear-gradient(90deg, var(--coral) 0%, var(--teal) 100%) !important;
    border-radius: 999px !important;
}
[data-testid="stExpander"] {
    background: var(--white) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    margin-bottom: 0.5rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stExpander"] summary { font-weight: 600 !important; color: var(--text) !important; padding: 0.875rem 1rem !important; }
[data-testid="stExpander"] summary:hover { color: var(--coral) !important; }
[data-testid="stMetric"] {
    background: var(--white) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
[data-testid="stMetricLabel"] > div { font-size: 0.68rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.09em !important; color: var(--muted) !important; }
[data-testid="stMetricValue"] > div { font-size: 1.6rem !important; font-weight: 700 !important; color: var(--text) !important; }
[data-testid="stAlert"] { border-radius: 10px !important; border-left-width: 4px !important; }
[data-testid="stAlert"] p { color: var(--text) !important; }
[data-testid="stForm"] { border: 1px solid var(--border) !important; border-radius: 12px !important; background: #FAFBFF !important; padding: 1.25rem !important; }
[data-testid="stStatus"] { border-radius: 10px !important; border: 1px solid var(--border) !important; }
[data-testid="stStatus"] p { color: var(--text) !important; }
hr { border-color: var(--border) !important; margin: 1.25rem 0 !important; }

/* ════════════════════════════════════════════════════════════════════
   RIGHT PANE BACKGROUND
   ════════════════════════════════════════════════════════════════════ */

div[data-testid="column"]:nth-of-type(2):has(.agent-col-marker),
div[data-testid="stColumn"]:has(.agent-col-marker) {
    background: linear-gradient(175deg, #0F1E38 0%, #101B35 100%) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 14px !important;
    padding: 1rem 1.25rem 0.75rem !important;
    position: sticky !important;
    top: 6rem !important;
    height: calc(100vh - 7rem) !important;
    max-height: calc(100vh - 7rem) !important;
    overflow: hidden !important;
    align-self: flex-start !important;
    z-index: 100 !important;
    display: flex !important;
    flex-direction: column !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) > div {
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 0% !important;
    height: 100% !important;
    min-height: 0 !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) > div > div[data-testid="stVerticalBlock"] {
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 0% !important;
    min-height: 0 !important;
    height: 100% !important;
    overflow: hidden !important;
}

/* Chat History Container - ensures messages start from bottom */
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stVerticalBlock"] > div:has(#chat-history-start) + div {
    flex: 1 1 0% !important;
    overflow-y: auto !important;
    min-height: 0 !important;
    padding: 0.5rem 0.8rem !important;
    margin-bottom: 0.5rem !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important; /* Start from top of the flex container, but spacer pushes to bottom */
}

/* Spacer to push messages to bottom - flex-grow:1 makes it fill empty space */
div[data-testid="stColumn"]:has(.agent-col-marker) .chat-spacer {
    flex: 1 1 auto !important;
    height: auto !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stForm"]) {
    flex-shrink: 0 !important;
    margin-top: auto !important;
    padding-top: 0.5rem !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] {
    flex-shrink: 0 !important;
    margin-top: auto !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stVerticalBlock"] > div:has(#chat-history-start) + div::-webkit-scrollbar {
    width: 6px;
}
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stVerticalBlock"] > div:has(#chat-history-start) + div::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.15);
    border-radius: 10px;
}
div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stVerticalBlock"] > div:has(#chat-history-start) + div::-webkit-scrollbar-track {
    background: transparent;
}

/* ════════════════════════════════════════════════════════════════════
   CHAT MESSAGES — Gemini/ChatGPT Style
   ════════════════════════════════════════════════════════════════════ */

[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    margin-bottom: 1.25rem !important;
    padding: 0 !important;
    animation: chatEntrance 0.4s cubic-bezier(0.2, 0.8, 0.2, 1) forwards !important;
}

/* Message Bubble Styles */
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
    padding: 0.75rem 1.1rem !important;
    border-radius: 18px !important;
    font-size: 0.9rem !important;
    line-height: 1.5 !important;
    max-width: 90% !important;
    width: fit-content !important;
}

/* User Message - Right Aligned, Coral BG */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"] {
    margin-left: 0.6rem !important;
    margin-right: 0 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] {
    background: var(--coral) !important;
    color: #FFFFFF !important;
    border-bottom-right-radius: 4px !important;
    margin-left: auto !important;
    box-shadow: 0 4px 12px rgba(255, 107, 53, 0.2) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p {
    color: #FFFFFF !important;
}

/* Assistant Message - Left Aligned, Subtle Dark BG */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stMarkdownContainer"] {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #E2E8F0 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-bottom-left-radius: 4px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}



/* ════════════════════════════════════════════════════════════════════
   INLINE CHAT FORM — Pill Style
   ════════════════════════════════════════════════════════════════════ */

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] {
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 28px !important; /* Pill shape */
    padding: 0.4rem 0.6rem 0.4rem 1.2rem !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
    margin-bottom: 0.5rem !important;
    backdrop-filter: blur(12px) !important;
    transition: border-color 0.3s ease;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"]:focus-within {
    border-color: rgba(255, 107, 53, 0.5) !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] [data-testid="stTextInput"] {
    padding: 0 !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] [data-testid="stTextInput"] div[data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] [data-testid="stTextInput"] input {
    color: #FFFFFF !important;
    font-size: 0.95rem !important;
    padding: 0.5rem 0 !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] {
    margin: 0 !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button {
    background: var(--coral) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 50% !important; /* Circular send button */
    width: 36px !important;
    height: 36px !important;
    min-width: 36px !important;
    padding: 0 !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    box-shadow: 0 2px 8px rgba(255, 107, 53, 0.4) !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button p {
    font-size: 1.2rem !important;
    line-height: 1 !important;
    margin-top: -2px !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button:hover {
    background: var(--coral-dark) !important;
    transform: scale(1.05) !important;
}

/* ════════════════════════════════════════════════════════════════════
   EXPANDER OVERRIDES for Agent Column (Fix Visibility)
   ════════════════════════════════════════════════════════════════════ */
div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] summary {
    color: #F1F5F9 !important;
    padding: 0.6rem 0.75rem !important;
    font-size: 0.8rem !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] summary:hover {
    color: #FF6B35 !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
    padding: 0.75rem !important;
}

div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] p,
div[data-testid="stColumn"]:has(.agent-col-marker) [data-testid="stExpander"] span {
    color: #CBD5E1 !important;
}

/* ════════════════════════════════════════════════════════════════════
   MAIN CANVAS REFINEMENTS
   ════════════════════════════════════════════════════════════════════ */

/* Sticky Page Header fix - Zero bottom margin prevents transparent scroll leak */
div[data-testid="stVerticalBlock"] > div:has(.page-header-marker) {
    position: sticky !important;
    top: 2.875rem !important; /* offset for Streamlit header */
    z-index: 999 !important;
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

/* Ensure intermediate containers don't introduce transparent gaps */
div:has(> .page-header-marker) {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

/* Compact Scheduled Tasks Table */
div[data-testid="stHorizontalBlock"]:has(.task-row-marker) {
    margin-bottom: -1rem !important;
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────

PRIORITY_MAP = {"low": 1, "medium": 3, "high": 5}


def _priority_badge(p: int) -> str:
    if p >= 5: return "High"
    if p >= 3: return "Medium"
    return "Low"


def _priority_badge_html(p: int) -> str:
    if p >= 5:
        return (
            '<span style="display:inline-block;background:#FEE2E2;color:#7F1D1D;'
            'padding:3px 10px;border-radius:999px;font-size:0.68rem;font-weight:800;'
            'letter-spacing:0.04em;border:1px solid #FCA5A5;">HIGH</span>'
        )
    if p >= 3:
        return (
            '<span style="display:inline-block;background:#FEF3C7;color:#78350F;'
            'padding:3px 10px;border-radius:999px;font-size:0.68rem;font-weight:800;'
            'letter-spacing:0.04em;border:1px solid #FDE68A;">MED</span>'
        )
    return (
        '<span style="display:inline-block;background:#D1FAE5;color:#14532D;'
        'padding:3px 10px;border-radius:999px;font-size:0.68rem;font-weight:800;'
        'letter-spacing:0.04em;border:1px solid #6EE7B7;">LOW</span>'
    )


def _section_header(icon: str, title: str, subtitle: str = "") -> str:
    """For MAIN area (white/slate bg) — dark text."""
    sub = (f'<div style="color:#64748B;font-size:0.72rem;margin-top:2px;">{subtitle}</div>'
           if subtitle else "")
    return (
        f'<div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.75rem;">'
        f'<div style="width:26px;height:26px;background:rgba(255,107,53,0.10);'
        f'border:1px solid rgba(255,107,53,0.25);border-radius:7px;flex-shrink:0;'
        f'display:flex;align-items:center;justify-content:center;font-size:0.82rem;">'
        f'{icon}</div>'
        f'<div><div style="font-weight:700;color:#0F172A;font-size:0.88rem;">{title}</div>{sub}</div>'
        f'</div>'
    )


def _sidebar_section(icon: str, title: str, subtitle: str = "") -> str:
    """For SIDEBAR (navy bg) — ALL text must be bright."""
    sub = (f'<div style="color:#94A3B8;font-size:0.72rem;margin-top:2px;">{subtitle}</div>'
           if subtitle else "")
    return (
        f'<div style="display:flex;align-items:center;gap:0.55rem;margin-bottom:0.75rem;">'
        f'<div style="width:26px;height:26px;background:rgba(255,107,53,0.14);'
        f'border:1px solid rgba(255,107,53,0.30);border-radius:7px;flex-shrink:0;'
        f'display:flex;align-items:center;justify-content:center;font-size:0.82rem;">'
        f'{icon}</div>'
        f'<div><div style="font-weight:700;color:#E2E8F0;font-size:0.88rem;">{title}</div>{sub}</div>'
        f'</div>'
    )


def _page_header(owner: Owner, total_due: int, total_mins: int) -> str:
    n = len(owner.pets)
    return (
        '<div class="page-header-marker" style="background:linear-gradient(135deg,#101B35 0%,#1A2E55 55%,#152B50 100%);'
        'border-radius:14px;padding:0.75rem 1.5rem;border:1px solid rgba(255,255,255,0.07);'
        'box-shadow:0 4px 24px rgba(0,0,0,0.28);'
        'overflow:hidden;">'
        '<div style="position:absolute;right:-0.5rem;top:50%;transform:translateY(-50%);'
        'font-size:8rem;opacity:0.04;pointer-events:none;">🐾</div>'
        '<div style="position:relative;z-index:1;display:flex;align-items:center;gap:1.25rem;">'
        '<div style="background:rgba(255,107,53,0.15);border:1px solid rgba(255,107,53,0.40);'
        'border-radius:12px;width:44px;height:44px;flex-shrink:0;'
        'display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🐾</div>'
        '<div>'
        '<h1 style="margin:0;color:#FFFFFF;font-size:1.55rem;font-weight:800;letter-spacing:-0.03em;">'
        'PawPal<span style="color:#FF6B35;">+</span></h1>'
        '<p style="margin:0.15rem 0 0;color:#94A3B8;font-size:0.78rem;">'
        'AI-powered scheduling\u00a0·\u00a0conflict detection\u00a0·\u00a0safety guardrail'
        '</p></div>'
        '<div style="margin-left:auto;display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;">'
        '<span style="background:rgba(46,196,182,0.15);border:1px solid rgba(46,196,182,0.40);'
        'color:#5EEAD4;font-size:0.68rem;font-weight:700;padding:3px 9px;border-radius:999px;">'
        'HAIKU-4.5 &amp; SONNET-4.6</span>'
        '<span style="background:rgba(255,107,53,0.15);border:1px solid rgba(255,107,53,0.40);'
        'color:#FB923C;font-size:0.68rem;font-weight:700;padding:3px 9px;border-radius:999px;">'
        'REACT AGENT</span>'
        f'<span style="background:rgba(255,255,255,0.09);border:1px solid rgba(255,255,255,0.18);'
        f'color:#CBD5E1;font-size:0.68rem;font-weight:600;padding:3px 9px;border-radius:999px;">'
        f'{n}\u00a0pet{"s" if n != 1 else ""}\u00a0·\u00a0{total_due}\u00a0due\u00a0·\u00a0{total_mins}\u00a0min'
        f'</span>'
        '</div></div></div>'
    )


# ── Gantt ─────────────────────────────────────────────────────────────────

_DAY_START_H = 6
_DAY_END_H   = 22
_DAY_RANGE_M = (_DAY_END_H - _DAY_START_H) * 60


def _gantt_axis() -> str:
    ticks = ""
    for h in range(_DAY_START_H, _DAY_END_H + 1):
        pct = (h - _DAY_START_H) / (_DAY_END_H - _DAY_START_H) * 100
        label_html = (
            f'<span style="font-size:0.58rem;color:#475569;font-family:\'DM Mono\',monospace;">'
            f'{h:02d}:00</span>' if h % 2 == 0 else ""
        )
        ticks += (
            f'<div style="position:absolute;left:{pct:.2f}%;'
            f'display:flex;flex-direction:column;align-items:center;gap:2px;">'
            f'<div style="width:1px;height:6px;background:#CBD5E1;"></div>{label_html}</div>'
        )
    ruler = '<div style="position:absolute;top:6px;left:0;right:0;height:1px;background:#E2E8F0;"></div>'
    return f'<div style="position:relative;height:24px;margin-bottom:6px;">{ruler}{ticks}</div>'


def _gantt_bar(task_name, start_str, duration: int, is_required: bool, is_skipped=False) -> str:
    lock  = "🔒 " if is_required else ""
    label = f"{lock}{task_name} ({duration}m)"

    if is_skipped:
        return (
            f'<div style="font-size:0.78rem;color:#475569;padding:5px 10px;'
            f'background:#F1F5F9;border-radius:6px;border:1px dashed #CBD5E1;margin-bottom:4px;">'
            f'⏭\u00a0{label}\u00a0— skipped (budget full)</div>'
        )
    if start_str is None:
        return (
            f'<div style="font-size:0.78rem;color:#475569;padding:5px 10px;'
            f'background:#F8FAFC;border-radius:6px;border:1px dashed #CBD5E1;'
            f'margin-bottom:4px;display:flex;align-items:center;gap:6px;">'
            f'<span>⏱</span><span>{label}</span>'
            f'<span style="margin-left:auto;font-size:0.65rem;color:#94A3B8;">'
            f'Assign a start time to show on Gantt</span></div>'
        )

    try:
        t = datetime.strptime(start_str, "%H:%M")
        start_min = t.hour * 60 + t.minute
    except ValueError:
        start_min = _DAY_START_H * 60

    end_min   = start_min + duration
    left_pct  = max(0.0, (start_min - _DAY_START_H * 60) / _DAY_RANGE_M * 100)
    width_pct = min(max(0.5, duration / _DAY_RANGE_M * 100), 100.0 - left_pct)
    if left_pct >= 100:
        left_pct, width_pct = 99.0, 0.5

    color   = "#D64E18" if is_required else "#178F85"
    end_str = f"{end_min // 60:02d}:{end_min % 60:02d}"

    return (
        f'<div style="position:relative;height:30px;background:#F8FAFC;'
        f'border-radius:6px;border:1px solid #E2E8F0;overflow:hidden;margin-bottom:5px;">'
        f'<div style="position:absolute;left:{left_pct:.2f}%;width:{width_pct:.2f}%;'
        f'height:100%;background:{color};border-radius:5px;'
        f'display:flex;align-items:center;padding:0 8px;box-sizing:border-box;overflow:hidden;">'
        f'<span style="color:#FFFFFF;font-size:0.72rem;font-weight:700;white-space:nowrap;'
        f'overflow:hidden;text-overflow:ellipsis;text-shadow:0 1px 3px rgba(0,0,0,0.4);">'
        f'{label}</span></div>'
        f'<span style="position:absolute;right:6px;top:50%;transform:translateY(-50%);'
        f'font-size:0.62rem;color:#64748B;font-family:\'DM Mono\',monospace;pointer-events:none;">'
        f'{start_str}–{end_str}</span></div>'
    )


# ── Session state ─────────────────────────────────────────────────────────

def _init_session():
    if "owner_data" not in st.session_state:
        if os.path.exists("data/data.json"):
            st.session_state.owner_data = Owner.load_from_json("data/data.json")
        else:
            p = Pet(name="Mochi", species="dog", age=3)
            o = Owner(name="Jordan", available_time_mins=60)
            o.pets.append(p)
            st.session_state.owner_data = o

    defaults = {
        "owner_name":       st.session_state.owner_data.name,
        "available_time":   st.session_state.owner_data.available_time_mins,
        "schedule_result":  None,
        "pending_complete": None,
        "last_completed":   None,
        "chat_history":     [],
        "guardrail_result": None,
        "guardrail_banner": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = PawPalOrchestrator(
            owner=st.session_state.owner_data,
            client=anthropic.Anthropic(),
        )
    else:
        st.session_state.orchestrator.owner = st.session_state.owner_data
        st.session_state.orchestrator.tools.owner = st.session_state.owner_data


_init_session()

if st.session_state.pending_complete is not None:
    _pname, _tidx = st.session_state.pending_complete
    for _pet in st.session_state.owner_data.pets:
        if _pet.name == _pname and _tidx < len(_pet.tasks):
            _t = _pet.tasks[_tidx]
            if not _t.is_completed:
                _pet.complete_task(_t)
                st.session_state.last_completed = _t.name
            break
    st.session_state.pending_complete = None
    st.session_state.schedule_result  = None

orchestrator: PawPalOrchestrator = st.session_state.orchestrator
owner  = st.session_state.owner_data
today  = date.today()

total_due          = sum(1 for p in owner.pets for t in p.tasks if t.due_date <= today and not t.is_completed)
total_required_due = sum(1 for p in owner.pets for t in p.tasks if t.is_required and t.due_date <= today and not t.is_completed)
total_mins         = sum(t.duration for p in owner.pets for t in p.tasks if t.due_date <= today and not t.is_completed)


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="padding:0 0 1.25rem;border-bottom:1px solid rgba(255,255,255,0.09);margin-bottom:1.25rem;">'
        '<div style="display:flex;align-items:center;gap:0.75rem;">'
        '<div style="width:36px;height:36px;background:rgba(255,107,53,0.15);'
        'border:1px solid rgba(255,107,53,0.35);border-radius:9px;'
        'display:flex;align-items:center;justify-content:center;font-size:1.1rem;">🐾</div>'
        '<div>'
        '<div style="color:#F1F5F9;font-weight:700;font-size:0.95rem;">PawPal<span style="color:#FB923C;">+</span></div>'
        '<div style="color:#94A3B8;font-size:0.7rem;margin-top:1px;">Management Console</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )

    with st.expander("👤 Owner Settings", expanded=False):
        owner_name_val     = st.text_input("Owner name", key="owner_name")
        available_time_val = st.number_input("Available time (minutes)", min_value=0, max_value=480, key="available_time")
        st.session_state.owner_data.name                = owner_name_val
        st.session_state.owner_data.available_time_mins = int(available_time_val)
        if st.button("💾  Save Data", use_container_width=True, type="primary"):
            st.session_state.owner_data.save_to_json("data/data.json")
            st.success("Saved to data/data.json")

    with st.expander("🐕 Add a Pet", expanded=False):
        with st.form("add_pet_form", clear_on_submit=True):
            new_pet_name = st.text_input("Name")
            c1, c2 = st.columns(2)
            with c1:
                new_pet_species = st.selectbox("Species", ["dog","cat","rabbit","fish","bird","other"])
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

    with st.expander("📋 Add a Task", expanded=False):
        owner_sb = st.session_state.owner_data
        if not owner_sb.pets:
            st.markdown('<p style="color:#94A3B8;font-size:0.8rem;">Add a pet first.</p>', unsafe_allow_html=True)
        else:
            with st.form("add_task_form", clear_on_submit=False):
                selected_pet   = st.selectbox("Assign to pet", [p.name for p in owner_sb.pets])
                task_title     = st.text_input("Task title", value="Morning walk")
                ta, tb = st.columns(2)
                with ta: duration       = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
                with tb: priority_label = st.selectbox("Priority", ["low","medium","high"], index=2)
                tc, td = st.columns(2)
                with tc: frequency   = st.selectbox("Frequency", ["one-off","daily","weekly"])
                with td: is_required = st.checkbox("Required")
                # Fix truncation by making these full width instead of columns
                start_time_raw = st.text_input("Start time (HH:MM)", value="", placeholder="09:00")
                due_date_val   = st.date_input("Due date", value=date.today())

                if st.form_submit_button("Add Task", use_container_width=True):
                    if task_title.strip():
                        st_val = start_time_raw.strip() or None
                        if st_val and not re.match(r"^\d{2}:\d{2}$", st_val):
                            st.error("Start time must be HH:MM (e.g. 09:00).")
                        else:
                            new_task = Task(
                                name=task_title.strip(), duration=int(duration),
                                priority=PRIORITY_MAP[priority_label], is_required=is_required,
                                frequency=frequency, start_time=st_val, due_date=due_date_val,
                            )
                            next(p for p in owner_sb.pets if p.name == selected_pet).tasks.append(new_task)
                            st.session_state.schedule_result = None
                            st.success(f"'{new_task.name}' added!")
                    else:
                        st.warning("Please enter a task title.")

    st.divider()
    st.markdown(
        '<div style="background:rgba(46,196,182,0.09);border:1px solid rgba(46,196,182,0.30);'
        'border-radius:10px;padding:0.75rem 1rem;">'
        '<div style="display:flex;align-items:center;gap:0.5rem;">'
        '<span style="font-size:1.1rem;">🛡️</span>'
        '<div>'
        '<div style="color:#5EEAD4;font-weight:700;font-size:0.8rem;">Safety Guardrail: Active</div>'
        '<div style="color:#94A3B8;font-size:0.68rem;margin-top:1px;">Required tasks are always protected</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )

    with st.expander("🗂  Guardrail Audit Log", expanded=False):
        log_path = "data/guardrail_violations.jsonl"
        if os.path.exists(log_path):
            records = []
            with open(log_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip(): records.append(json.loads(line.strip()))
            if records:
                html = '<table style="width:100%;font-size:0.75rem;color:#E2E8F0;border-collapse:collapse;">'
                html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.1);"><th style="text-align:left;padding:4px;">Timestamp</th><th style="text-align:left;padding:4px;">Event</th></tr>'
                for r in records[-5:]:
                    ts = r.get("timestamp", "")[:19].replace("T", " ")
                    ev = r.get("event", "Violation")
                    html += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td style="padding:4px;">{ts}</td><td style="padding:4px;">{ev}</td></tr>'
                html += '</table>'
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#94A3B8;font-size:0.8rem;">No violations yet.</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#94A3B8;font-size:0.8rem;">Log not found.</p>', unsafe_allow_html=True)

    with st.expander("📊  Performance & Cache Report", expanded=False):
        if orchestrator.run_metrics.total_calls > 0:
            st.markdown(orchestrator.run_metrics.format_summary())
        else:
            st.markdown('<p style="color:#94A3B8;font-size:0.8rem;">No optimizations run yet.</p>', unsafe_allow_html=True)

    with st.expander("ℹ️  About"):
        st.markdown(
            '<p style="color:#94A3B8;font-size:0.75rem;line-height:1.6;margin:0;">'
            'PawPal+ uses a ReAct agent loop with Claude to resolve schedule conflicts '
            'and enforce safety guardrails on every optimization run.</p>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════
st.markdown(_page_header(owner, total_due, total_mins), unsafe_allow_html=True)
# This spacer creates the visual gap below the header but scrolls away naturally
st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

if st.session_state.guardrail_banner:
    gr  = st.session_state.guardrail_result
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
# DUAL-PANE
# ══════════════════════════════════════════════════════════════════════════
canvas_col, agent_col = st.columns([0.65, 0.35], gap="large")


# ══════════════════════════════════════════════════════════════════════════
# MIDDLE PANE
# ══════════════════════════════════════════════════════════════════════════
with canvas_col:

    # KPI bar
    st.markdown(
        '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;'
        'padding:1rem 1.25rem;box-shadow:0 1px 4px rgba(0,0,0,0.04);margin-bottom:1rem;">'
        '<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.1em;color:#475569;margin-bottom:0.6rem;">📊 Daily Overview</div>',
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pets", len(owner.pets))
    m2.metric("Due / Overdue", total_due)
    m3.metric("Required", total_required_due)
    m4.metric("Budget (min)", owner.available_time_mins)
    st.markdown("</div>", unsafe_allow_html=True)

    # Agentic card (dark)
    st.markdown(
        '<div style="background:linear-gradient(135deg,#101B35 0%,#1B2E54 100%);'
        'border-radius:12px;padding:0.9rem 1.25rem 0.75rem;margin-bottom:0.75rem;'
        'border:1px solid rgba(255,107,53,0.22);box-shadow:0 4px 20px rgba(0,0,0,0.20);">'
        '<div style="display:flex;align-items:center;gap:0.75rem;">'
        '<div style="width:34px;height:34px;background:rgba(255,107,53,0.16);'
        'border:1px solid rgba(255,107,53,0.35);border-radius:9px;flex-shrink:0;'
        'display:flex;align-items:center;justify-content:center;font-size:1rem;">🤖</div>'
        '<div>'
        '<div style="color:#F1F5F9;font-weight:700;font-size:0.9rem;">Agentic Optimization</div>'
        '<div style="color:#B0BAC9;font-size:0.72rem;margin-top:2px;">'
        'ReAct loop · Conflict resolution · Safety guardrail check'
        '</div></div></div></div>',
        unsafe_allow_html=True,
    )

    if st.button("🤖  Optimize Schedule & Resolve Conflicts", type="primary", use_container_width=True):
        orchestrator.clear_trace()
        st.session_state.guardrail_result = None
        st.session_state.guardrail_banner = False
        with st.status("Agent is thinking…", expanded=True) as status:
            resolve_result   = orchestrator.resolve_schedule_conflicts()
            guardrail_result = orchestrator.run_final_guardrail(resolve_result["schedule"])
            st.session_state.guardrail_result = guardrail_result
            if guardrail_result.guardrail_triggered:
                st.session_state.guardrail_banner = True
                st.toast(f"🛡️ Guardrail restored {guardrail_result.violation_count} required task(s)!", icon="🛡️")
            if resolve_result["conflicts_resolved"]:
                lbl = "✓ Done — all conflicts resolved!"
            elif resolve_result["escalated"]:
                lbl = f"Done — escalated after {resolve_result['steps_taken']} step(s)."
            else:
                lbl = f"Done — {resolve_result['steps_taken']} step(s) taken."
            status.update(label=lbl, state="complete", expanded=False)
        st.session_state.schedule_result = Scheduler(owner).generate_schedule()

    st.divider()

    st.markdown(
        '<div style="font-weight:700;color:#0F172A;font-size:0.95rem;margin-bottom:0.75rem;">'
        '🗓️  Gantt Daily Plan</div>',
        unsafe_allow_html=True,
    )

    if st.button("▶  Generate Schedule", type="secondary", use_container_width=True):
        if not owner.pets or not owner.get_all_tasks():
            st.warning("Add at least one pet with at least one task first.")
        else:
            with st.spinner("Building your schedule…"):
                st.session_state.schedule_result = Scheduler(owner).generate_schedule()

    if st.session_state.last_completed:
        st.success(f"✓ '{st.session_state.last_completed}' marked complete!")
        st.session_state.last_completed = None

    result = st.session_state.schedule_result

    if result is not None:
        if "Time Deficit" in result.reasoning:
            st.error(f"⚠️  {result.reasoning}")
        else:
            st.info(result.reasoning)

        budget    = owner.available_time_mins
        time_used = result.total_time_used
        if budget > 0:
            over = f" (+{time_used - budget} over)" if time_used > budget else ""
            st.progress(min(time_used / budget, 1.0), text=f"Time used: {time_used} / {budget} min{over}")
        else:
            st.progress(0.0, text="No time budget set.")

        for ta, tb in Scheduler(owner).detect_conflicts(result.scheduled_tasks):
            st.warning(f"**Overlap:** _{ta.name}_ ends at **{ta.end_time}** but _{tb.name}_ starts at **{tb.start_time}**.")

        if result.scheduled_tasks:
            if not any(t.start_time for t in result.scheduled_tasks):
                st.markdown(
                    '<div style="background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;'
                    'padding:0.6rem 1rem;font-size:0.8rem;color:#92400E;margin:0.5rem 0;">'
                    '💡 <strong>Tip:</strong> Assign start times (HH:MM) to see tasks on the Gantt timeline.'
                    '</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div style="margin:0.75rem 0 0.25rem;font-size:0.65rem;font-weight:700;'
                'text-transform:uppercase;letter-spacing:0.1em;color:#475569;">'
                'Timeline (06:00 – 22:00)</div>',
                unsafe_allow_html=True,
            )
            gantt_html  = '<div style="padding:0.25rem 0 0.5rem;">' + _gantt_axis()
            task_pet_map = {id(t): p for p in owner.pets for t in p.tasks}
            for task in result.scheduled_tasks:
                gantt_html += _gantt_bar(task.name, task.start_time, task.duration, task.is_required)
            gantt_html += "</div>"
            st.markdown(gantt_html, unsafe_allow_html=True)

            st.markdown(
                '<div style="margin:0.75rem 0 0.25rem;font-size:0.65rem;font-weight:700;'
                'text-transform:uppercase;letter-spacing:0.1em;color:#475569;">Scheduled Tasks</div>',
                unsafe_allow_html=True,
            )
            _hs = "font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#64748B;"
            h1, h2, h3, h4 = st.columns([3.5, 1.2, 1.5, 2])
            h1.markdown(f'<span style="{_hs}">Task</span>',     unsafe_allow_html=True)
            h2.markdown(f'<span style="{_hs}">Min</span>',      unsafe_allow_html=True)
            h3.markdown(f'<span style="{_hs}">Priority</span>', unsafe_allow_html=True)
            h4.markdown("")

            for i, task in enumerate(result.scheduled_tasks):
                pet = task_pet_map.get(id(task))
                c1, c2, c3, c4 = st.columns([3.5, 1.2, 1.5, 2])
                c1.markdown(
                    f'<div class="task-row-marker" style="display:none;"></div>'
                    f'<span style="font-weight:600;color:#0F172A;font-size:0.85rem;">'
                    f'{task.name}{"&nbsp;🔒" if task.is_required else ""}</span>',
                    unsafe_allow_html=True,
                )
                c2.markdown(f'<span style="color:#475569;font-size:0.85rem;">{task.duration}</span>', unsafe_allow_html=True)
                c3.markdown(_priority_badge_html(task.priority), unsafe_allow_html=True)
                if pet is not None:
                    idx = next((j for j, t in enumerate(pet.tasks) if t is task), None)
                    if idx is not None and c4.button("✓ Done", key=f"complete_{i}", use_container_width=True):
                        st.session_state.pending_complete = (pet.name, idx)
                        st.rerun()

        if result.skipped_tasks:
            with st.expander(f"⏭  {len(result.skipped_tasks)} task(s) skipped — over budget"):
                html = '<div style="padding:4px 0;">'
                for t in result.skipped_tasks:
                    html += _gantt_bar(t.name, t.start_time, t.duration, t.is_required, is_skipped=True)
                html += "</div>"
                st.markdown(html, unsafe_allow_html=True)

    else:
        st.markdown(
            '<div style="background:#F8FAFC;border:1px dashed #CBD5E1;border-radius:12px;'
            'padding:2.5rem;text-align:center;margin-top:1rem;">'
            '<div style="font-size:2.5rem;margin-bottom:0.75rem;">📅</div>'
            '<div style="font-weight:600;color:#334155;margin-bottom:0.35rem;font-size:0.95rem;">No schedule yet</div>'
            '<div style="font-size:0.8rem;color:#475569;">'
            'Click <strong>▶ Generate Schedule</strong> or describe a task to the AI Agent →'
            '</div></div>',
            unsafe_allow_html=True,
        )

    if orchestrator.agent_trace:
        with st.expander("🛠️  Agent Reasoning & ReAct Log"):
            for ts in orchestrator.agent_trace:
                dot = "#FF6B35" if ts.action_tool != "(end_turn)" else "#94A3B8"
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;gap:0.65rem;margin-bottom:0.5rem;">'
                    f'<div style="min-width:22px;height:22px;background:{dot};color:#fff;border-radius:50%;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-size:0.68rem;font-weight:700;flex-shrink:0;margin-top:2px;">{ts.step}</div>'
                    f'<code style="background:#F1F5F9;color:#0F172A;border-radius:5px;'
                    f'padding:2px 8px;font-size:0.76rem;font-weight:600;border:1px solid #E2E8F0;">'
                    f'{ts.action_tool}</code></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Thought:** {ts.thought}")
                if ts.action_input: st.json(ts.action_input)
                st.markdown("**Observation:**")
                st.json(ts.observation)
                st.divider()


# ══════════════════════════════════════════════════════════════════════════
# RIGHT PANE — Agent Chat  (dark #0F1E38 → #101B35)
# ══════════════════════════════════════════════════════════════════════════
with agent_col:

    # Marker used by CSS to target this column
    st.markdown('<div class="agent-col-marker" id="agent-col-marker" style="display:none;"></div>', unsafe_allow_html=True)

    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        # FIX [2]: white title, #94A3B8 subtitle — both readable on dark
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.6rem;'
            'padding-bottom:0.75rem;border-bottom:1px solid rgba(255,255,255,0.10);margin-bottom:0.75rem;">'
            '<div style="width:30px;height:30px;background:rgba(255,107,53,0.18);'
            'border:1px solid rgba(255,107,53,0.38);border-radius:8px;'
            'display:flex;align-items:center;justify-content:center;font-size:0.95rem;">💬</div>'
            '<div>'
            '<div style="color:#FFFFFF;font-weight:700;font-size:0.88rem;">AI Agent</div>'
            '<div style="color:#94A3B8;font-size:0.68rem;margin-top:1px;">NL task entry · HAIKU-4.5</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
    with hdr_r:
        # FIX [3]: Destructive actions get lowest prominence
        if st.button("🗑️", key="clear_chat", help="Clear chat history", use_container_width=True):
            st.session_state.chat_history = []

    # FIX [4]: instruction paragraph bright on dark
    st.markdown(
        '<p style="color:#94A3B8;font-size:0.76rem;line-height:1.55;margin:0 0 0.75rem;">'
        'Describe a task in plain English. The agent parses it and adds it automatically.'
        '</p>',
        unsafe_allow_html=True,
    )

    st.markdown('<div id="chat-history-start" style="display:none;"></div>', unsafe_allow_html=True)
    chat_box = st.container()
    with chat_box:
        # Flexible spacer to push messages to the bottom
        st.markdown('<div class="chat-spacer" style="height:0px;"></div>', unsafe_allow_html=True)
        if not st.session_state.chat_history:
            # FIX [5][12]: empty state — responsive height
            st.markdown(
                '<div style="height:100%;min-height:150px;display:flex;flex-direction:column;'
                'align-items:center;justify-content:center;padding:2rem 1rem;text-align:center;">'
                '<div style="font-size:2.5rem;margin-bottom:0.75rem;opacity:0.22;">💬</div>'
                '<div style="color:#CBD5E1;font-size:0.83rem;line-height:1.7;font-weight:500;">'
                'No messages yet.<br>'
                '<span style="color:#94A3B8;font-size:0.78rem;font-weight:400;">'
                'Type a task description below to get started.'
                '</span></div></div>',
                unsafe_allow_html=True,
            )
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg.get("trace"):
                        with st.expander("🛠 View Agent Reasoning"):
                            for step in msg["trace"]:
                                st.markdown(
                                    f'<div style="margin-bottom:0.75rem;">'
                                    f'<code style="background:rgba(255,107,53,0.15);color:#FF6B35;'
                                    f'padding:2px 8px;border-radius:5px;font-size:0.72rem;'
                                    f'font-weight:700;border:1px solid rgba(255,107,53,0.3);">'
                                    f'{step["action_tool"]}</code>'
                                    f'<div style="margin-top:0.4rem;color:#E2E8F0;font-size:0.8rem;">'
                                    f'<strong>Thought:</strong> {step["thought"]}</div>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                                if step.get("observation"):
                                    st.markdown('<div style="font-size:0.72rem;color:#94A3B8;margin-bottom:0.2rem;">Observation:</div>', unsafe_allow_html=True)
                                    st.json(step["observation"])
                                st.divider()
            # This hidden marker helps the JS find the bottom of the chat
            st.markdown('<div id="chat-history-end" style="height:1px; margin-top:-1px; opacity:0;"></div>', unsafe_allow_html=True)

    # ── Inline chat input form inside right pane ─────────────────────────────
    with st.form("chat_input_form", clear_on_submit=True, border=False):
        f_col1, f_col2 = st.columns([6, 1])
        with f_col1:
            prompt = st.text_input("Task", label_visibility="collapsed", placeholder="Describe a task in plain English...")
        with f_col2:
            submitted = st.form_submit_button("↑", type="primary", use_container_width=True)

    if submitted and prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        trace_before = len(orchestrator.agent_trace)
        parse_result = orchestrator.parse_nl_task(prompt)
        new_trace    = [t.as_dict() for t in orchestrator.agent_trace[trace_before:]]
        del orchestrator.agent_trace[trace_before:]
        
        if parse_result.success:
            task_name     = (parse_result.task_dict or {}).get("name", "task")
            response_text = (
                f"Done! Task **{task_name}** has been added. "
                "Hit **▶ Generate Schedule** to see it in the Gantt view, or "
                "**🤖 Optimize Schedule** to auto-resolve any conflicts."
            )
            st.session_state.schedule_result = None
            st.toast("Task added! Click 💾 Save Data in the sidebar to persist it.", icon="💾")
        elif parse_result.needs_clarification:
            response_text = f"Could you clarify: {parse_result.clarification_question}"
        else:
            response_text = f"I wasn't able to process that — {parse_result.error}"
            
        st.session_state.chat_history.append({
            "role": "assistant", "content": response_text, "trace": new_trace,
        })
        st.rerun()

    # ── Auto-scroll to bottom script ─────────────────────────────────────────
    components.html(
        """
        <script>
        const scrollChat = () => {
            const doc = window.parent.document;
            const endMarker = doc.getElementById('chat-history-end');
            if (endMarker) {
                // Scroll the marker into view within its container
                endMarker.scrollIntoView({ behavior: 'smooth', block: 'end' });
            } else {
                // Fallback: try to find the container via the start marker
                const startMarker = doc.getElementById('chat-history-start');
                if (startMarker) {
                    const scrollContainer = startMarker.parentElement.nextElementSibling;
                    if (scrollContainer) {
                        scrollContainer.scrollTop = scrollContainer.scrollHeight;
                    }
                }
            }
        };
        // Run frequently at first, then less often
        [10, 100, 300, 800, 1500].forEach(ms => setTimeout(scrollChat, ms));
        </script>
        """,
        height=0,
    )
