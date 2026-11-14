"""A/B assignment for proposal strategies (signature extension X2).

Deterministic: the same job always gets the same arm (sha256 of experiment name + job id), so a resumed or
replayed run never switches strategy, and the split is reproducible in evaluations.
GIGBID_ARM (env) forces one arm: used by the evaluation to run every job under both strategies.
"""
import hashlib
import os

from agent.config import cfg


def assign_arm(job_id: str) -> str:
    e = cfg().get("experiment") or {}
    arms = e.get("arms") or ["evidence_first"]
    forced = os.getenv("GIGBID_ARM") or e.get("force_arm")
    if forced:
        if forced not in arms:
            raise ValueError(f"unknown arm {forced!r}; arms: {arms}")
        return forced
    if not e.get("enabled") or len(arms) < 2:
        return arms[0]
    u = int(hashlib.sha256(f"{e.get('name', 'exp')}:{job_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return arms[1] if u < float(e.get("split", 0.5)) else arms[0]
