"""Load agent/config.yaml once. Env LLM_PROFILE overrides the profile."""
import functools
import os
from pathlib import Path

import yaml


@functools.lru_cache
def cfg() -> dict:
    data = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
    data["profile"] = os.getenv("LLM_PROFILE", data["profile"])
    return data
