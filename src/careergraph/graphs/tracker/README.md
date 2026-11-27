# graphs/tracker/

## Purpose
The second graph: track applications after CareerGraph marked them "ready", with validated
status transitions, and turn an "interview" status into interview prep plus a mock interview.

## How it works
<!-- graph:tracker:start -->
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	update_status(update_status)
	interview_prep(interview_prep)
	ask_question(ask_question)
	score_answer(score_answer)
	wrap_up(wrap_up)
	__end__([<p>__end__</p>]):::last
	__start__ --> update_status;
	ask_question --> score_answer;
	interview_prep -. &nbsp;ask&nbsp; .-> ask_question;
	interview_prep -. &nbsp;done&nbsp; .-> wrap_up;
	score_answer -. &nbsp;ask&nbsp; .-> ask_question;
	score_answer -. &nbsp;done&nbsp; .-> wrap_up;
	update_status -. &nbsp;interview&nbsp; .-> interview_prep;
	update_status -. &nbsp;done&nbsp; .-> wrap_up;
	wrap_up --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
<!-- graph:tracker:end -->

`interview_prep` subgraph:

<!-- graph:interview_prep:start -->
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	prep_research(prep_research)
	derive_questions(derive_questions)
	build_stories(build_stories)
	__end__([<p>__end__</p>]):::last
	__start__ --> prep_research;
	derive_questions --> build_stories;
	prep_research --> derive_questions;
	build_stories --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
<!-- graph:interview_prep:end -->

- `update_status` validates the transition (`domain/status.py`: saved, ready, applied,
  screening, interview, offer, rejected, withdrawn) and records an event.
- The router `on_status` sends "interview" to `interview_prep`; everything else ends.
- `interview_prep` runs the subgraph: `prep_research` **reuses the `research_company`
  subgraph** from `job_search`, `derive_questions` builds likely questions from the stored
  `JobAnalysis` (must-have skills, seniority, behavioral, company), `build_stories` writes STAR
  stories that cite your evidence ids (stories citing unknown ids are dropped).
- `ask_question` calls `interrupt()` once per turn; `score_answer` scores your answer against a
  rubric (structure, relevance, specificity, conciseness, 1-5 each); the loop continues up to
  `MOCK_INTERVIEW_TURNS` or until you answer `/stop`; `wrap_up` reports averages and your
  weakest dimension.

## Key files
`graph.py`, `state.py`, `subgraph.py`, `nodes/` (one file per node),
`../../documents/interview.py` (question derivation).

## LangGraph concepts used and why
A second, independent `StateGraph` sharing the same checkpointer and Store; a router on a state
value; **subgraph reuse across graphs**; an interrupt **per loop iteration** (each answer is a
`Command(resume=answer)`), all at the top level.

## Configuration
`MOCK_INTERVIEW_TURNS`, `ENABLE_COMPANY_RESEARCH` (prep research), `CHEAP_MODEL`.

## How to run and test
```bash
careergraph tracker set <job_id> applied
careergraph tracker set <job_id> interview        # prints the first question
careergraph interview answer <thread> "my answer" # repeat; "/stop" to finish
```
Or use the Tracker page. Tests: `uv run pytest tests/test_tracker.py`.

## Design decisions and trade-offs
Questions are derived deterministically (cheap, explainable); only stories and scoring use the
cheap model. In demo mode scoring is a heuristic (STAR cue words, overlap with the question,
numbers, length): a plumbing check, not a judgement of your answer.

## Extending and gotchas
Interview prep needs a stored analysis of the posting and a cached profile (both exist for
applications created by `job_search`).
