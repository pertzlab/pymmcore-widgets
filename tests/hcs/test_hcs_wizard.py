from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import useq

from pymmcore_widgets.hcs import HCSWizard

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus
    from pytestqt.qtbot import QtBot


def test_hcs_wizard(qtbot: QtBot, global_mmcore: CMMCorePlus) -> None:
    """Test the HCSWizard."""

    plan = useq.WellPlatePlan(
        plate="96-well",
        a1_center_xy=(1000, 1500),
        rotation=0.3,
        selected_wells=slice(0, 8, 2),
    )

    wdg = HCSWizard(mmcore=global_mmcore)
    wdg.setValue(plan)
    qtbot.addWidget(wdg)
    wdg.show()
    wdg.next()
    wdg.next()
    wdg.next()
    wdg.accept()

    # we haven't done anything, the plan should be the same
    assert wdg.value() == plan


def test_hcs_wizard_calibration_applied(
    qtbot: QtBot, global_mmcore: CMMCorePlus
) -> None:
    """Applied calibrations are reported; a fit still being made is not."""
    wdg = HCSWizard(mmcore=global_mmcore)
    qtbot.addWidget(wdg)
    assert wdg.calibration() is None
    mock = Mock()
    wdg.calibrationApplied.connect(mock)

    # setValue (and so load) reports the calibration part of the plan
    wdg.setValue(
        useq.WellPlatePlan(
            plate="96-well",
            a1_center_xy=(1000, 1500),
            rotation=0.3,
            selected_wells=slice(0, 8, 2),
        )
    )
    calibration = useq.WellPlatePlan(
        plate="96-well", a1_center_xy=(1000, 1500), rotation=0.3
    )
    mock.assert_called_once_with(calibration, "loaded")
    assert wdg.calibration() == calibration

    # setCalibration keeps the well selection of the same plate...
    selection = wdg.plate_page.widget.currentSelection()
    assert selection
    mock.reset_mock()
    moved = useq.WellPlatePlan(plate="96-well", a1_center_xy=(0, 0), rotation=1.0)
    wdg.setCalibration(moved)
    mock.assert_called_once_with(moved, "set")
    assert wdg.calibration() == moved
    assert wdg.plate_page.widget.currentSelection() == selection

    # ...and switches the plate when the format differs
    other = useq.WellPlatePlan(plate="24-well", a1_center_xy=(5, 5), rotation=0.0)
    wdg.setCalibration(other)
    assert wdg.plate_page.widget.value().plate == other.plate
    assert wdg.calibration() == other

    # a calibration made on the calibration page is reported on finish only
    mock.reset_mock()
    fitted = useq.WellPlatePlan(plate="24-well", a1_center_xy=(7, 7), rotation=0.1)
    wdg.calibration_page.widget.setValue(fitted)
    mock.assert_not_called()
    assert wdg.calibration() == other
    wdg.accept()
    mock.assert_called_once_with(fitted, "finished")
    assert wdg.calibration() == fitted


def test_hcs_wizard_cancel_and_clear_calibration(
    qtbot: QtBot, global_mmcore: CMMCorePlus
) -> None:
    """Cancel undoes a fit that is not confirmed; clearCalibration forgets one."""
    wdg = HCSWizard(mmcore=global_mmcore)
    qtbot.addWidget(wdg)
    applied = useq.WellPlatePlan(plate="96-well", a1_center_xy=(10, 20), rotation=0.5)
    wdg.setCalibration(applied)
    applied_at = wdg.calibrationTime()
    assert applied_at is not None

    # a fit that the user cancels changes nothing
    fit = useq.WellPlatePlan(plate="96-well", a1_center_xy=(30, 40), rotation=1.0)
    wdg.calibration_page.widget.setValue(fit)
    wdg.reject()
    assert wdg.calibration() == applied
    assert wdg.calibrationTime() == applied_at
    assert wdg.calibration_page.widget.value() == applied

    # clearing another plate changes nothing
    wdg.clearCalibration(useq.WellPlate.from_str("384-well"))
    assert wdg.calibration() == applied
    # clearing the plate forgets the calibration and uncalibrates the page
    wdg.clearCalibration(applied.plate)
    assert wdg.calibration() is None
    assert wdg.calibrationTime() is None
    assert not wdg.calibration_page.isComplete()


def test_hcs_wizard_calibration_without_rotation(
    qtbot: QtBot, global_mmcore: CMMCorePlus
) -> None:
    """A calibration without rotation shows as calibrated, square to the stage."""
    wdg = HCSWizard(mmcore=global_mmcore)
    qtbot.addWidget(wdg)
    wdg.setCalibration(useq.WellPlatePlan(plate="96-well", a1_center_xy=(10, 20)))
    calibration = wdg.calibration()
    assert calibration is not None
    assert calibration.rotation == 0.0
    assert "Plate calibrated" in wdg.calibration_page.widget._info.text()
