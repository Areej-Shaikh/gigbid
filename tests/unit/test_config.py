"""config.yaml holds every rule, threshold and prompt setting, so a silent mistake there changes behaviour.
YAML keeps the LAST of two duplicate keys without any error: this test makes that an error."""
from pathlib import Path

import yaml

from agent.config import cfg


class StrictLoader(yaml.SafeLoader):
    pass


def _no_duplicates(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate keys in config.yaml: {sorted(dupes)} (line {node.start_mark.line + 1})"
    return loader.construct_mapping(node, deep=deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def test_config_has_no_duplicate_keys():
    yaml.load(Path("agent/config.yaml").read_text(encoding="utf-8"), Loader=StrictLoader)


def test_every_node_model_and_priced_model_exist():
    c = cfg()
    assert set(c["nodes"].values()) <= {"small", "strong"}
    open_models = set(c["profiles"]["open"]["models"].values())
    assert open_models <= set(c["llm_pricing"]), f"open-profile models without a price: {open_models - set(c['llm_pricing'])}"
