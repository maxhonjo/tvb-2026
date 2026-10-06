import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".boku"
CONFIG_PATH = CONFIG_DIR / "config.json"

# The config is the single source of truth every shell (CLI, GUI, app) reads.
# Each source: enabled flag + poll interval in seconds. Disabled by default.
DEFAULTS = {
    "sources": {
        "location":     {"enabled": False, "interval": 300},
        "filetree":     {"enabled": False, "interval": 300},
        "keystrokes":   {"enabled": False, "interval": 60},
        "app_activity": {"enabled": False, "interval": 60},
    }
}


def _merge(defaults: dict, loaded: dict) -> dict:
    """Overlay loaded config onto defaults so missing keys fall back.

    Additive schema growth needs no version field: new keys appear here with
    their default until a shell writes them.
    """
    merged = {}
    merged["sources"] = {}
    for name, default_cfg in defaults["sources"].items():
        loaded_cfg = loaded.get("sources", {}).get(name, {})
        merged["sources"][name] = {**default_cfg, **loaded_cfg}
    return merged


def load() -> dict:
    """Read ~/.boku/config.json, merged over defaults. Writes defaults on first run."""
    if not CONFIG_PATH.exists():
        save(DEFAULTS)
        return _merge(DEFAULTS, {})
    with open(CONFIG_PATH) as f:
        loaded = json.load(f)
    return _merge(DEFAULTS, loaded)


def save(config: dict) -> None:
    """Atomically write config: temp file + os.replace, so a crash can't corrupt it."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_PATH)


def _source(config: dict, name: str) -> dict:
    if name not in config["sources"]:
        raise ValueError(f"unknown source: {name}")
    return config["sources"][name]


def set_enabled(name: str, enabled: bool) -> dict:
    """Enable or disable one source and save. Returns the new config."""
    config = load()
    _source(config, name)["enabled"] = bool(enabled)
    save(config)
    return config


def set_interval(name: str, seconds: float) -> dict:
    """Set one source's poll interval in seconds and save. Returns the new config."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise ValueError(f"interval must be a positive number, got {seconds!r}")
    config = load()
    _source(config, name)["interval"] = seconds
    save(config)
    return config


if __name__ == "__main__":
    print(load())
