from __future__ import annotations
def dream(store)->dict:
    """Deterministic consolidation: merge duplicates, supersede contradicted (same key, newer wins). Nothing deleted."""
    before=store.list_memories(active_only=True); before_count=len(before)
    total_before=len(store.list_memories())
    details=[]; merged=0; superseded=0
    # duplicates: normalized content
    seen={}
    for m in before:
        norm=" ".join(m["content"].lower().split())
        if norm in seen:
            store.set_memory_status(m["id"],"superseded",superseded_by=seen[norm]); merged+=1; details.append(f"merged duplicate memory {m['id']} into {seen[norm]}: {m['content']}")
        else: seen[norm]=m["id"]
    # contradictions: same non-empty key, different content -> newer (higher id / created_at) wins
    active=store.list_memories(active_only=True)
    by_key={}
    for m in active:
        if m["key"]: by_key.setdefault(m["key"],[]).append(m)
    for key, group in by_key.items():
        if len(group)>1:
            # sort by created_at then id, keep last
            group_sorted=sorted(group, key=lambda x:(x["created_at"], x["id"]))
            keeper=group_sorted[-1]
            for old in group_sorted[:-1]:
                if " ".join(old["content"].lower().split())!=" ".join(keeper["content"].lower().split()):
                    store.set_memory_status(old["id"],"superseded",superseded_by=keeper["id"]); superseded+=1; details.append(f"superseded memory {old['id']} ({old['content']}) by {keeper['id']} ({keeper['content']}) for key {key}")
    after=store.list_memories(active_only=True)
    return {"before_active":before_count,"after_active":len(after),"total_before":total_before,"total_after":len(store.list_memories()),"duplicates_merged":merged,"superseded":superseded,"details":details}
