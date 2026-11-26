# agent-persistent

You tell a chat assistant a goal on Monday; by Friday nobody remembers it exists.

Chat agents are amnesiac between sessions and passive between messages. You have to re-explain the goal, re-paste the context, and be the one who remembers to check back. The work that matters — watching something, following up, assembling a brief every day — does not fit in a single chat window.

`agent-persistent` is a persistent, proactive, goal-oriented agent that runs **locally in one command**. It keeps a durable goal list in SQLite, wakes itself up on a schedule, works the list one session at a time through a LangGraph state graph, follows markdown playbooks, consolidates its memory in a nightly "dreaming" pass, and writes every notification to a local outbox. Nothing is ever sent anywhere.

## What it does

- **Persistent goals** — text, playbook, status (`active` / `blocked` / `done`), `next_check_at`, step progress, and a history of work sessions, all in SQLite. State survives restarts mid-goal (the demo proves it).
- **Heartbeat + self-scheduling** — `tick` finds due goals, works **one** session on the most due goal, then the agent sets its own next check-in with a recorded reason and interval (deterministic fallback rules on the stub model).
- **Playbooks** — markdown files in `playbooks/` with named steps, parsed deterministically. Ships `watch-and-summarize` and `daily-brief`.
- **Memory + dreaming** — durable per-user memory notes with provenance. `dream` merges duplicates and supersedes contradicted facts (newer wins, old marked superseded, **never deleted**), returning a before/after report.
- **Watch mode** — watches a local JSONL channel file; files a notification only when a message mentions a tracked goal or a deadline. Noise gets silence.
- **Notification outbox** — notifications live in a SQLite outbox table, listed by CLI. Hard invariant: no network sends, no email, no Slack.

## Architecture

LangGraph state graph (`PersistentAgent` in `src/agent_persistent/agent.py`):

```
load_goal -> execute_step -> record_outcome -> schedule_next -> END
```

- `load_goal` — loads the goal and its playbook state from SQLite.
- `execute_step` — runs the current playbook step using typed tools (`read_source`, `save_memory`, `create_notification`, `set_next_checkin` in `tools.py`).
- `record_outcome` — advances the step, appends to the goal's session history, handles blocked/done.
- `schedule_next` — sets `next_check_at` + reason for the next heartbeat.

The system prompt lives in its own module, `src/agent_persistent/prompts.py` — never inline in agent code. The model layer is LiteLLM (`LLM_MODEL` env, default `gemini/gemini-3.5-flash-lite`); a deterministic `StubModel` powers the offline demo and tests with no API key.

### Mapping to the enterprise original

Inspired by the ideas in LangChain's "Persistent Agent" (personal memory, background goals, playbooks, dreaming, watch mode), re-implemented locally with no enterprise stack:

| Enterprise original | This repo |
|---|---|
| Slack | Local CLI + local JSONL channel file |
| LangSmith tools / tracing | Local typed tools + SQLite history |
| Managed (MDA) hosting | Your machine, one command |
| Nightly dreaming pass | Same idea, local: `dream` command |
| Cloud scheduler | Heartbeat `tick` / `run` + injectable virtual clock |

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python scripts/demo.py        # or: agent-persistent demo
pytest -q
```

Live test (needs a real model key for `LLM_MODEL`):

```bash
LLM_MODEL=gemini/gemini-3.5-flash-lite python scripts/live_test.py
```

CLI:

```bash
agent-persistent --db agent.db add-goal "produce a daily brief" --playbook daily-brief --source ./inbox
agent-persistent --db agent.db tick
agent-persistent --db agent.db run 5
agent-persistent --db agent.db goals
agent-persistent --db agent.db notifications
agent-persistent --db agent.db memory
agent-persistent --db agent.db dream
agent-persistent --db agent.db brief
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | `gemini/gemini-3.5-flash-lite` | LiteLLM model for the live path |
| `AGENT_DB` | `agent_persistent.db` | SQLite database path |
| `AGENT_STUB` | unset | `1` forces the stub model in helpers that use `get_model()` |

## Why LangGraph?

A persistent, resumable state graph fits an agent that must survive restarts mid-goal: each session is a graph run over durable state loaded from SQLite, the current step is explicit, and outcomes/scheduling are separate nodes you can inspect and test — not a hidden loop inside a chat transcript.

## Honest limits

- Local, single-user only. No multi-user, no cloud, no Slack/email — by design.
- Watch mode's speak-up layer is rules + goal matching (keywords, deadline words, dates), not deep understanding.
- Self-scheduling intervals are heuristic (1 hour while in progress, 1 day when blocked/done-ish), recorded with a reason — not learned.
- The stub demo is scripted/deterministic: it proves the mechanics (persistence, scheduling, playbooks, dreaming, watch, outbox), not model intelligence. The live path is `scripts/live_test.py`.
- Playbooks are intentionally small and step execution is code-driven per step name; arbitrary new playbooks need matching step handlers.

## Layout

```
playbooks/  scripts/  src/agent_persistent/  tests/  fixtures/
```
