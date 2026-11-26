from __future__ import annotations
from typing import TypedDict
import hashlib
from pathlib import Path
# Typed tool definitions (OpenAI-style schemas, used by the live model layer)
TOOL_DEFINITIONS=[
 {"type":"function","function":{"name":"read_source","description":"Read a local file or return missing","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
 {"type":"function","function":{"name":"save_memory","description":"Save a fact/preference to durable memory","parameters":{"type":"object","properties":{"content":{"type":"string"},"key":{"type":"string"},"provenance":{"type":"string"}},"required":["content"]}}},
 {"type":"function","function":{"name":"create_notification","description":"Write a notification to the local outbox only","parameters":{"type":"object","properties":{"title":{"type":"string"},"body":{"type":"string"}},"required":["title","body"]}}},
 {"type":"function","function":{"name":"set_next_checkin","description":"Set the next check-in time with a reason","parameters":{"type":"object","properties":{"interval_seconds":{"type":"number"},"reason":{"type":"string"}},"required":["interval_seconds","reason"]}}},
]
class ReadResult(TypedDict): exists:bool; content:str; hash:str
def read_source(path:str)->ReadResult:
    p=Path(path)
    if not p.exists(): return {"exists":False,"content":"","hash":""}
    c=p.read_text(errors="ignore"); return {"exists":True,"content":c,"hash":hashlib.sha256(c.encode()).hexdigest()}
def save_memory(store, content:str, key:str="", provenance:str="agent")->int: return store.add_memory(content,key=key,provenance=provenance)
def create_notification(store, title:str, body:str, goal_id=None, kind="info", created_at=None)->int: return store.add_notification(title,body,goal_id=goal_id,kind=kind,created_at=created_at)
def set_next_checkin(goal, now:float, interval_seconds:float, reason:str)->None:
    goal.next_check_at=float(now)+float(interval_seconds); goal.step_progress["next_check_reason"]=reason; goal.step_progress["next_check_interval"]=float(interval_seconds)
