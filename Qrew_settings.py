# Qrew_settings.py  -----------------------------------------------
import json, threading, pathlib

_FILE = pathlib.Path(__file__).with_name("settings.json")
_lock  = threading.Lock()
_data  = None          # lazy-loaded cache


def _load() -> dict:
    global _data
    if _data is None:
        try:
            with _FILE.open() as fh:
                _data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _data = {}
    return _data


def _flush():
    with _FILE.open("w") as fh:
        json.dump(_data, fh, indent=2)


# --------------- public API -----------------

def get(key, default=None):
    return _load().get(key, default)


def set(key, value):
    with _lock:
        _load()[key] = value
        _flush()


def as_dict() -> dict:
    """Return a **copy** of all current settings."""
    return dict(_load())


def update_many(mapping: dict):
    """Atomically update several keys at once."""
    with _lock:
        _load().update(mapping)
        _flush()
