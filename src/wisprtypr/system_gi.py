from __future__ import annotations

import sys
from pathlib import Path


def ensure_gi_available() -> None:
    try:
        import gi  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    system_paths = (
        Path("/usr/lib/python3/dist-packages"),
        Path("/usr/lib64/python3/dist-packages"),
    )
    for path in system_paths:
        path_str = str(path)
        if path.exists() and path_str not in sys.path:
            sys.path.append(path_str)

    import gi  # noqa: F401
