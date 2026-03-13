from __future__ import annotations

from pathlib import Path

from wisprtypr.system_gi import ensure_gi_available

ensure_gi_available()

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from wisprtypr.state import AppState


class TrayIcon:
    def __init__(self, on_toggle, on_quit) -> None:
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._on_select_chunk_duration = None
        self._chunk_duration_seconds = 4
        self._chunk_items = {}
        self._icon = Gtk.StatusIcon()
        self._icon.set_visible(True)
        self._icon.connect("activate", self._handle_activate)
        self._icon.connect("popup-menu", self._handle_popup_menu)
        self._menu = self._build_menu()

    def set_state(self, state: AppState, chunk_duration_seconds: int, error: str | None = None) -> None:
        GLib.idle_add(self._set_state_sync, state, chunk_duration_seconds, error)

    def set_chunk_duration_options(self, options, selected: int, on_select) -> None:
        self._on_select_chunk_duration = on_select
        self._chunk_duration_seconds = selected
        GLib.idle_add(self._rebuild_menu, tuple(options), selected)

    def set_chunk_duration(self, seconds: int) -> None:
        self._chunk_duration_seconds = seconds
        GLib.idle_add(self._sync_chunk_menu_state, seconds)

    def run(self) -> None:
        Gtk.main()

    def stop(self) -> None:
        Gtk.main_quit()

    def _set_state_sync(self, state: AppState, chunk_duration_seconds: int, error: str | None) -> bool:
        self._chunk_duration_seconds = chunk_duration_seconds
        asset_dir = Path(__file__).resolve().parent / "assets"
        icon_name = {
            AppState.OFF: asset_dir / "wisprtypr-off.svg",
            AppState.LISTENING: asset_dir / "wisprtypr-on.svg",
            AppState.ERROR: asset_dir / "wisprtypr-error.svg",
        }[state]
        tooltip = {
            AppState.OFF: f"WisprTypr: Off ({chunk_duration_seconds}s chunks)",
            AppState.LISTENING: f"WisprTypr: Listening ({chunk_duration_seconds}s chunks)",
            AppState.ERROR: f"WisprTypr: Error ({chunk_duration_seconds}s chunks){f' - {error}' if error else ''}",
        }[state]
        self._icon.set_from_file(str(icon_name))
        self._icon.set_tooltip_text(tooltip)
        self._sync_chunk_menu_state(chunk_duration_seconds)
        return False

    def _build_menu(self):
        menu = Gtk.Menu()
        chunk_header = Gtk.MenuItem(label="Chunk Length")
        chunk_header.set_sensitive(False)
        menu.append(chunk_header)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_args: self._on_quit())
        menu.append(Gtk.SeparatorMenuItem())
        menu.append(quit_item)
        menu.show_all()
        return menu

    def _rebuild_menu(self, options, selected: int) -> bool:
        for item in self._chunk_items.values():
            self._menu.remove(item)
        self._chunk_items = {}

        group = None
        for offset, seconds in enumerate(options, start=1):
            item = Gtk.RadioMenuItem.new_with_label(group, f"{seconds}s")
            group = item.get_group()
            item.connect("activate", self._handle_chunk_duration_activate, seconds)
            self._menu.insert(item, offset)
            self._chunk_items[seconds] = item

        self._menu.show_all()
        self._sync_chunk_menu_state(selected)
        return False

    def _sync_chunk_menu_state(self, selected: int) -> bool:
        self._chunk_duration_seconds = selected
        for seconds, item in self._chunk_items.items():
            item.handler_block_by_func(self._handle_chunk_duration_activate)
            item.set_active(seconds == selected)
            item.handler_unblock_by_func(self._handle_chunk_duration_activate)
        return False

    def _handle_activate(self, *_args) -> None:
        self._on_toggle()

    def _handle_chunk_duration_activate(self, item, seconds: int) -> None:
        if item.get_active() and self._on_select_chunk_duration is not None:
            self._on_select_chunk_duration(seconds)

    def _handle_popup_menu(self, icon, button, activate_time) -> None:
        self._menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)
