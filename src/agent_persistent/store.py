from __future__ import annotations
import sqlite3, json, time
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class Goal:
    id:int; text:str; playbook:str; status:str; next_check_at:float; step_index:int=0
    step_progress:dict=field(default_factory=dict); history:list=field(default_factory=list)
    source:str=""; metadata:dict=field(default_factory=dict)

class Store:
    def __init__(self, db_path:str|Path):
        self.db_path=str(db_path); Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn=sqlite3.connect(self.db_path); self.conn.row_factory=sqlite3.Row
        self._init()
    def _init(self):
        c=self.conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, playbook TEXT, status TEXT, next_check_at REAL, step_index INTEGER, step_progress TEXT, history TEXT, source TEXT, metadata TEXT, created_at REAL, updated_at REAL);
        CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, key TEXT, provenance TEXT, created_at REAL, status TEXT DEFAULT 'active', superseded_by INTEGER);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, title TEXT, body TEXT, kind TEXT, created_at REAL);
        CREATE TABLE IF NOT EXISTS briefs(id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, content TEXT, created_at REAL);
        CREATE TABLE IF NOT EXISTS watch_seen(hash TEXT PRIMARY KEY, seen_at REAL);
        """); c.commit()
    def close(self): self.conn.close()
    # goals
    def add_goal(self, text, playbook, source="", next_check_at=0.0, metadata=None)->Goal:
        cur=self.conn.execute("INSERT INTO goals(text,playbook,status,next_check_at,step_index,step_progress,history,source,metadata,created_at,updated_at) VALUES(?,?,?,?,0,?,?,?,?,?,?)",(text,playbook,"active",next_check_at,"{}","[]",source,json.dumps(metadata or {}),next_check_at,next_check_at)); self.conn.commit(); return self.get_goal(cur.lastrowid)
    def get_goal(self, gid)->Goal|None:
        r=self.conn.execute("SELECT * FROM goals WHERE id=?",(gid,)).fetchone()
        return self._to_goal(r) if r else None
    def _to_goal(self,r):
        return Goal(id=r["id"],text=r["text"],playbook=r["playbook"],status=r["status"],next_check_at=r["next_check_at"],step_index=r["step_index"],step_progress=json.loads(r["step_progress"] or "{}"),history=json.loads(r["history"] or "[]"),source=r["source"] or "",metadata=json.loads(r["metadata"] or "{}"))
    def list_goals(self): return [self._to_goal(r) for r in self.conn.execute("SELECT * FROM goals ORDER BY id")]
    def due_goals(self, now):
        return [g for g in self.list_goals() if g.status=="active" and g.next_check_at<=now]
    def update_goal(self, g:Goal):
        self.conn.execute("UPDATE goals SET text=?,playbook=?,status=?,next_check_at=?,step_index=?,step_progress=?,history=?,source=?,metadata=?,updated_at=? WHERE id=?",(g.text,g.playbook,g.status,g.next_check_at,g.step_index,json.dumps(g.step_progress),json.dumps(g.history),g.source,json.dumps(g.metadata),time.time(),g.id)); self.conn.commit()
    # memory
    def add_memory(self, content, key="", provenance="user", created_at=None)->int:
        cur=self.conn.execute("INSERT INTO memories(content,key,provenance,created_at,status) VALUES(?,?,?,?, 'active')",(content,key,provenance,created_at if created_at is not None else time.time())); self.conn.commit(); return cur.lastrowid
    def list_memories(self, active_only=False):
        q="SELECT * FROM memories"+(" WHERE status='active'" if active_only else "")+" ORDER BY id"
        return [dict(r) for r in self.conn.execute(q)]
    def set_memory_status(self, mid, status, superseded_by=None):
        self.conn.execute("UPDATE memories SET status=?, superseded_by=? WHERE id=?",(status,superseded_by,mid)); self.conn.commit()
    # notifications / outbox - ONLY sink
    def add_notification(self, title, body, goal_id=None, kind="info", created_at=None)->int:
        cur=self.conn.execute("INSERT INTO notifications(goal_id,title,body,kind,created_at) VALUES(?,?,?,?,?)",(goal_id,title,body,kind,created_at if created_at is not None else time.time())); self.conn.commit(); return cur.lastrowid
    def list_notifications(self): return [dict(r) for r in self.conn.execute("SELECT * FROM notifications ORDER BY id")]
    def add_brief(self, goal_id, content, created_at=None)->int:
        cur=self.conn.execute("INSERT INTO briefs(goal_id,content,created_at) VALUES(?,?,?)",(goal_id,content,created_at if created_at is not None else time.time())); self.conn.commit(); return cur.lastrowid
    def list_briefs(self): return [dict(r) for r in self.conn.execute("SELECT * FROM briefs ORDER BY id")]
    # watch: durable seen-message hashes so re-ticks never re-evaluate/re-notify
    def has_watch_seen(self, h)->bool:
        return self.conn.execute("SELECT 1 FROM watch_seen WHERE hash=?",(h,)).fetchone() is not None
    def mark_watch_seen(self, h, seen_at=None):
        self.conn.execute("INSERT OR IGNORE INTO watch_seen(hash,seen_at) VALUES(?,?)",(h,seen_at if seen_at is not None else time.time())); self.conn.commit()
