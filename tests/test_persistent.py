import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from agent_persistent.store import Store
from agent_persistent.agent import PersistentAgent
from agent_persistent.llm import StubModel
from agent_persistent.clock import VirtualClock
from agent_persistent.playbooks import load_playbook
from agent_persistent.dreaming import dream
from agent_persistent.watch import watch_channel, evaluate_message
from agent_persistent.demo import run_demo

def make(tmp_path, inbox=None):
    store=Store(tmp_path/"a.db"); clock=VirtualClock(); agent=PersistentAgent(store, model=StubModel(), clock=clock, inbox_dir=str(inbox) if inbox else None); return store,clock,agent

def test_persistence_across_restart(tmp_path):
    store,clock,agent=make(tmp_path)
    g=store.add_goal("produce a daily brief from inbox notes","daily-brief",source="",next_check_at=clock.now())
    agent.tick(); mid=store.get_goal(g.id); assert mid.step_index>=1 and mid.status=="active"
    store.close(); store2=Store(tmp_path/"a.db"); g2=store2.get_goal(g.id); assert g2.step_index==mid.step_index and g2.text==g.text
    assert g2.status==mid.status and g2.next_check_at==mid.next_check_at
    assert g2.history==mid.history and g2.step_progress==mid.step_progress

def test_due_goal_selection(tmp_path):
    store,clock,agent=make(tmp_path)
    store.add_goal("future goal","daily-brief",next_check_at=clock.now()+10000)
    gdue=store.add_goal("due goal","daily-brief",next_check_at=clock.now()-10)
    r=agent.tick(); assert r["goal_id"]==gdue.id
    # most due first
    store2=Store(tmp_path/"b.db"); clock2=VirtualClock(); ag2=PersistentAgent(store2, model=StubModel(), clock=clock2)
    a=store2.add_goal("less due","daily-brief",next_check_at=clock2.now()-10)
    b=store2.add_goal("most due","daily-brief",next_check_at=clock2.now()-100)
    assert ag2.tick()["goal_id"]==b.id

def test_self_scheduling_sets_future_with_reason(tmp_path):
    store,clock,agent=make(tmp_path)
    g=store.add_goal("goal","daily-brief",next_check_at=clock.now())
    agent.tick(); upd=store.get_goal(g.id); assert upd.next_check_at>clock.now(); assert upd.step_progress.get("next_check_reason")

def test_playbook_parse_and_advance_and_completion(tmp_path):
    pb=load_playbook("daily-brief"); assert [s.name for s in pb.steps]==["collect_notes","assemble_brief","save_brief"]
    inbox=tmp_path/"inbox"; inbox.mkdir(); (inbox/"n.txt").write_text("hello brief world")
    store,clock,agent=make(tmp_path, inbox=inbox)
    g=store.add_goal("produce a daily brief","daily-brief",source=str(inbox),next_check_at=clock.now())
    for _ in range(4):
        clock.advance(3600); agent.tick()
    assert store.get_goal(g.id).status=="done"; assert store.list_briefs()

def test_watch_speak_and_silence(tmp_path):
    store,clock,agent=make(tmp_path)
    g=store.add_goal("produce a daily brief","daily-brief",next_check_at=clock.now())
    ok,_=evaluate_message("brief deadline tomorrow", store.list_goals()); assert ok
    ok2,_=evaluate_message("nice sunny lunch", store.list_goals()); assert not ok2
    ch=tmp_path/"ch.jsonl"; ch.write_text(json.dumps({"text":"help with brief deadline tomorrow"})+"\n"+json.dumps({"text":"random movie chatter"}))
    res=watch_channel(store, ch, store.list_goals(), now=clock.now()); assert res["spoken"]==1 and res["silent"]==1

def test_dream_dedupe_and_supersede(tmp_path):
    store,clock,agent=make(tmp_path)
    store.add_memory("User prefers tea",key="drink",created_at=1); store.add_memory("User prefers tea",key="drink",created_at=2)
    store.add_memory("User lives in Minneapolis",key="location",created_at=1); store.add_memory("User lives in Corcoran",key="location",created_at=5)
    rep=dream(store); assert rep["duplicates_merged"]>=1 and rep["superseded"]>=1
    active=[m["content"] for m in store.list_memories(active_only=True)]
    assert "User lives in Minneapolis" not in active and "User lives in Corcoran" in active
    # never resurrects: run dream again, still not active
    dream(store); active2=[m["content"] for m in store.list_memories(active_only=True)]; assert "User lives in Minneapolis" not in active2
    assert len(store.list_memories())==4  # nothing deleted

def test_outbox_only_invariant(tmp_path):
    # No send functions / network calls in codebase: notifications only via store table
    import agent_persistent.agent as ag, pathlib
    src=pathlib.Path(ag.__file__).parent
    combined=" ".join(p.read_text() for p in src.glob("*.py"))
    for forbidden in ["smtplib","sendmail","slack_sdk","requests","urllib","socket","http.client","subprocess","os.system","webhook"]:
        assert forbidden not in combined, f"outbox-only invariant violated: {forbidden} in src"
    store,clock,agent=make(tmp_path)
    g=store.add_goal("blocked-ish","daily-brief",next_check_at=clock.now()); agent.tick()
    # notifications, if any, are only rows in DB
    assert isinstance(store.list_notifications(), list)

def test_goal_blocked_missing_source(tmp_path):
    store,clock,agent=make(tmp_path)
    g=store.add_goal("watch missing","watch-and-summarize",source=str(tmp_path/"nope.txt"),next_check_at=clock.now())
    r=agent.tick(); upd=store.get_goal(g.id); assert upd.status=="blocked"; assert any(n["kind"]=="blocked" for n in store.list_notifications())

def test_watch_and_summarize_completes(tmp_path):
    srcf=tmp_path/"w.txt"; srcf.write_text("v1\n")
    store,clock,agent=make(tmp_path)
    g=store.add_goal("watch file","watch-and-summarize",source=str(srcf),next_check_at=clock.now())
    agent.tick(); srcf.write_text("v1\nv2 shipped\n")
    for _ in range(6):
        clock.advance(3600); agent.tick()
        if store.get_goal(g.id).status=="done": break
    assert store.get_goal(g.id).status=="done"

def test_watch_no_duplicate_notifications_on_rerun(tmp_path):
    store,clock,agent=make(tmp_path)
    store.add_goal("produce a daily brief","daily-brief",next_check_at=clock.now())
    ch=tmp_path/"ch.jsonl"; ch.write_text(json.dumps({"text":"help with brief deadline tomorrow"})+"\n"+json.dumps({"text":"random movie chatter"}))
    r1=watch_channel(store, ch, store.list_goals(), now=clock.now()); assert r1["spoken"]==1
    n1=len(store.list_notifications())
    r2=watch_channel(store, ch, store.list_goals(), now=clock.now())
    assert r2["spoken"]==0 and r2["skipped"]==2 and len(store.list_notifications())==n1

def test_watch_word_boundary_no_false_positives(tmp_path):
    store,clock,agent=make(tmp_path)
    store.add_goal("produce a daily brief","daily-brief",next_check_at=clock.now())
    ok,_=evaluate_message("briefly sunny afternoon", store.list_goals()); assert not ok
    ok2,_=evaluate_message("overdue library chat about movies", []); assert not ok2

def test_malformed_playbook_fails_loudly(tmp_path):
    import pytest
    from agent_persistent.playbooks import parse_playbook
    bad=tmp_path/"bad.md"; bad.write_text("# Something else\nno steps here\n")
    with pytest.raises(ValueError): parse_playbook(bad)
    # and a goal using it becomes blocked, never silently done
    pdir=tmp_path/"pbs"; pdir.mkdir(); (pdir/"bad.md").write_text(bad.read_text())
    store=Store(tmp_path/"x.db"); clock=VirtualClock(); ag=PersistentAgent(store, model=StubModel(), clock=clock, playbooks_dir=str(pdir))
    g=store.add_goal("do bad thing","bad",next_check_at=clock.now()); ag.tick()
    assert store.get_goal(g.id).status=="blocked"

def test_blocked_goal_does_not_wedge_other_goals(tmp_path):
    store,clock,agent=make(tmp_path)
    gb=store.add_goal("watch missing","watch-and-summarize",source=str(tmp_path/"nope.txt"),next_check_at=clock.now()-100)
    g2=store.add_goal("produce a daily brief","daily-brief",next_check_at=clock.now())
    agent.tick(); assert store.get_goal(gb.id).status=="blocked"
    r=agent.tick(); assert r is not None and r["goal_id"]==g2.id

def test_sql_injection_in_goal_text_is_inert(tmp_path):
    store,clock,agent=make(tmp_path)
    evil="x'); DROP TABLE goals;--"
    g=store.add_goal(evil,"daily-brief",next_check_at=clock.now())
    assert store.get_goal(g.id).text==evil and len(store.list_goals())==1

def test_demo_passes():
    assert run_demo(verbose=False)==0
