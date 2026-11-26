from __future__ import annotations
import json, re
from pathlib import Path
DEADLINE_WORDS=["deadline","due","tomorrow","urgent","by friday","by monday","expires","reminder"]
def evaluate_message(text:str, goals)->tuple[bool,str]:
    low=text.lower()
    for g in goals:
        # keywords from goal text (words >3 chars)
        words=[w.strip(".,") for w in g.text.lower().split() if len(w)>3]
        # also playbook name parts
        words+= [p for p in g.playbook.split("-") if len(p)>3]
        if any(w in low for w in words): return True, f"mentions tracked goal: {g.text}"
    if any(d in low for d in DEADLINE_WORDS): return True, "mentions a deadline"
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", low): return True, "mentions a date/deadline"
    return False, "no goal match or deadline"
def watch_channel(store, channel_path, goals, now=None)->dict:
    p=Path(channel_path); spoken=0; silent=0; results=[]
    if not p.exists(): return {"spoken":0,"silent":0,"results":[]}
    for line in p.read_text().splitlines():
        if not line.strip(): continue
        try: msg=json.loads(line); text=msg.get("text","") if isinstance(msg,dict) else str(msg)
        except Exception: text=line
        ok,reason=evaluate_message(text, goals)
        results.append({"text":text,"speak":ok,"reason":reason})
        if ok:
            store.add_notification("Watch: you can help", f"{text} ({reason})", kind="watch", created_at=now); spoken+=1
        else: silent+=1
    return {"spoken":spoken,"silent":silent,"results":results}
