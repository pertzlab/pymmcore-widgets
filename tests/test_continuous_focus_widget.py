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

    wdg = ContinuousFocusWidget(mmcore=global_mmcore, poll_interval_ms=0)
    qtbot.addWidget(wdg)
    wdg.refresh()

    assert wdg._button.isEnabled()
    assert not wdg._button.isChecked()
    assert wdg._status_color == _COLOR_OFF

    # clicking enables continuous focus on the core
    wdg._button.setChecked(True)
    wdg._on_button_clicked(True)
    assert global_mmcore.isContinuousFocusEnabled()
    assert wdg._button.isChecked()

    # clicking again disables it
    wdg._button.setChecked(False)
    wdg._on_button_clicked(False)
    assert not global_mmcore.isContinuousFocusEnabled()
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
