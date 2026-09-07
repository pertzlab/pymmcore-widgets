"""Example usage of the ContinuousFocusWidget class.

Toggles the core's continuous-focus (autofocus) device and shows a live
indicator of whether the system is locked in focus. Because MMCore emits no
signal when the continuous-focus state changes, the widget polls its status
sources on a timer (only while visible).
"""

from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

from pymmcore_widgets import ContinuousFocusWidget

app = QApplication([])

mmc = CMMCorePlus().instance()
mmc.loadSystemConfiguration()

pfs = ContinuousFocusWidget()
pfs.show()

app.exec()
