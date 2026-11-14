"""The human-readable policy pack and the rules the Compliance Guard enforces must not drift apart."""
import re
from pathlib import Path

from agent.config import cfg

POLICY = Path("data/policy_pack/marketplace_policy.md").read_text(encoding="utf-8")


def documented_ids() -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", POLICY, re.M))


def test_every_enforced_rule_is_documented():
    c = cfg()
    enforced = {r["id"] for r in c["compliance"]["rules"]} | {r["flag"] for r in c["risk"]["rules"]} | {"below_floor"}
    assert enforced <= documented_ids(), f"undocumented rules: {enforced - documented_ids()}"


def test_every_documented_rule_is_enforced():
    c = cfg()
    enforced = {r["id"] for r in c["compliance"]["rules"]} | {r["flag"] for r in c["risk"]["rules"]} | {"below_floor"}
    assert documented_ids() <= enforced, f"documented but not enforced: {documented_ids() - enforced}"
