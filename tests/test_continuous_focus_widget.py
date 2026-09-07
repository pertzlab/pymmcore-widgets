from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_widgets.control._continuous_focus_widget import (
    _COLOR_ENABLED,
    _COLOR_ERROR,
    _COLOR_LOCKED,
    _COLOR_OFF,
    ContinuousFocusWidget,
)

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus
    from pytestqt.qtbot import QtBot


def test_default_sources_track_core(qtbot: QtBot, global_mmcore: CMMCorePlus):
    """With the demo autofocus device, the button drives continuous focus."""
    global_mmcore.setAutoFocusDevice("Autofocus")
    global_mmcore.enableContinuousFocus(False)

    # toggle_settle_ms=0 makes the click path synchronous for this test
    wdg = ContinuousFocusWidget(
        mmcore=global_mmcore, poll_interval_ms=0, toggle_settle_ms=0
    )
    qtbot.addWidget(wdg)
    wdg.refresh()

    assert wdg._button.isEnabled()
    assert not wdg._button.isChecked()
    assert wdg._status_color == _COLOR_OFF

    # clicking enables continuous focus on the core; the demo device locks at once
    wdg._button.setChecked(True)
    wdg._on_button_clicked(True)
    assert global_mmcore.isContinuousFocusEnabled()
    assert wdg._button.isChecked()
    assert wdg._status_color == _COLOR_LOCKED

    # clicking again disables it
    wdg._button.setChecked(False)
    wdg._on_button_clicked(False)
    assert not global_mmcore.isContinuousFocusEnabled()
    assert not wdg._button.isChecked()
    assert wdg._status_color == _COLOR_OFF


def test_no_autofocus_device_disables_widget(qtbot: QtBot, global_mmcore: CMMCorePlus):
    global_mmcore.setAutoFocusDevice("")
    wdg = ContinuousFocusWidget(mmcore=global_mmcore, poll_interval_ms=0)
    qtbot.addWidget(wdg)
    wdg.refresh()
    assert not wdg._button.isEnabled()
    assert "continuous-focus device" in wdg._status_label.text().lower()


def test_injected_sources_reflect_external_change(
    qtbot: QtBot, global_mmcore: CMMCorePlus
):
    """Injected live readers keep the indicator truthful with no core signal.

    Simulates hardware (e.g. a Nikon PFS button) whose state changes without any
    MMCore event: the widget must re-sync on the next ``refresh``/poll.
    """
    global_mmcore.setAutoFocusDevice("Autofocus")
    state = {"enabled": True, "locked": True, "text": "Locked in focus"}

    wdg = ContinuousFocusWidget(
        mmcore=global_mmcore,
        enabled_source=lambda: state["enabled"],
        locked_source=lambda: state["locked"],
        status_text_source=lambda: state["text"],
        poll_interval_ms=0,
    )
    qtbot.addWidget(wdg)
    wdg.refresh()
    assert wdg._button.isChecked()
    assert wdg._status_color == _COLOR_LOCKED
    assert wdg._status_label.text() == "Locked in focus"

    # enabled but not yet locked -> amber "searching"
    state.update(enabled=True, locked=False, text="Focusing")
    wdg.refresh()
    assert wdg._status_color == _COLOR_ENABLED

    # turned off behind our back -> button re-syncs to unchecked
    state.update(enabled=False, locked=False, text="Off")
    wdg.refresh()
    assert not wdg._button.isChecked()
    assert wdg._status_color == _COLOR_OFF


def test_status_source_read_error_shows_red(qtbot: QtBot, global_mmcore: CMMCorePlus):
    global_mmcore.setAutoFocusDevice("Autofocus")

    def boom() -> bool:
        raise RuntimeError("device offline")

    wdg = ContinuousFocusWidget(
        mmcore=global_mmcore, locked_source=boom, poll_interval_ms=0
    )
    qtbot.addWidget(wdg)
    wdg.refresh()
    assert wdg._status_color == _COLOR_ERROR


def test_poll_interval_property(qtbot: QtBot, global_mmcore: CMMCorePlus):
    wdg = ContinuousFocusWidget(mmcore=global_mmcore, poll_interval_ms=500)
    qtbot.addWidget(wdg)
    assert wdg.poll_interval_ms == 500
    wdg.poll_interval_ms = 250
    assert wdg.poll_interval_ms == 250


def test_toggle_uses_hook_and_settles_before_rereading(
    qtbot: QtBot, global_mmcore: CMMCorePlus
):
    """A click goes through ``set_enabled`` and waits ``toggle_settle_ms``.

    While settling, polls must not read the status sources (on some hardware a
    read right after a write is fatal). The deferred refresh then applies.
    """
    global_mmcore.setAutoFocusDevice("Autofocus")
    state = {"enabled": False, "locked": False}
    writes: list[bool] = []
    reads = {"n": 0}

    def set_enabled(on: bool) -> None:
        writes.append(on)
        state.update(enabled=on, locked=on)

    def locked() -> bool:
        reads["n"] += 1
        return state["locked"]

    wdg = ContinuousFocusWidget(
        mmcore=global_mmcore,
        enabled_source=lambda: state["enabled"],
        locked_source=locked,
        set_enabled=set_enabled,
        poll_interval_ms=0,
        toggle_settle_ms=200,
    )
    qtbot.addWidget(wdg)
    wdg.refresh()
    assert wdg._status_color == _COLOR_OFF
    reads_before = reads["n"]

    wdg._button.setChecked(True)
    wdg._on_button_clicked(True)

    # the write went through the hook immediately ...
    assert writes == [True]
    # ... but the widget is settling: a poll now must not touch the sources
    assert wdg._toggling
    wdg.refresh()
    assert reads["n"] == reads_before
    assert wdg._status_color == _COLOR_OFF

    # after the settle delay the deferred refresh reads and updates
    qtbot.waitUntil(lambda: not wdg._toggling, timeout=2000)
    assert reads["n"] > reads_before
    assert wdg._status_color == _COLOR_LOCKED
