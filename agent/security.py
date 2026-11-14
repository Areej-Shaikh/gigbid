"""Prompt-injection defence layers (E4), switched in config.yaml -> security.

Production always runs with every layer on. The switches exist so the injection evaluation
(evals/runners/injection_eval.py) can measure attack success rate with and without them.

Layers that are part of the architecture and can NOT be switched off:
  - human approval: interrupt() before any submit/send; the graph has no other path to a write tool
  - least-privilege tool allowlists per agent (config.yaml -> tool_allowlist)
  - preview nodes force dry_run=True in code
"""
from agent.config import cfg

LAYERS = ("fence_untrusted", "injection_rules", "claim_verifier", "output_guard", "scam_template")


def on(layer: str) -> bool:
    if layer not in LAYERS:
        raise KeyError(f"unknown security layer {layer!r}")
    return bool((cfg().get("security") or {}).get(layer, True))


def set_layers(enabled: bool | dict) -> None:
    """Evaluation only: switch every layer (bool) or some layers ({layer: bool}) in the cached config."""
    values = {k: enabled for k in LAYERS} if isinstance(enabled, bool) else enabled
    cfg().setdefault("security", {}).update(values)
