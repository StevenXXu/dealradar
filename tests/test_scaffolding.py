# tests/test_scaffolding.py
import json
from pathlib import Path

def test_vc_seeds_config_exists():
    config_path = Path("config/vc_seeds.json")
    assert config_path.exists(), "vc_seeds.json must exist"

def test_vc_seeds_config_valid():
    with open("config/vc_seeds.json") as f:
        seeds = json.load(f)
    assert isinstance(seeds, list)
    assert len(seeds) == 10
    for seed in seeds:
        assert "name" in seed
        assert "url" in seed
        assert seed["url"].startswith("http")
