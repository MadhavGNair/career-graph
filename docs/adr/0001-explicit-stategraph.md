# ADR 0001: Explicit StateGraph instead of prebuilt agents

Status: accepted (2026-11-22)

## Context
LangGraph/LangChain offer prebuilt agents (`create_agent`, `create_react_agent`) that hide
the loop. CareerGraph's owner wants hands-on graph experience, and the workflow is mostly
known in advance: ingest, find, analyse, score, pause, draft, verify, pause, render.

## Decision
Build every graph explicitly with `StateGraph`: named nodes, explicit conditional edges,
Send fan-out, subgraphs. The one open-ended part (company research) is an explicit ReAct loop
(`plan_query -> ToolNode -> reflect_or_stop`) rather than a prebuilt agent.

## Comparison
| | Explicit StateGraph | Prebuilt agent |
|---|---|---|
| Control flow | visible in `graph.py`, diagram generated | inside the library |
| Limits (steps, tokens, domains) | nodes we own and test | via config/hooks, less direct |
| Human pauses | `interrupt()` exactly where we want | possible, less obvious |
| Lines of code | more | fewer |
| Upgrades | our code may need changes | library absorbs some changes |

## Consequences
More code and more tests, in exchange for readable, testable control flow and an honest
learning vehicle.
