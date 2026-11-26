from __future__ import annotations
import argparse, os, json
from pathlib import Path
from .store import Store
from .agent import PersistentAgent
from .llm import StubModel
from .clock import VirtualClock, SystemClock
from .dreaming import dream
def _store(args): return Store(args.db)
def main(argv=None):
    p=argparse.ArgumentParser(prog="agent-persistent"); p.add_argument("--db", default=os.environ.get("AGENT_DB","agent_persistent.db"))
    sub=p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    a=sub.add_parser("add-goal"); a.add_argument("text"); a.add_argument("--playbook", default="daily-brief"); a.add_argument("--source", default="")
    sub.add_parser("tick"); r=sub.add_parser("run"); r.add_argument("ticks", type=int, nargs="?", default=3)
    sub.add_parser("goals"); sub.add_parser("notifications"); sub.add_parser("memory"); sub.add_parser("dream"); sub.add_parser("brief")
    args=p.parse_args(argv)
    if args.cmd=="demo":
        from .demo import run_demo; return run_demo()
    store=_store(args); clock=SystemClock(); agent=PersistentAgent(store, model=StubModel(), clock=clock)
    if args.cmd=="add-goal":
        g=store.add_goal(args.text, args.playbook, source=args.source, next_check_at=clock.now()); print(f"Added goal {g.id}: {g.text} [{g.playbook}]")
    elif args.cmd=="tick": print(agent.tick())
    elif args.cmd=="run": print(agent.run(args.ticks))
    elif args.cmd=="goals":
        for g in store.list_goals(): print(f"{g.id}: {g.text} playbook={g.playbook} status={g.status} step={g.step_index} next_check_at={g.next_check_at}")
    elif args.cmd=="notifications":
        for n in store.list_notifications(): print(f"{n['id']}: {n['title']} - {n['body']}")
    elif args.cmd=="memory":
        for m in store.list_memories(active_only=True): print(f"{m['id']}: {m['content']} (key={m['key']}, provenance={m['provenance']})")
    elif args.cmd=="dream": print(dream(store))
    elif args.cmd=="brief":
        for b in store.list_briefs(): print(b["content"])
    return 0
if __name__=="__main__": raise SystemExit(main())
