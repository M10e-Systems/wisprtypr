from __future__ import annotations

import os
from pathlib import Path

from wisprtypr.system_gi import ensure_gi_available

ensure_gi_available()

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

try:  # pragma: no cover - depends on system package availability
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # type: ignore # noqa: E402

    HAS_APP_INDICATOR = True
except (ImportError, ValueError):  # pragma: no cover - depends on host
    AppIndicator3 = None
    HAS_APP_INDICATOR = False

USE_APP_INDICATOR = os.environ.get("WISPRTYPR_USE_APPINDICATOR", "0") == "1"

from wisprtypr.state import AppState


class TrayIcon:
    def __init__(self, on_toggle, on_quit) -> None:
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._on_select_chunk_duration = None
        self._on_enable_validation = None
        self._on_disable_validation = None
        self._on_mark_last_bad = None
        self._on_upload_validation = None
        self._on_delete_validation = None
        self._chunk_duration_seconds = 4
        self._chunk_items = {}
        self._validation_enabled = False
        self._status_icon = None
        self._indicator = None
        self._indicator_icon_name = "audio-input-microphone"
        self._indicator_tooltip = "WisprTypr"
        self._indicator_refresh_id = None
        if HAS_APP_INDICATOR and USE_APP_INDICATOR:
            indicator_id = f"wisprtypr-{os.getpid()}"
            self._indicator = AppIndicator3.Indicator.new(
                indicator_id,
                "audio-input-microphone-symbolic",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self._indicator.set_title("WisprTypr")
            self._indicator_refresh_id = GLib.timeout_add_seconds(6, self._refresh_indicator_registration)
        else:
            self._status_icon = Gtk.StatusIcon()
            self._status_icon.set_visible(True)
            self._status_icon.connect("activate", self._handle_activate)
            self._status_icon.connect("popup-menu", self._handle_popup_menu)
        self._menu = self._build_menu()
        if self._indicator is not None:
            self._indicator.set_menu(self._menu)

    def set_state(self, state: AppState, chunk_duration_seconds: int, error: str | None = None) -> None:
        GLib.idle_add(self._set_state_sync, state, chunk_duration_seconds, error)

    def set_chunk_duration_options(self, options, selected: int, on_select) -> None:
        self._on_select_chunk_duration = on_select
        self._chunk_duration_seconds = selected
        GLib.idle_add(self._rebuild_menu, tuple(options), selected)

    def set_chunk_duration(self, seconds: int) -> None:
        self._chunk_duration_seconds = seconds
        GLib.idle_add(self._sync_chunk_menu_state, seconds)

    def set_validation_actions(
        self,
        *,
        enabled: bool,
        on_enable,
        on_disable,
        on_mark_last_bad,
        on_upload_pending,
        on_delete_pending,
    ) -> None:
        self._validation_enabled = enabled
        self._on_enable_validation = on_enable
        self._on_disable_validation = on_disable
        self._on_mark_last_bad = on_mark_last_bad
        self._on_upload_validation = on_upload_pending
        self._on_delete_validation = on_delete_pending
        GLib.idle_add(self._sync_validation_menu_state)

    def run(self) -> None:
        Gtk.main()

    def stop(self) -> None:
        if self._indicator_refresh_id is not None:
            GLib.source_remove(self._indicator_refresh_id)
            self._indicator_refresh_id = None
        Gtk.main_quit()

    def _set_state_sync(self, state: AppState, chunk_duration_seconds: int, error: str | None) -> bool:
        self._chunk_duration_seconds = chunk_duration_seconds
        asset_dir = Path(__file__).resolve().parent / "assets"
        icon_file = {
            AppState.OFF: asset_dir / "wisprtypr-off.svg",
            AppState.LISTENING: asset_dir / "wisprtypr-on.svg",
            AppState.ERROR: asset_dir / "wisprtypr-error.svg",
        }[state]
        indicator_icon_name = {
            AppState.OFF: "audio-input-microphone",
            AppState.LISTENING: "media-record",
            AppState.ERROR: "dialog-error",
        }[state]
        tooltip = {
            AppState.OFF: f"WisprTypr: Off ({chunk_duration_seconds}s chunks)",
            AppState.LISTENING: f"WisprTypr: Listening ({chunk_duration_seconds}s chunks)",
            AppState.ERROR: f"WisprTypr: Error ({chunk_duration_seconds}s chunks){f' - {error}' if error else ''}",
        }[state]
        if self._indicator is not None:
            self._indicator_icon_name = indicator_icon_name
            self._indicator_tooltip = tooltip
            self._indicator.set_icon_full(indicator_icon_name, tooltip)
        elif self._status_icon is not None:
            self._status_icon.set_from_file(str(icon_file))
            self._status_icon.set_tooltip_text(tooltip)
        self._sync_chunk_menu_state(chunk_duration_seconds)
        return False

    def _build_menu(self):
        menu = Gtk.Menu()
        toggle_item = Gtk.MenuItem(label="Toggle")
        toggle_item.connect("activate", lambda *_args: self._on_toggle())
        menu.append(toggle_item)
        menu.append(Gtk.SeparatorMenuItem())
        chunk_header = Gtk.MenuItem(label="Chunk Length")
        chunk_header.set_sensitive(False)
        menu.append(chunk_header)
        menu.append(Gtk.SeparatorMenuItem())
        validation_header = Gtk.MenuItem(label="Validation Mode")
        validation_header.set_sensitive(False)
        menu.append(validation_header)
        self._validation_off_item = Gtk.MenuItem(label="Off")
        self._validation_off_item.connect("activate", lambda *_args: self._disable_validation())
        menu.append(self._validation_off_item)
        self._validation_on_item = Gtk.MenuItem(label="On: audio + correction capture")
        self._validation_on_item.connect("activate", lambda *_args: self._enable_validation())
        menu.append(self._validation_on_item)
        self._mark_bad_item = Gtk.MenuItem(label="Mark Last Utterance Wrong")
        self._mark_bad_item.connect("activate", lambda *_args: self._mark_last_bad())
        menu.append(self._mark_bad_item)
        self._upload_validation_item = Gtk.MenuItem(label="Upload Pending Now")
        self._upload_validation_item.connect("activate", lambda *_args: self._upload_pending_validation())
        menu.append(self._upload_validation_item)
        self._delete_validation_item = Gtk.MenuItem(label="Delete Pending Validation Data")
        self._delete_validation_item.connect("activate", lambda *_args: self._delete_pending_validation())
        menu.append(self._delete_validation_item)
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

    def _sync_validation_menu_state(self) -> bool:
        if self._validation_enabled:
            self._validation_on_item.set_sensitive(False)
            self._validation_off_item.set_sensitive(True)
            self._mark_bad_item.set_sensitive(True)
        else:
            self._validation_on_item.set_sensitive(True)
            self._validation_off_item.set_sensitive(False)
            self._mark_bad_item.set_sensitive(False)
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

    def _enable_validation(self) -> None:
        if self._confirm_validation_enable() and self._on_enable_validation is not None:
            self._validation_enabled = True
            self._on_enable_validation()
            self._sync_validation_menu_state()

    def _disable_validation(self) -> None:
        if self._on_disable_validation is not None:
            self._validation_enabled = False
            self._on_disable_validation()
            self._sync_validation_menu_state()

    def _mark_last_bad(self) -> None:
        if self._on_mark_last_bad is not None:
            self._on_mark_last_bad()

    def _upload_pending_validation(self) -> None:
        if self._on_upload_validation is not None:
            self._on_upload_validation()

    def _delete_pending_validation(self) -> None:
        if self._on_delete_validation is not None:
            self._on_delete_validation()

    def _confirm_validation_enable(self) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=None,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Enable validation mode?",
        )
        dialog.format_secondary_text(
            "WisprTypr will save dictated audio clips and likely correction edits, then upload them to the validation server."
        )
        try:
            response = dialog.run()
        finally:
            dialog.destroy()
        return response == Gtk.ResponseType.OK

    def _refresh_indicator_registration(self) -> bool:
        if self._indicator is None:
            return False
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_icon_full(self._indicator_icon_name, self._indicator_tooltip)
        self._indicator.set_menu(self._menu)
        return True
