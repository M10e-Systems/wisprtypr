from __future__ import annotations

import ctypes
import os


def configure_process_metadata(app_name: str = "wisprtypr") -> None:
    os.environ["PULSE_PROP_application.name"] = app_name
    os.environ["PULSE_PROP_application.process.binary"] = app_name

    try:
        libc = ctypes.CDLL(None)
        libc.prctl(15, app_name.encode("utf-8"), 0, 0, 0)
    except Exception:
        pass

    try:
        from wisprtypr.system_gi import ensure_gi_available

        ensure_gi_available()

        from gi.repository import GLib

        GLib.set_prgname(app_name)
        GLib.set_application_name(app_name)
    except Exception:
        pass
