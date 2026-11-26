from __future__ import annotations
from typing import TypedDict, Any
from pathlib import Path
import hashlib, json
from langgraph.graph import StateGraph, END
from .store import Store
from .playbooks import load_playbook
from .llm import StubModel
from .tools import read_source, set_next_checkin, create_notification
from .prompts import SYSTEM_PROMPT

class AgentState(TypedDict, total=False):
    goal_id:int; step_name:str; outcome:str; context:dict

class PersistentAgent:
    """Persistent, proactive, goal-oriented agent. System prompt lives in prompts.py."""
    system_prompt = SYSTEM_PROMPT
    def __init__(self, store:Store, model=None, clock=None, playbooks_dir=None, inbox_dir=None):
        self.store=store; self.model=model or StubModel(); self.clock=clock
        self.playbooks_dir=playbooks_dir; self.inbox_dir=inbox_dir
        self.graph=self._build_graph()
    def _now(self):
        return self.clock.now() if self.clock else __import__("time").time()
    def _build_graph(self):
        g=StateGraph(AgentState)
        g.add_node("load_goal", self._node_load)
        g.add_node("execute_step", self._node_execute)
        g.add_node("record_outcome", self._node_record)
        g.add_node("schedule_next", self._node_schedule)
        g.set_entry_point("load_goal")
        g.add_edge("load_goal","execute_step"); g.add_edge("execute_step","record_outcome"); g.add_edge("record_outcome","schedule_next"); g.add_edge("schedule_next",END)
        return g.compile()
    # nodes
    def _node_load(self, state):
        goal=self.store.get_goal(state["goal_id"]); state["context"]={"goal_text":goal.text if goal else ""}; return state
    def _node_execute(self, state):
        goal=self.store.get_goal(state["goal_id"])
        if not goal: state["outcome"]="goal missing"; return state
        try: pb=load_playbook(goal.playbook, self.playbooks_dir)
        except Exception as e:
            goal.status="blocked"; goal.history.append({"outcome":f"blocked: playbook missing {e}","at":self._now()}); self.store.update_goal(goal); state["outcome"]="blocked: playbook missing"; return state
        if goal.step_index>=len(pb.steps):
            goal.status="done"; self.store.update_goal(goal); state["outcome"]="already done"; return state
        step=pb.steps[goal.step_index]; state["step_name"]=step.name
        outcome=self._execute_step(goal, step.name, pb)
        state["outcome"]=outcome; self.store.update_goal(goal); return state
    def _execute_step(self, goal, step_name, pb)->str:
        now=self._now()
        if goal.playbook=="watch-and-summarize":
            if step_name=="check_source":
                src=goal.source or goal.metadata.get("source","")
                r=read_source(src) if src else {"exists":False,"content":"","hash":""}
                if not r["exists"]:
                    goal.status="blocked"; create_notification(self.store,"Goal blocked: source missing",f"Goal {goal.id} source not found: {src}",goal_id=goal.id,kind="blocked",created_at=now); return "blocked: source missing"
                prev=goal.step_progress.get("last_hash")
                goal.step_progress["last_hash"]=r["hash"]; goal.step_progress["last_content"]=r["content"]
                if prev is None:
                    goal.step_progress["baseline"]=True; return "baseline recorded"
                if prev==r["hash"]:
                    return "no change detected"
                goal.step_progress["changed"]=True; goal.step_progress["prev_content"]=goal.step_progress.get("prev_content","")
                return "change detected"
            if step_name=="summarize_change":
                # if no change, still summarize current (demo changes before this step)
                old=goal.step_progress.get("prev_content","")
                # prev_content stored incorrectly? Use snapshot: we stored last_content as new, need old snapshot
                # We keep snapshot in check: actually store previous content before overwrite - handled via 'snapshot_content'
                old=goal.step_progress.get("snapshot_content", old)
                new=goal.step_progress.get("last_content","")
                # Re-read source to get latest
                src=goal.source or goal.metadata.get("source","")
                r=read_source(src) if src else {"exists":True,"content":new,"hash":""}
                if r["exists"]: new=r["content"]
                summary=self.model.summarize_change(old, new) if hasattr(self.model,"summarize_change") else self.model.summarize(new)
                goal.step_progress["summary"]=summary; return f"summarized: {summary}"
            if step_name=="notify_user":
                summary=goal.step_progress.get("summary","change detected")
                create_notification(self.store,"Watch summary",summary,goal_id=goal.id,kind="watch-summary",created_at=now); return "notified via outbox"
            if step_name=="complete":
                goal.status="done"; return "completed"
        if goal.playbook=="daily-brief":
            if step_name=="collect_notes":
                notes=[]
                inbox=goal.source or goal.metadata.get("inbox") or self.inbox_dir
                if inbox:
                    p=Path(inbox)
                    if p.is_dir():
                        for f in sorted(p.iterdir()):
                            if f.is_file(): notes.append(f.read_text(errors="ignore"))
                    elif p.is_file(): notes.append(p.read_text(errors="ignore"))
                goal.step_progress["notes"]=notes; return f"collected {len(notes)} notes"
            if step_name=="assemble_brief":
                notes=goal.step_progress.get("notes",[])
                brief=self.model.assemble_brief(notes) if hasattr(self.model,"assemble_brief") else self.model.summarize(" ".join(notes))
                goal.step_progress["brief"]=brief; return "brief assembled"
            if step_name=="save_brief":
                brief=goal.step_progress.get("brief","Daily Brief: (empty)")
                self.store.add_brief(goal.id, brief, created_at=now)
                create_notification(self.store,"Daily brief ready",brief,goal_id=goal.id,kind="brief",created_at=now)
                goal.status="done"; return "brief saved"
        # generic fallback
        return f"executed {step_name}"
    def _node_record(self, state):
        goal=self.store.get_goal(state["goal_id"])
        if not goal: return state
        outcome=state.get("outcome","")
        # snapshot handling for watch: before advancing check_source, preserve old content
        # Actually snapshot is set in tick wrapper below; here just record
        if outcome.startswith("blocked"):
            goal.history.append({"step":state.get("step_name",""),"outcome":outcome,"at":self._now()}); self.store.update_goal(goal); return state
        if goal.status!="done":
            # advance step unless no-change on check_source (stay on same step to re-check later)
            if outcome=="no change detected":
                pass
            elif outcome=="baseline recorded":
                # stay? In demo we want progress: baseline then next tick should re-check, so do NOT advance yet
                # But to allow completion after change, keep step_index at check_source until change detected
                pass
            elif outcome=="change detected":
                # preserve snapshot for summarize: snapshot_content already should be old content; ensure it
                goal.step_index+=1
            else:
                goal.step_index+=1
        goal.history.append({"step":state.get("step_name",""),"outcome":outcome,"at":self._now()})
        self.store.update_goal(goal); return state
    def _node_schedule(self, state):
        goal=self.store.get_goal(state["goal_id"])
        if not goal: return state
        if goal.status=="done":
            goal.next_check_at=self._now()+86400*365; goal.step_progress["next_check_reason"]="goal done, no further check-in"; self.store.update_goal(goal); return state
        if goal.status=="blocked":
            set_next_checkin(goal, self._now(), 86400, "blocked: retry in 1 day when source may exist"); self.store.update_goal(goal); return state
        outcome=state.get("outcome","")
        if outcome in ("baseline recorded","no change detected"):
            set_next_checkin(goal, self._now(), 3600, "watching for changes: recheck in 1 hour")
        elif "collected" in outcome:
            set_next_checkin(goal, self._now(), 3600, "brief in progress: continue in 1 hour")
        else:
            set_next_checkin(goal, self._now(), 3600, "work in progress: continue next session in 1 hour")
        self.store.update_goal(goal); return state
    # public API
    def tick(self)->dict|None:
        now=self._now(); due=self.store.due_goals(now)
        if not due: return None
        due_sorted=sorted(due, key=lambda g:g.next_check_at)
        goal=due_sorted[0]
        # snapshot previous content before check_source overwrites
        if goal.playbook=="watch-and-summarize" and goal.step_index==0:
            prev_content=goal.step_progress.get("last_content","")
            goal.step_progress["snapshot_content"]=prev_content; self.store.update_goal(goal)
        result=self.graph.invoke({"goal_id":goal.id,"context":{}})
        updated=self.store.get_goal(goal.id)
        return {"goal_id":goal.id,"outcome":result.get("outcome",""),"step":result.get("step_name",""),"status":updated.status if updated else "","next_check_at":updated.next_check_at if updated else None}
    def run(self, ticks:int)->list:
        out=[]
        for _ in range(ticks):
            r=self.tick()
            if r: out.append(r)
        return out
