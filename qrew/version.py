"""Version information."""

__version__ = "0.9.5"

try:
    import os
    import warnings

    # Suppress libgit2 warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from git import Repo

    # Get the git repository at the correct level
    repo = Repo(os.path.dirname(os.path.abspath(__file__)))
    if repo.is_dirty():
        __version__ = f"{__version__}-dirty"
except Exception:
    # Not in a git repo or git not installed, just use the specified version
    pass
