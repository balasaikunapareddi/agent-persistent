#!/usr/bin/env python3
"""Real-model live test: exercises LiteLLM model on a seeded goal.
Asserts on STATE, not exact wording. Requires a real API key for LLM_MODEL (default gemini/gemini-3.5-flash-lite).
Usage: LLM_MODEL=gemini/gemini-3.5-flash-lite python scripts/live_test.py
Scheduling uses a VirtualClock (advanced between ticks) so the goal's own
+1h next-check-ins become due without real sleeps; model calls are real.
"""
import sys, os, tempfile, time
sys.path.insert(0, "src")
from pathlib import Path
from agent_persistent.store import Store
from agent_persistent.agent import PersistentAgent
from agent_persistent.llm import LiteLLMModel
from agent_persistent.clock import VirtualClock
def main():
    tmp=Path(tempfile.mkdtemp()); db=tmp/"live.db"; inbox=tmp/"inbox"; inbox.mkdir()
    (inbox/"note.txt").write_text("Live test note: the persistent agent should brief this.")
    store=Store(db); clock=VirtualClock(start=time.time()); model=LiteLLMModel()
    print(f"Live model: {model.model}")
    # Direct model sanity (real call)
    out=model.summarize("The persistent agent keeps goals across restarts and schedules its own check-ins.")
    assert out and len(out)>5, "model returned empty summary"
    print(f"Model summary (truncated): {out[:160]}")
    agent=PersistentAgent(store, model=model, clock=clock, inbox_dir=str(inbox))
    g=store.add_goal("produce a daily brief from inbox notes", "daily-brief", source=str(inbox), next_check_at=clock.now()-1)
    store.add_memory("Live test started", key="live", provenance="live_test")
    for _ in range(5):
        r=agent.tick(); print("tick:", r)
        if store.get_goal(g.id).status=="done": break
        clock.advance(3600)
    goal=store.get_goal(g.id)
    assert goal.status=="done", f"goal not done, status={goal.status} history={goal.history}"
    assert goal.next_check_at>clock.now(), "next check-in not in future"
    assert store.list_briefs(), "no brief produced"
    assert store.list_notifications(), "no notification/outbox entry produced"
    assert store.list_memories(active_only=True), "no memory write"
    print("LIVE TEST PASS: goal done, brief + notification + memory present, next_check_at in future")
    return 0
if __name__=="__main__": raise SystemExit(main())
