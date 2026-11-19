from __future__ import annotations

import time
import warnings
from contextlib import suppress
from pathlib import Path

import useq
from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import QSize, Signal, Slot
from qtpy.QtWidgets import QFileDialog, QVBoxLayout, QWidget, QWizard, QWizardPage
from useq import WellPlatePlan

from pymmcore_widgets.useq_widgets import PointsPlanWidget, WellPlateWidget

from ._plate_calibration_widget import PlateCalibrationWidget


class HCSWizard(QWizard):
    """A wizard to setup an High Content Screening (HCS) experiment.

    This widget can be used to select a plate, calibrate it, and then select the number
    of images (and their arrangement) to acquire per well.  The output is a
    [useq.WellPlatePlan][] object, which can be retrieved with the `value()` method.

    Parameters
    ----------
    parent : QWidget | None
        The parent widget. By default, None.
    mmcore : CMMCorePlus | None
        The CMMCorePlus instance. By default, None.
    """

    # Emitted with (plan, source) whenever a plate calibration is applied to the
    # wizard. `plan` is a useq.WellPlatePlan that holds only the plate, the A1
    # center and the rotation. `source` tells where the calibration came from:
    # "loaded" (`setValue` or `load`, e.g. a file or an MDA sequence), "set"
    # (`setCalibration`) or "finished" (the user finished the wizard). Fits made
    # while wells are still being calibrated are not emitted.
    calibrationApplied = Signal(object, str)

    def __init__(
        self, parent: QWidget | None = None, *, mmcore: CMMCorePlus | None = None
    ) -> None:
        super().__init__(parent)
        self._mmc = mmcore or CMMCorePlus.instance()
        self._calibrated: bool = False
        # the last applied calibration and when it was applied (time.time())
        self._applied: useq.WellPlatePlan | None = None
        self._applied_at: float | None = None

        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setWindowTitle("HCS Wizard")

        # WIZARD PAGES ----------------------

        self.plate_page = _PlatePage(self)
        self.calibration_page = _PlateCalibrationPage(self._mmc, self)
        self.points_plan_page = _PointsPlanPage(self._mmc, self)

        self.addPage(self.plate_page)
        self.addPage(self.calibration_page)
        self.addPage(self.points_plan_page)

        # SAVE/LOAD BUTTONS ----------------------

        # add custom button to save
        self.setOption(QWizard.WizardOption.HaveCustomButton1, True)
        if save_btn := self.button(QWizard.WizardButton.CustomButton1):
            save_btn.setText("Save")
            save_btn.clicked.connect(self.save)
            save_btn.setEnabled(False)
        # add custom button to load
        self.setOption(QWizard.WizardOption.HaveCustomButton2, True)
        if load_btn := self.button(QWizard.WizardButton.CustomButton2):
            load_btn.setText("Load")
            load_btn.clicked.connect(self.load)

        # CONNECTIONS ---------------------------

        self.plate_page.widget.valueChanged.connect(self._on_plate_changed)
        self._on_plate_changed(self.plate_page.widget.value())
        self.calibration_page.widget.calibrationChanged.connect(
            self._on_calibration_changed
        )
        self.accepted.connect(self._on_accepted)
        self.rejected.connect(self._on_rejected)

    def sizeHint(self) -> QSize:
        return QSize(880, 690)

    def value(self) -> useq.WellPlatePlan | None:
        """Return the current well plate plan, or None if the plan is uncalibrated."""
        calib_plan = self.calibration_page.widget.value()
        if not self._calibrated or not calib_plan:  # pragma: no cover
            return None

        plate_plan = self.plate_page.widget.value()
        if plate_plan.plate != calib_plan.plate:  # pragma: no cover
            warnings.warn("Plate Plan and Calibration Plan do not match.", stacklevel=2)
            return None

        return useq.WellPlatePlan(
            plate=plate_plan.plate,
            selected_wells=plate_plan.selected_wells,
            rotation=calib_plan.rotation,
            a1_center_xy=calib_plan.a1_center_xy,
            well_points_plan=self.points_plan_page.widget.value(),
        )

    def setValue(self, value: useq.WellPlatePlan) -> None:
        """Set the state of the wizard to a WellPlatePlan."""
        self.plate_page.widget.setValue(value)
        self.calibration_page.widget.setValue(value)
        # update the points plan fov size if it's not set
        point_plan = value.well_points_plan
        if point_plan.fov_width is None or point_plan.fov_height is None:
            point_plan.fov_width, point_plan.fov_height = (
                self.points_plan_page._get_fov_size()
            )
        self.points_plan_page.widget.setValue(point_plan)
        self._apply_calibration("loaded")

    def calibration(self) -> useq.WellPlatePlan | None:
        """Return the last applied plate calibration, or None.

        A calibration is applied when it is loaded (`setValue`, `load`), set with
        `setCalibration`, or confirmed by finishing the wizard. A fit that the
        user is still making on the calibration page is not returned. The
        returned plan holds only the plate, the A1 center and the rotation.
        """
        return self._applied

    def calibrationTime(self) -> float | None:
        """Return when the calibration was applied (as `time.time()`), or None."""
        return self._applied_at

    def setCalibration(self, plan: useq.WellPlatePlan) -> None:
        """Apply the plate calibration of `plan` (plate, A1 center and rotation).

        Unlike `setValue`, this keeps the well selection and the points plan.
        Only a different plate format resets the well selection.
        """
        if self.plate_page.widget.value().plate != plan.plate:
            self.plate_page.widget.setValue(plan.plate)
            self._on_plate_changed(self.plate_page.widget.value())
        # a calibration without rotation is square with the stage axes; with
        # rotation None, the calibration page would ask for a calibration
        self.calibration_page.widget.setValue(
            useq.WellPlatePlan(
                plate=plan.plate,
                a1_center_xy=plan.a1_center_xy,
                rotation=plan.rotation or 0.0,
            )
        )
        self._apply_calibration("set")

    def clearCalibration(self, plate: useq.WellPlate) -> None:
        """Forget the calibration of `plate`, e.g. after it was deleted elsewhere.

        If the calibration page shows that calibration, it goes back to an
        uncalibrated `plate`. Nothing is emitted.
        """
        if self._applied is None or self._applied.plate != plate:
            return
        if self.calibration_page.widget.value() == self._applied:
            self.calibration_page.widget.setValue(plate)
        self._applied = self._applied_at = None

    @Slot()
    def save(self, path: str | None = None) -> None:
        """Save the current well plate plan to disk."""
        if not isinstance(path, str):
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Well Plate Plan", "", "JSON (*.json)"
            )
        elif not path.endswith(".json"):  # pragma: no cover
            raise ValueError("Path must end with '.json'")
        if path and (value := self.value()):
            txt = value.model_dump_json(exclude_unset=True, indent=2)
            Path(path).write_text(txt)

    @Slot()
    def load(self, path: str | None = None) -> None:
        """Load a well plate plan from disk."""
        if not isinstance(path, str):
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Well Plate Plan", "", "JSON (*.json)"
            )
        if path:
            self.setValue(WellPlatePlan.from_file(path))

    @Slot(object)
    def _on_plate_changed(self, plate_plan: useq.WellPlatePlan) -> None:
        """Synchronize the points plan with the well size/shape."""
        # update the calibration widget with the new plate if it's different
        current_calib_plan = self.calibration_page.widget.value()
        if current_calib_plan is None or current_calib_plan.plate != plate_plan.plate:
            self.calibration_page.widget.setValue(plate_plan.plate)

        pp_widget = self.points_plan_page.widget

        # set the well size on the points plan widget to the current plate well size
        well_width, well_height = plate_plan.plate.well_size
        pp_widget.setWellSize(well_width, well_height)

        # additionally, restrict the max width and height of the random points widget
        # to the plate size minus the fov size.
        fovw = pp_widget._selector.fov_w.value()
        fovh = pp_widget._selector.fov_h.value()

        # if the random points shape is a rectangle, but the wells are circular,
        # reduce the max width and height by 1.4 to keep the points inside the wells
        random_wdg = pp_widget.random_points_wdg
        if random_wdg.shape.currentText() == useq.Shape.RECTANGLE.value:
            if plate_plan.plate.circular_wells:
                well_width /= 1.4
                well_height /= 1.4

        random_wdg.max_width.setMaximum(well_width * 1000)
        random_wdg.max_width.setValue(well_width * 1000 - fovw / 1.4)
        random_wdg.max_height.setMaximum(well_height * 1000)
        random_wdg.max_height.setValue(well_height * 1000 - fovh / 1.4)

    @Slot(bool)
    def _on_calibration_changed(self, calibrated: bool) -> None:
        self._calibrated = calibrated
        self.button(QWizard.WizardButton.CustomButton1).setEnabled(calibrated)

    def _apply_calibration(self, source: str) -> None:
        """Record the calibration of the calibration page as applied, and emit it."""
        plan = self.calibration_page.widget.value()
        if not self._calibrated or plan is None:
            return
        self._applied = plan
        self._applied_at = time.time()
        self.calibrationApplied.emit(plan, source)

    @Slot()
    def _on_accepted(self) -> None:
        self._apply_calibration("finished")

    @Slot()
    def _on_rejected(self) -> None:
        """Undo a fit that the user made on the calibration page but did not confirm."""
        applied = self._applied
        current = self.calibration_page.widget.value()
        if (
            applied is not None
            and current is not None
            and current.plate == applied.plate
            and current != applied
        ):
            self.calibration_page.widget.setValue(applied)


# ---------------------------------- PAGES ---------------------------------------


class _PlatePage(QWizardPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setTitle("Plate and Well Selection")

        self.widget = WellPlateWidget()
        self.widget.setShowRotation(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)


class _PlateCalibrationPage(QWizardPage):
    def __init__(self, mmcore: CMMCorePlus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Plate Calibration")

        self._is_complete = False
        self.widget = PlateCalibrationWidget(mmcore=mmcore)
        self.widget.calibrationChanged.connect(self._on_calibration_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)

    def isComplete(self) -> bool:
        return self._is_complete

    @Slot(bool)
    def _on_calibration_changed(self, calibrated: bool) -> None:
        self._is_complete = calibrated
        self.completeChanged.emit()


class _PointsPlanPage(QWizardPage):
    def __init__(self, mmcore: CMMCorePlus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mmc = mmcore
        self.setTitle("Field of View Selection")

        self.widget = PointsPlanWidget()
        self.widget._selector.fov_widgets.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)

        self._mmc.events.pixelSizeChanged.connect(self._on_px_size_changed)
        self._mmc.events.systemConfigurationLoaded.connect(self._on_px_size_changed)
        self._on_px_size_changed()

    @Slot()
    def _on_px_size_changed(self) -> None:
        val = self.widget.value()
        val.fov_width, val.fov_height = self._get_fov_size()
        self.widget.setValue(val)

    def _get_fov_size(self) -> tuple[float, float] | tuple[None, None]:
        with suppress(RuntimeError):
            if self._mmc.getCameraDevice() and (px := self._mmc.getPixelSizeUm()):
                return self._mmc.getImageWidth() * px, self._mmc.getImageHeight() * px
        return (None, None)
