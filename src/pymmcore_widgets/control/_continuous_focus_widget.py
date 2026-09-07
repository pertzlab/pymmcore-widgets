from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import QSize, Qt, QTimer, Slot
from qtpy.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget
from superqt.iconify import QIconifyIcon

if TYPE_CHECKING:
    from collections.abc import Callable

    from qtpy.QtGui import QHideEvent, QShowEvent

# indicator colors
_COLOR_LOCKED = "#4CAF50"  # green: engaged / locked in focus
_COLOR_ENABLED = "#FFB300"  # amber: mode on but not (yet) locked / searching
_COLOR_OFF = "#9E9E9E"  # grey: continuous focus off
_COLOR_ERROR = "#E53935"  # red: status could not be read

_DEFAULT_POLL_MS = 1000
_DEFAULT_TOGGLE_SETTLE_MS = 1000


class ContinuousFocusWidget(QWidget):
    """A button and a live status indicator for hardware continuous focus (PFS).

    The button turns the core's continuous-focus (autofocus) device on and off
    through [`enableContinuousFocus`][pymmcore_plus.CMMCorePlus.enableContinuousFocus].
    A colored dot next to it shows whether the system is actually locked in
    focus.

    MMCore sends no signal when the continuous-focus state changes. That is true
    for changes made in software and for changes made at the hardware, such as
    the PFS button on a Nikon scope or another widget writing the device
    property. So the widget polls its status sources on a timer while it is
    visible. That keeps the indicator correct no matter who changed the state.

    On some hardware the values MMCore caches for
    [`isContinuousFocusEnabled`][pymmcore_plus.CMMCorePlus.isContinuousFocusEnabled]
    and [`isContinuousFocusLocked`][pymmcore_plus.CMMCorePlus.isContinuousFocusLocked]
    go stale. The Nikon Ti adapter is a known case: it freezes the cached
    "enabled" flag at config load and never notices later changes. For such
    devices, pass your own live readers as ``enabled_source``, ``locked_source``
    and ``status_text_source``. The defaults use the plain MMCore queries, which
    are correct for autofocus devices that behave.

    Parameters
    ----------
    parent : QWidget | None
        Optional parent widget. By default, None.
    mmcore : CMMCorePlus | None
        Optional [`pymmcore_plus.CMMCorePlus`][] micromanager core. If not
        specified, the widget will use the active (or create a new)
        [`CMMCorePlus.instance`][pymmcore_plus.CMMCorePlus.instance].
    enabled_source : Callable[[], bool] | None
        Optional callable returning whether continuous-focus *mode* is currently
        on. Used to keep the button's checked state in sync with reality. By
        default, ``mmcore.isContinuousFocusEnabled``.
    locked_source : Callable[[], bool] | None
        Optional callable returning whether the system is currently *locked* in
        focus. Drives the indicator color. By default,
        ``mmcore.isContinuousFocusLocked``.
    status_text_source : Callable[[], str] | None
        Optional callable returning a short human-readable status string (e.g.
        "Locked in focus", "Focusing", "Focus lock failed") shown next to the
        indicator. By default a generic label is derived from the enabled/locked
        sources.
    poll_interval_ms : int
        How often, in milliseconds, to poll the status sources while the widget
        is visible. Pass 0 to disable polling (the indicator then updates only on
        button clicks and config loads). By default, 1000.
    set_enabled : Callable[[bool], None] | None
        Optional callable that turns continuous focus on or off. Use it to route
        the write through your own lock or bookkeeping. By default,
        ``mmcore.enableContinuousFocus``.
    toggle_settle_ms : int
        How long to wait, in milliseconds, after a button click before reading
        the status sources again. Polling pauses during this time. A PFS needs a
        moment to lock, and some adapters must not be queried while a write is
        still settling. By default, 1000.
    """

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        mmcore: CMMCorePlus | None = None,
        enabled_source: Callable[[], bool] | None = None,
        locked_source: Callable[[], bool] | None = None,
        status_text_source: Callable[[], str] | None = None,
        poll_interval_ms: int = _DEFAULT_POLL_MS,
        set_enabled: Callable[[bool], None] | None = None,
        toggle_settle_ms: int = _DEFAULT_TOGGLE_SETTLE_MS,
    ) -> None:
        super().__init__(parent=parent)

        self._mmc = mmcore or CMMCorePlus.instance()
        self._enabled_source = enabled_source or self._mmc.isContinuousFocusEnabled
        self._locked_source = locked_source or self._mmc.isContinuousFocusLocked
        self._status_text_source = status_text_source
        self._set_enabled = set_enabled or self._mmc.enableContinuousFocus
        self._toggle_settle_ms = max(0, int(toggle_settle_ms))

        # guard against a poll fighting a user toggle mid-flight
        self._toggling = False

        self._button = QPushButton()
        self._button.setCheckable(True)
        self._button.setIconSize(QSize(22, 22))
        self._button.clicked.connect(self._on_button_clicked)

        self._indicator = QLabel()
        self._indicator.setFixedWidth(16)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_color = _COLOR_OFF

        self._status_label = QLabel()
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._button)
        layout.addWidget(self._indicator)
        layout.addWidget(self._status_label)

        self._timer = QTimer(self)
        self._timer.setInterval(max(0, int(poll_interval_ms)))
        self._timer.timeout.connect(self.refresh)

        self._mmc.events.systemConfigurationLoaded.connect(self._on_system_cfg_loaded)
        self.destroyed.connect(self._disconnect)

        self._on_system_cfg_loaded()

    # ------------------------------------------------------------------ public

    @property
    def poll_interval_ms(self) -> int:
        """Polling interval in milliseconds (0 = polling disabled)."""
        return self._timer.interval()

    @poll_interval_ms.setter
    def poll_interval_ms(self, value: int) -> None:
        self._timer.setInterval(max(0, int(value)))
        if self.isVisible() and self._timer.interval() > 0:
            self._timer.start()

    @Slot()
    def refresh(self) -> None:
        """Re-read the status sources and update the button and indicator."""
        if self._toggling:
            return
        if not self._mmc.getAutoFocusDevice():
            self._button.setEnabled(False)
            self._set_indicator(_COLOR_OFF, "No continuous-focus device")
            return

        self._button.setEnabled(True)
        try:
            enabled = bool(self._enabled_source())
        except Exception:
            self._set_indicator(_COLOR_ERROR, "enabled: read error")
            return

        # keep the button in sync without re-emitting clicked()
        was_blocked = self._button.blockSignals(True)
        self._button.setChecked(enabled)
        self._button.blockSignals(was_blocked)
        self._set_button_state(enabled)

        try:
            locked = bool(self._locked_source())
        except Exception:
            self._set_indicator(_COLOR_ERROR, "status: read error")
            return

        if self._status_text_source is not None:
            try:
                text = str(self._status_text_source())
            except Exception:
                text = "status: read error"
        elif not enabled:
            text = "Off"
        elif locked:
            text = "Locked"
        else:
            text = "Searching"

        if not enabled:
            color = _COLOR_OFF
        elif locked:
            color = _COLOR_LOCKED
        else:
            color = _COLOR_ENABLED
        self._set_indicator(color, text)

    # ----------------------------------------------------------------- private

    @Slot()
    def _on_system_cfg_loaded(self) -> None:
        self.refresh()

    @Slot(bool)
    def _on_button_clicked(self, checked: bool) -> None:
        # Write, then wait before reading the status again. A PFS needs a moment
        # to lock, and some adapters (Nikon Ti) abort the process if the device
        # is queried or reloaded while the write is still settling. refresh()
        # does nothing while _toggling is set, so polls stay out of the way too.
        self._toggling = True
        try:
            self._set_enabled(checked)
        except Exception:
            pass
        if self._toggle_settle_ms > 0:
            QTimer.singleShot(self._toggle_settle_ms, self._finish_toggle)
        else:
            self._finish_toggle()

    def _finish_toggle(self) -> None:
        self._toggling = False
        self.refresh()

    def _set_button_state(self, enabled: bool) -> None:
        # constant label; the checked state + status indicator convey on/off
        self._button.setText("Focus Lock")
        icon = "mdi:crosshairs-gps" if enabled else "mdi:crosshairs"
        color = _COLOR_LOCKED if enabled else _COLOR_OFF
        self._button.setIcon(QIconifyIcon(icon, color=color))

    def _set_indicator(self, color: str, text: str) -> None:
        # a colored dot, drawn as an icon pixmap (no stylesheet: theming is
        # handled application-wide, see the project conventions)
        self._status_color = color
        self._indicator.setPixmap(
            QIconifyIcon("mdi:circle", color=color).pixmap(12, 12)
        )
        self._status_label.setText(text)
        self._status_label.setToolTip(text)

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self.refresh()
        if self._timer.interval() > 0:
            self._timer.start()

    def hideEvent(self, event: QHideEvent | None) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _disconnect(self) -> None:
        self._timer.stop()
        with contextlib.suppress(Exception):
            self._mmc.events.systemConfigurationLoaded.disconnect(
                self._on_system_cfg_loaded
            )
