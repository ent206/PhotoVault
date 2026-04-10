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
