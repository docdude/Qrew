# Qrew_settings.py  -----------------------------------------------
import json
import threading
import pathlib
import sys

# Handle PyInstaller bundled vs development environments
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller environment - try multiple locations for settings.json in priority order:
    # 1. Root of the executable directory (for user-editable settings)
    # 2. Inside the qrew subdirectory in _MEIPASS
    # 3. Root of _MEIPASS

    locations = [
        pathlib.Path(sys.executable).parent / "settings.json",  # Exe directory
        pathlib.Path(sys._MEIPASS) / "qrew" / "settings.json",  # _MEIPASS/qrew
        pathlib.Path(sys._MEIPASS) / "settings.json",  # _MEIPASS root
    ]

    found = False
    for loc in locations:
        if loc.exists():
            _FILE = loc
            print(f"Using settings.json from: {_FILE}")
            found = True
            break

    if not found:
        # Default to executable dir for writing settings
        _FILE = locations[0]  # Exe directory is best for writing
        print(f"No settings.json found, will create at: {_FILE}")
else:
    # Development environment - settings.json is next to this .py file
    _FILE = pathlib.Path(__file__).with_name("settings.json")
    print(f"Using settings.json from development path: {_FILE}")

_lock = threading.Lock()
_data = None  # lazy-loaded cache


def _load() -> dict:
    global _data
    if _data is None:
        try:
            with _FILE.open() as fh:
                _data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # Create default settings if file doesn't exist
            _data = {
                "vlc_backend": "auto",
                "show_vlc_gui": False,
                "show_tooltips": True,
                "auto_pause_on_quality_issue": False,
                "save_after_repeat": False,
                "use_light_theme": False,
                "speaker_config": "Manual Select",
            }
            # Try to create the settings file
            try:
                _flush()
            except OSError:
                print(f"Warning: Could not create settings file at {_FILE}")
    return _data


def _flush():
    try:
        # Ensure parent directory exists
        _FILE.parent.mkdir(parents=True, exist_ok=True)

        print(f"DEBUG: Attempting to save settings to {_FILE}")
        print(f"DEBUG: Current settings data: {_data}")

        # Check if file exists and get its metadata
        if _FILE.exists():
            print(f"DEBUG: File exists, checking permissions and metadata")
            try:
                stat = _FILE.stat()
                print(f"DEBUG: File size: {stat.st_size}, Modified: {stat.st_mtime}")
                print(
                    f"DEBUG: File is{'not ' if not _FILE.is_file() else ' '}a regular file"
                )
                print(f"DEBUG: File permissions: {oct(stat.st_mode)}")
            except Exception as e:
                print(f"DEBUG: Error checking file metadata: {e}")
        else:
            print(f"DEBUG: File does not exist yet, will create")

        # Write the settings with careful error handling
        try:
            import os

            temp_file = _FILE.with_name(f".{_FILE.name}.tmp")
            with temp_file.open("w") as fh:
                json.dump(_data, fh, indent=2)

            # Verify the temp file was written correctly
            if temp_file.exists() and temp_file.stat().st_size > 0:
                # Use atomic rename when possible
                if hasattr(os, "replace"):  # Python 3.3+
                    os.replace(str(temp_file), str(_FILE))
                else:
                    # Fallback for older Python or if replace not available
                    if _FILE.exists():
                        _FILE.unlink()
                    temp_file.rename(_FILE)
                print(f"DEBUG: Successfully saved settings to {_FILE}")
            else:
                print(f"ERROR: Temp file not written correctly: {temp_file}")

        except Exception as e:
            print(f"DEBUG: Error during file write: {e}")
            raise

    except OSError as e:
        print(f"WARNING: Could not save settings to {_FILE}: {e}")
        import traceback

        traceback.print_exc()


# --------------- public API -----------------


def get(key, default=None):
    return _load().get(key, default)


def set(key, value):
    print(f"DEBUG: Setting {key} = {value}")
    with _lock:
        _load()[key] = value
        print(f"DEBUG: After setting: {key} = {_load().get(key)}")
        _flush()


def as_dict() -> dict:
    """Return a **copy** of all current settings."""
    return dict(_load())


def update_many(mapping: dict):
    """Atomically update several keys at once."""
    with _lock:
        _load().update(mapping)
        _flush()
