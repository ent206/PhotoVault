# src/config.py
import json
from pathlib import Path
from typing import Any, Optional

_CONFIG_PATH = Path(__file__).parent.parent / "settings.json"


def _load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    _CONFIG_PATH.write_text(json.dumps(data, indent=2))


def get(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set(key: str, value: Any) -> None:
    data = _load()
    data[key] = value
    _save(data)


def get_last_destination() -> Optional[str]:
    return get("last_destination")


def set_last_destination(path: str) -> None:
    set("last_destination", path)
    # Keep a rolling list of the last 5 unique destinations
    recents = get_recent_destinations()
    if path in recents:
        recents.remove(path)
    recents.insert(0, path)
    set("recent_destinations", recents[:5])


def get_recent_destinations() -> list:
    recents = get("recent_destinations", None)
    if recents is None:
        # Seed from last_destination on first run
        last = get_last_destination()
        return [last] if last else []
    return recents


def set_last_date_range(start: str, end: str) -> None:
    """Persist last used date range as ISO strings (YYYY-MM-DD)."""
    set("last_date_range", {"start": start, "end": end})


def get_last_date_range() -> Optional[tuple]:
    """Returns (start_str, end_str) or None."""
    val = get("last_date_range")
    if val and "start" in val and "end" in val:
        return val["start"], val["end"]
    return None
