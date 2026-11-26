from __future__ import annotations
import tempfile, json
from pathlib import Path
from .store import Store
from .agent import PersistentAgent
from .llm import StubModel
from .clock import VirtualClock
from .dreaming import dream
from .watch import watch_channel

def run_demo(verbose=True)->int:
    checks=[]
    def check(name, cond):
        checks.append((name,bool(cond)))
        if verbose: print(f"{'PASS' if cond else 'FAIL'}: {name}")
    tmp=Path(tempfile.mkdtemp(prefix="agent-persistent-demo-"))
    db=tmp/"agent.db"; src=tmp/"watched.txt"; inbox=tmp/"inbox"; inbox.mkdir()
    src.write_text("Version 1\nInitial release notes.\n")
    (inbox/"note1.txt").write_text("Standup: finish the persistent agent design.")
    (inbox/"note2.txt").write_text("Reminder: review goals for the week.")
    clock=VirtualClock(start=1700000000.0); store=Store(db); model=StubModel()
    agent=PersistentAgent(store, model=model, clock=clock, inbox_dir=str(inbox))
    g1=store.add_goal("watch the release notes file for changes and summarize", "watch-and-summarize", source=str(src), next_check_at=clock.now())
    g2=store.add_goal("produce a daily brief from inbox notes", "daily-brief", source=str(inbox), next_check_at=clock.now())
    # seed memories for dream
    store.add_memory("User prefers tea in the morning", key="drink", provenance="demo", created_at=clock.now())
    store.add_memory("User prefers tea in the morning", key="drink", provenance="demo", created_at=clock.now()+1)
    store.add_memory("User lives in Minneapolis", key="location", provenance="demo", created_at=clock.now())
    store.add_memory("User lives in Corcoran", key="location", provenance="demo", created_at=clock.now()+10)
    # tick 1: most due (g1 first) baseline
    r=agent.tick(); check("tick works a due goal", r is not None and r["goal_id"]==g1.id)
    check("baseline recorded, goal still active", store.get_goal(g1.id).status=="active")
    # change fixture
    src.write_text("Version 1\nInitial release notes.\nVersion 2: persistent agent shipped.\n")
    clock.advance_days(1)
    # need g1 due: its next_check was +1h, so due. But g2 also due earlier? g2 next= start, so g2 is most due. Tick will pick g2 first.
    # Work through ticks until g1 completes or 12 ticks
    outcomes=[]
    for i in range(15):
        clock.advance(3600)
        r=agent.tick()
        if r: outcomes.append(r)
        if store.get_goal(g1.id).status=="done" and store.get_goal(g2.id).status=="done": break
    check("goal 1 watch-and-summarize completes after change", store.get_goal(g1.id).status=="done")
    notifs=store.list_notifications()
    check("goal 1 produced a watch summary notification", any(n["kind"]=="watch-summary" for n in notifs))
    check("summary mentions the change", any("persistent agent shipped" in n["body"] for n in notifs))
    check("goal 2 daily-brief completes", store.get_goal(g2.id).status=="done")
    check("goal 2 produced briefs", len(store.list_briefs())>=1)
    check("brief mentions inbox notes", any("persistent agent" in b["content"] or "Standup" in b["content"] for b in store.list_briefs()))
    # watch mode: 3 messages, speak on 1
    channel=tmp/"channel.jsonl"
    channel.write_text("\n".join([json.dumps({"text":"Can you help with the daily brief deadline tomorrow?"}), json.dumps({"text":"Lunch was nice today, sunny weather"}), json.dumps({"text":"Random chatter about movies and music"})]))
    before_notif=len(store.list_notifications())
    wres=watch_channel(store, channel, store.list_goals(), now=clock.now())
    check("watch mode speaks up on 1 message", wres["spoken"]==1)
    check("watch mode silent on 2 messages", wres["silent"]==2)
    check("watch mode filed exactly 1 notification", len(store.list_notifications())==before_notif+1)
    # dream
    before=len(store.list_memories(active_only=True))
    report=dream(store)
    after=len(store.list_memories(active_only=True))
    if verbose: print(f"DREAM REPORT: before_active={report['before_active']} after_active={report['after_active']} duplicates_merged={report['duplicates_merged']} superseded={report['superseded']} details={report['details']}")
    check("dream merges duplicates", report["duplicates_merged"]>=1)
    check("dream supersedes contradicted fact", report["superseded"]>=1)
    check("dream before/after counts shrink", after<before and report["after_active"]==after)
    active_texts=[m["content"] for m in store.list_memories(active_only=True)]
    check("superseded location not in active memory", "User lives in Minneapolis" not in active_texts and "User lives in Corcoran" in active_texts)
    check("no memory deleted (total count unchanged by dream)", report["total_before"]==report["total_after"])
    # restart segment
    g3=store.add_goal("produce a daily brief from inbox notes after restart", "daily-brief", source=str(inbox), next_check_at=clock.now())
    clock.advance(10); agent.tick()  # one session, mid-flight (not done: needs 3 steps)
    mid=store.get_goal(g3.id); check("mid-flight goal is not done before restart", mid.status=="active" and mid.step_index>=1)
    store.close()
    # fresh agent + store on same DB = restart
    store2=Store(db); agent2=PersistentAgent(store2, model=model, clock=clock, inbox_dir=str(inbox))
    resumed=store2.get_goal(g3.id); check("state survives restart (step progress preserved)", resumed is not None and resumed.step_index==mid.step_index)
    for i in range(6):
        clock.advance(3600); agent2.tick()
        if store2.get_goal(g3.id).status=="done": break
    check("mid-flight goal resumes and finishes after restart", store2.get_goal(g3.id).status=="done")
    check("outbox is the only notification sink (all notifications in DB)", len(store2.list_notifications())>=3)
    failed=[n for n,c in checks if not c]
    if verbose: print(f"DEMO RESULT: {len(checks)-len(failed)}/{len(checks)} checks passed")
    store2.close()
    return 0 if not failed else 1
if __name__=="__main__": raise SystemExit(run_demo())
