from pathlib import Path
from functools import lru_cache
import yaml
from typing import Any, Dict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@lru_cache()
def load_config() -> Dict[str, Any]:
    """Load and cache the YAML configuration."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_budget_ceiling() -> float:
    return float(load_config()["gig"]["budget_ceiling_usd"])


def get_tone() -> str:
    return load_config()["gig"]["tone"]


def get_gig_description() -> str:
    cfg = load_config()["gig"]
    return f"{cfg['title']}\n\n{cfg['description']}"