"""Type alias for the runtime every node receives (services are the LangGraph context)."""

from __future__ import annotations

from langgraph.runtime import Runtime

from careergraph.service.wiring import Services

Ctx = Runtime[Services]
