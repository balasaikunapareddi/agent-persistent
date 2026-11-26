from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
@dataclass
class PlaybookStep: name:str; description:str
@dataclass
class Playbook: name:str; steps:list[PlaybookStep]
def default_playbooks_dir()->Path: return Path(__file__).resolve().parents[2]/"playbooks"
def parse_playbook(path)->Playbook:
    text=Path(path).read_text(); name=""; steps=[]
    for line in text.splitlines():
        s=line.strip()
        if s.startswith("# Playbook:"): name=s.split(":",1)[1].strip()
        elif s.startswith("## Step"):
            # format: ## Step 1: check_source - description
            rest=s[len("## Step"):].strip()
            # drop leading number:
            if ":" in rest: rest=rest.split(":",1)[1].strip()
            if " - " in rest: n,d=rest.split(" - ",1)
            else: n,d=rest,""
            steps.append(PlaybookStep(name=n.strip(), description=d.strip()))
    if not name: name=Path(path).stem
    return Playbook(name=name, steps=steps)
def load_playbook(name, playbooks_dir=None)->Playbook:
    d=Path(playbooks_dir) if playbooks_dir else default_playbooks_dir()
    p=d/f"{name}.md"
    if not p.exists(): raise FileNotFoundError(f"playbook not found: {p}")
    return parse_playbook(p)
