from __future__ import annotations
import os
class StubModel:
    """Deterministic offline model: no API key, no network."""
    name="stub"
    def complete(self, prompt:str)->str:
        return f"Stub completion: {prompt[:120]}"
    def summarize(self, text:str)->str:
        t=" ".join(text.split())
        return f"Summary: {t[:280]}" if t else "Summary: (empty)"
    def summarize_change(self, old:str, new:str)->str:
        old_lines=set(old.splitlines()); new_lines=[l for l in new.splitlines() if l not in old_lines]
        added="; ".join(new_lines) if new_lines else "content changed"
        return f"Changed: {added}"
    def assemble_brief(self, notes:list[str])->str:
        lines=["Daily Brief:"]
        for n in notes: lines.append(f"- {' '.join(n.split())[:200]}")
        return "\n".join(lines) if len(lines)>1 else "Daily Brief: no notes found."
class LiteLLMModel:
    name="litellm"
    def __init__(self, model:str|None=None):
        self.model=model or os.environ.get("LLM_MODEL","gemini/gemini-3.5-flash-lite")
    def complete(self, prompt:str)->str:
        import litellm
        r=litellm.completion(model=self.model, messages=[{"role":"user","content":prompt}])
        return r.choices[0].message.content or ""
    def summarize(self, text:str)->str: return self.complete(f"Summarize concisely: {text}")
    def summarize_change(self, old:str, new:str)->str: return self.complete(f"Old:\n{old}\nNew:\n{new}\nSummarize what changed:")
    def assemble_brief(self, notes:list[str])->str: return self.complete("Assemble a daily brief from these notes:\n"+"\n".join(notes))
def get_model(model=None):
    if model is not None: return model
    if os.environ.get("AGENT_STUB","")=="1": return StubModel()
    # Default for live path is LiteLLM; tests/demo pass StubModel explicitly
    return LiteLLMModel()
