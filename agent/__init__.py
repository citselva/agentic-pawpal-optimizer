"""agent — Agentic orchestration layer for PawPal+.

Public surface
--------------
PawPalTools
    Registry of the nine LLM-callable tool methods (Tools 1–9).
TOOL_SCHEMAS
    Anthropic-format tool definitions to pass to ``anthropic.messages.create``.
validate_required_tasks
    Guardrail utility (Tool 10) — called by the Orchestrator only, never by
    the LLM.
ApiCallRecord
    Per-call token-usage and latency record (populated by ``_call_api``).
RunMetrics
    Session-level aggregation of token usage, cache-hit rate, and latency.
"""

from agent.tools import TOOL_SCHEMAS, PawPalTools, validate_required_tasks
from agent.orchestrator import ApiCallRecord, RunMetrics

__all__ = [
    "PawPalTools",
    "TOOL_SCHEMAS",
    "validate_required_tasks",
    "ApiCallRecord",
    "RunMetrics",
]
