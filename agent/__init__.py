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
"""

from agent.tools import TOOL_SCHEMAS, PawPalTools, validate_required_tasks

__all__ = ["PawPalTools", "TOOL_SCHEMAS", "validate_required_tasks"]
