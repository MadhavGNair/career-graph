# ADR 0008: Interrupts only at the top level

Status: accepted (2026-11-22)

## Context
Verified on langgraph 1.2.24: `interrupt()` inside Send branches works, producing one
interrupt per branch with distinct ids; resuming then needs a map of interrupt id -> value.

## Decision
Both pauses (`human_shortlist`, `human_review`) are top-level nodes that run after parallel
branches have joined. Subgraphs and branch nodes never interrupt.

## Consequences
One payload and one resume value per pause: simple CLI/UI and validation. The review can
loop (edits are re-verified in parallel branches, then the single review node pauses again).
