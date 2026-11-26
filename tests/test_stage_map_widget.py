from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import useq
from qtpy.QtWidgets import QFileDialog, QMessageBox

from pymmcore_widgets.control._stage_map._calibration_store import (
    PlateCalibrationStore,
)
from pymmcore_widgets.control._stage_map._overlays import nearest_well
from pymmcore_widgets.control._stage_map._stage_map_widget import StageMapWidget
from pymmcore_widgets.useq_widgets import PositionTable

if TYPE_CHECKING:
    from pathlib import Path

    from pymmcore_plus import CMMCorePlus
    from pytestqt.qtbot import QtBot

    from pymmcore_widgets import MDAWidget

A1_XY = (1000.0, 2000.0)
PLAN = useq.WellPlatePlan(plate="96-well", a1_center_xy=A1_XY, rotation=2.0)
SPACING = 9000  # 96-well pitch in µm


def _map_with_table(
    qtbot: QtBot, mmcore: CMMCorePlus, tmp_path: Path
) -> tuple[StageMapWidget, PositionTable]:
    """A map bound to a standalone position table (the widget has none of its own)."""
    table = PositionTable()
    qtbot.addWidget(table)
    wdg = StageMapWidget(mmcore=mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.setPositionTable(table)
    return wdg, table


def _set_positions(
    wdg: StageMapWidget, table: PositionTable, positions: list[useq.Position]
) -> None:
    """Set positions on the table and let the map know (setValue is silent)."""
    table.setValue(positions)
    table.valueChanged.emit()


def test_calibration_store(tmp_path: Path) -> None:
    store = PlateCalibrationStore(tmp_path)
    assert not store.has_calibration("96-well")
    assert store.load("96-well") is None

    file = store.save(PLAN)
    assert file.is_file()
    assert store.has_calibration("96-well")

    loaded = store.load("96-well")
    assert loaded is not None
    assert loaded.a1_center_xy == A1_XY
    assert loaded.rotation == 2.0
    assert loaded.plate == PLAN.plate

    assert store.delete("96-well")
    assert not store.has_calibration("96-well")
    assert not store.delete("96-well")


def test_nearest_well() -> None:
    # a point slightly off the center of well B2 (row 1, col 1)
    hit = nearest_well(
        useq.WellPlatePlan(plate="96-well", a1_center_xy=A1_XY),
        A1_XY[0] + SPACING + 100,
        A1_XY[1] - SPACING - 100,
    )
    assert (hit.row, hit.col, hit.name) == (1, 1, "B2")
    assert hit.inside

    # a point in the gap between wells is not inside its closest well
    hit = nearest_well(
        useq.WellPlatePlan(plate="96-well", a1_center_xy=A1_XY),
        A1_XY[0] + SPACING / 2,
        A1_XY[1],
    )
    assert not hit.inside

    # with rotation, the well centers rotate accordingly
    rotated = useq.WellPlatePlan(plate="96-well", a1_center_xy=A1_XY, rotation=90)
    hit = nearest_well(rotated, A1_XY[0], A1_XY[1] + SPACING)
    assert (hit.row, hit.col, hit.name) == (0, 1, "A2")
    assert hit.inside


def test_stage_map_plate_selection(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)

    # no plate selected initially
    assert wdg.platePlan() is None
    assert not wdg._plate_overlay._outlines.visible

    # selecting an uncalibrated plate shows a preview, but platePlan() is None
    wdg.toolBar().plate_combo.setCurrentText("96-well")  # type: ignore[attr-defined]
    assert wdg.platePlan() is None
    assert wdg._plan is not None
    assert wdg._plan.plate.name == "96-well"
    assert wdg._plate_overlay._outlines.visible

    # once a calibration is stored, re-selecting the plate loads it
    PlateCalibrationStore(tmp_path).save(PLAN)
    wdg.toolBar().plate_combo.setCurrentText("None")  # type: ignore[attr-defined]
    mock = Mock()
    wdg.platePlanChanged.connect(mock)
    wdg.toolBar().plate_combo.setCurrentText("96-well")  # type: ignore[attr-defined]
    mock.assert_called_once()
    plan = wdg.platePlan()
    assert plan is not None
    assert plan.a1_center_xy == A1_XY
    assert plan.rotation == 2.0


def test_stage_map_set_plate_plan(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)

    mock = Mock()
    wdg.platePlanChanged.connect(mock)
    wdg.setPlatePlan(PLAN)
    mock.assert_called_once_with(PLAN)
    assert wdg.platePlan() == PLAN
    assert wdg.toolBar().plate_combo.currentText() == "96-well"  # type: ignore[attr-defined]

    # a custom (unregistered) plate is added to the combo
    custom = useq.WellPlate(
        rows=2, columns=2, well_spacing=10, well_size=8, name="my-plate"
    )
    wdg.setPlatePlan(custom)
    assert wdg.toolBar().plate_combo.currentText() == "my-plate"  # type: ignore[attr-defined]
    assert wdg.platePlan() is None  # not calibrated

    wdg.setPlatePlan(None)
    assert wdg.platePlan() is None
    assert not wdg._plate_overlay._outlines.visible


def test_stage_map_positions_and_trails(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)

    overlay = wdg._positions_overlay
    assert not overlay._markers.visible

    _set_positions(
        wdg,
        table,
        [
            useq.Position(x=0, y=0, name="a"),
            useq.Position(x=100, y=0, name="b"),
            useq.Position(x=100, y=100, name="c"),
        ],
    )
    assert overlay._markers.visible
    assert overlay._trail.visible
    assert len(overlay._markers._data["a_position"]) == 3

    # toggling the trails action hides the travel path
    wdg.toolBar().trails_action.setChecked(False)  # type: ignore[attr-defined]
    assert not overlay._trail.visible
    wdg.toolBar().trails_action.setChecked(True)  # type: ignore[attr-defined]
    assert overlay._trail.visible

    # labels toggle affects both well and position labels
    wdg.toolBar().labels_action.setChecked(False)  # type: ignore[attr-defined]
    assert not overlay._labels.visible

    _set_positions(wdg, table, [])
    assert not overlay._markers.visible
    assert not overlay._trail.visible

    # unbinding the table clears the map
    _set_positions(wdg, table, [useq.Position(x=0, y=0, name="a")])
    assert overlay._markers.visible
    wdg.setPositionTable(None)
    assert wdg.positionTable() is None
    assert not overlay._markers.visible


def test_stage_map_assign_wells(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)
    wdg.setPlatePlan(PLAN)

    _set_positions(
        wdg,
        table,
        [
            useq.Position(x=A1_XY[0] + 10, y=A1_XY[1] + 5, name="fov0"),
            useq.Position(x=A1_XY[0] + SPACING, y=A1_XY[1]),  # ~well A2
            useq.Position(x=A1_XY[0] + SPACING + 50, y=A1_XY[1]),  # also ~A2
        ],
    )
    mock = Mock()
    wdg.wellsAssigned.connect(mock)
    wdg.assign_wells_to_positions()
    mock.assert_called_once()

    # the wells land on the positions as plate indices, and the names are left
    # alone, so they stay free for user labels
    positions = wdg.value()
    assert [p.name for p in positions] == ["fov0", None, None]
    assert [(p.plate_row, p.plate_col) for p in positions] == [(0, 0), (0, 1), (0, 1)]
    # ...written into the bound table itself, where the column is now visible
    assert table.wellColumnVisible()
    assert [(p.plate_row, p.plate_col) for p in table.value()] == [
        (0, 0),
        (0, 1),
        (0, 1),
    ]

    # re-assigning simply overwrites the wells
    wdg.assign_wells_to_positions()
    assert [(p.plate_row, p.plate_col) for p in wdg.value()] == [(0, 0), (0, 1), (0, 1)]


def test_stage_map_assign_wells_requires_calibration(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)

    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args[1]))
    _set_positions(wdg, table, [useq.Position(x=0, y=0, name="fov0")])
    wdg.assign_wells_to_positions()
    assert infos  # warned, nothing renamed
    assert [p.name for p in wdg.value()] == ["fov0"]

    # ...and likewise with a calibrated plate but no bound table
    wdg.setPlatePlan(PLAN)
    wdg.setPositionTable(None)
    infos.clear()
    wdg.assign_wells_to_positions()
    assert infos
    assert wdg.value() == ()


def test_stage_map_double_click_moves_stage(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    from vispy.app.canvas import MouseEvent

    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.show()

    global_mmcore.setXYPosition(0.0, 0.0)
    global_mmcore.waitForSystem()

    event = MouseEvent("mouse_double_click", pos=(100, 100), button=1)
    wdg._on_mouse_double_click(event)
    expected = wdg._stage_viewer.view.camera.transform.imap((100, 100))[:2]

    def _at_target() -> None:
        x, y = global_mmcore.getXYPosition()
        assert x == pytest.approx(expected[0], abs=1.0)
        assert y == pytest.approx(expected[1], abs=1.0)

    qtbot.waitUntil(_at_target, timeout=2000)


def test_stage_map_delete_calibration(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    PlateCalibrationStore(tmp_path).save(PLAN)
    wdg.toolBar().plate_combo.setCurrentText("96-well")  # type: ignore[attr-defined]
    assert wdg.platePlan() is not None

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    wdg._delete_calibration()
    assert not PlateCalibrationStore(tmp_path).has_calibration("96-well")
    # plate still shown, but as uncalibrated preview
    assert wdg.platePlan() is None
    assert wdg._plan is not None
    assert wdg._plate_overlay._outlines.visible


def test_stage_map_polling(qtbot: QtBot, global_mmcore: CMMCorePlus) -> None:
    wdg = StageMapWidget(mmcore=global_mmcore)
    qtbot.addWidget(wdg)
    assert wdg.poll_stage_position
    assert wdg._stage_pos_marker.visible

    global_mmcore.setXYPosition(123.0, 456.0)
    global_mmcore.waitForSystem()
    qtbot.waitUntil(lambda: "123.00" in wdg._stage_pos_label.text(), timeout=2000)

    wdg.poll_stage_position = False
    assert not wdg.poll_stage_position
    assert not wdg._stage_pos_marker.visible


def test_affine_state_without_transpose_props(global_mmcore: CMMCorePlus) -> None:
    """Cameras without Transpose_* properties (e.g. python devices) must work."""
    from pymmcore_widgets.control._stage_explorer._stage_explorer import AffineState

    class NoTransposeCore:
        """Stands in for a core whose camera lacks the Transpose_* properties."""

        def __getattr__(self, name: str) -> object:
            return getattr(global_mmcore, name)

        def hasProperty(self, device: str, prop: str) -> bool:
            return False

    state = AffineState(NoTransposeCore())  # type: ignore[arg-type]
    px = global_mmcore.getPixelSizeUm()
    assert state.system_affine[0, 0] == pytest.approx(px)
    assert state.system_affine[1, 1] == pytest.approx(px)


def test_affine_state_with_degenerate_pixel_affine(global_mmcore: CMMCorePlus) -> None:
    """An all-zeros pixel size affine must fall back to plain pixel size scaling."""
    from pymmcore_widgets.control._stage_explorer._stage_explorer import AffineState

    state = AffineState(global_mmcore)
    state.pixel_size_affine = (0.0,) * 6
    matrix = state._compute_system_affine()
    px = global_mmcore.getPixelSizeUm()
    assert matrix[0, 0] == pytest.approx(px)
    assert matrix[1, 1] == pytest.approx(px)


def test_stage_map_links_external_table(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """The map can mirror a PositionTable living in another widget."""
    from pymmcore_widgets import MDAWidget

    mda = MDAWidget(mmcore=global_mmcore)
    qtbot.addWidget(mda)
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)

    external = mda.stage_positions
    assert wdg.positionTable() is None  # the widget has no table of its own
    found = wdg.linkablePositionTables()
    assert external in found.values()

    mock = Mock()
    wdg.positionTableChanged.connect(mock)
    wdg.setPositionTable(external)
    mock.assert_called_once_with(external)
    assert wdg.positionTable() is external

    # positions set on the external table show up on the map
    external.setValue([useq.Position(x=0, y=0, name="a"), useq.Position(x=50, y=50)])
    external.valueChanged.emit()
    assert len(wdg._positions_overlay._markers._data["a_position"]) == 2

    # ...and well assignment renames the external table's rows
    wdg.setPlatePlan(PLAN)
    external.setValue(
        [
            useq.Position(x=A1_XY[0], y=A1_XY[1], name="a"),
            useq.Position(x=A1_XY[0] + SPACING, y=A1_XY[1]),
        ]
    )
    wdg.assign_wells_to_positions()
    assert [p.name for p in external.value()] == ["a", None]
    assert [(p.plate_row, p.plate_col) for p in external.value()] == [(0, 0), (0, 1)]

    # ...and the map can be unbound again
    wdg.setPositionTable(None)
    assert wdg.positionTable() is None
    assert wdg.value() == ()


def test_stage_map_unbinds_when_table_destroyed(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)
    assert wdg.positionTable() is table

    table.deleteLater()
    qtbot.waitUntil(lambda: wdg.positionTable() is None, timeout=2000)


def test_stage_map_binds_to_first_table_on_show(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """Dropping the map next to an existing position list just works."""
    table = PositionTable()
    qtbot.addWidget(table)
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    assert wdg.positionTable() is None

    wdg.show()
    assert wdg.positionTable() is table

    # an explicit choice is not overridden the next time it is shown
    wdg.setPositionTable(None)
    wdg.hide()
    wdg.show()
    assert wdg.positionTable() is None


def test_stage_map_fov_rect_follows_camera(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """Position rectangles and the stage marker must match the camera FOV."""
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)
    _set_positions(wdg, table, [useq.Position(x=0, y=0, name="a")])

    px = global_mmcore.getPixelSizeUm()
    full_w, full_h = global_mmcore.getImageWidth(), global_mmcore.getImageHeight()
    assert wdg._fov_size() == pytest.approx((full_w * px, full_h * px))

    # an ROI crop shrinks both the drawn rectangles and the stage marker
    global_mmcore.setROI(0, 0, full_w // 2, full_h // 4)
    qtbot.waitUntil(
        lambda: (
            wdg._last_fov_size == pytest.approx((full_w // 2 * px, full_h // 4 * px))
        ),
        timeout=2000,
    )
    assert wdg._stage_pos_marker._rect.width == full_w // 2
    assert wdg._stage_pos_marker._rect.height == full_h // 4

    global_mmcore.clearROI()
    qtbot.waitUntil(
        lambda: wdg._last_fov_size == pytest.approx((full_w * px, full_h * px)),
        timeout=2000,
    )


def test_stage_map_calibration_dialog(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """Calibrating three wells stores and applies the plate calibration."""
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.setPlatePlan("96-well")
    assert wdg.platePlan() is None  # not calibrated yet

    dialog = wdg.calibrate()
    assert dialog is not None
    qtbot.addWidget(dialog)
    # the dialog must not be modal: the stage has to stay drivable while open
    assert not dialog.isModal()
    # calling again returns the same dialog rather than stacking them up
    assert wdg.calibrate() is dialog

    calib = dialog._calibration
    # drive the stage to the center of three (non-collinear) wells and record them
    for (row, col), (x, y) in {
        (0, 0): (0.0, 0.0),
        (0, 2): (18000.0, 0.0),
        (2, 0): (0.0, -18000.0),
    }.items():
        calib._plate_view.setSelectedIndices([(row, col)])
        global_mmcore.setXYPosition(x, y)
        qtbot.waitUntil(
            lambda x=x, y=y: global_mmcore.getXYPosition() == pytest.approx((x, y)),
            timeout=5000,
        )
        well_wdg = calib._current_calibration_widget()
        assert well_wdg is not None
        well_wdg._set_button.click()

    dialog.accept()

    plan = wdg.platePlan()
    assert plan is not None
    assert plan.a1_center_xy == pytest.approx((0.0, 0.0), abs=1)
    assert plan.rotation == pytest.approx(0.0, abs=0.01)
    # ...and it was persisted for the next session
    stored = PlateCalibrationStore(tmp_path).load("96-well")
    assert stored is not None
    assert stored.a1_center_xy == plan.a1_center_xy
    qtbot.waitUntil(lambda: wdg._calib_dialog is None, timeout=2000)


def test_stage_map_assign_wells_skips_hcs_table(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positions generated by the HCS wizard are named by it, not by the map."""
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)
    wdg.setPlatePlan(PLAN)
    _set_positions(wdg, table, [useq.Position(x=A1_XY[0], y=A1_XY[1], name="fov0")])
    # pretend the table is locked to a plate plan by the HCS wizard
    table._plate_plan = PLAN  # type: ignore[attr-defined]

    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args[1]))
    wdg.assign_wells_to_positions()
    assert infos
    assert not table.table().rowData(0).get("well")


def _calib(plan: useq.WellPlatePlan | None) -> tuple | None:
    """The part of a plan that the map and the HCS wizard share."""
    if plan is None:
        return None
    return plan.plate.name, plan.a1_center_xy, plan.rotation


def _map_with_mda(
    qtbot: QtBot, mmcore: CMMCorePlus, tmp_path: Path
) -> tuple[StageMapWidget, MDAWidget]:
    """A map bound to the position table of an MDA widget."""
    from pymmcore_widgets import MDAWidget

    mda = MDAWidget(mmcore=mmcore)
    qtbot.addWidget(mda)
    # the table starts with the current stage position; empty it, so finishing
    # the HCS wizard does not open the (modal) "Overwrite Positions" dialog
    mda.stage_positions.setValue([])
    wdg = StageMapWidget(mmcore=mmcore, calibration_dir=tmp_path / "store")
    qtbot.addWidget(wdg)
    wdg.setPositionTable(mda.stage_positions)
    return wdg, mda


def test_stage_map_import_calibrates_hcs_wizard(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A calibration imported in the map is applied to the MDA's HCS wizard."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()
    assert wizard.calibration() is None
    wizard.plate_page.widget.setValue(
        useq.WellPlatePlan(
            plate="96-well", a1_center_xy=(0, 0), selected_wells=(0, slice(0, 3))
        )
    )
    selection = wizard.plate_page.widget.currentSelection()
    assert len(selection) == 3

    file = tmp_path / "calibration.json"
    file.write_text(PLAN.model_dump_json())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(file), ""))
    wdg._import_calibration()

    assert _calib(wizard.calibration()) == _calib(PLAN)
    # the experiment's well selection is kept for the same plate format
    assert wizard.plate_page.widget.currentSelection() == selection


def test_hcs_wizard_calibration_shows_on_stage_map(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A calibration loaded or confirmed in the HCS wizard shows on the map."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()
    store = PlateCalibrationStore(tmp_path / "store")
    ask = Mock(return_value=True)
    monkeypatch.setattr(wdg, "_ask_use_loaded_calibration", ask)

    # loaded from a file in the wizard: shown, and stored like an import
    loaded = useq.WellPlatePlan(
        plate="384-well",
        a1_center_xy=(500.0, -500.0),
        rotation=-1.0,
        selected_wells=slice(0, 2),
    )
    file = tmp_path / "plan.json"
    file.write_text(loaded.model_dump_json())
    wizard.load(str(file))
    assert _calib(wdg.platePlan()) == _calib(loaded)
    assert wdg.toolBar().plate_combo.currentText() == "384-well"  # type: ignore[attr-defined]
    assert _calib(store.load("384-well")) == _calib(loaded)

    # calibrated in the wizard: shown once the wizard is finished
    fitted = useq.WellPlatePlan(plate="384-well", a1_center_xy=A1_XY, rotation=0.5)
    wizard.calibration_page.widget.setValue(fitted)
    assert _calib(wdg.platePlan()) == _calib(loaded)
    wizard.accept()
    assert _calib(wdg.platePlan()) == _calib(fitted)

    # loaded with an MDA sequence whose positions are a plate plan; it differs
    # from the stored calibration, so the map asks first
    ask.assert_not_called()
    in_sequence = loaded.model_copy(update={"a1_center_xy": (10.0, 20.0)})
    mda.setValue(useq.MDASequence(stage_positions=in_sequence))
    ask.assert_called_once()
    assert _calib(wdg.platePlan()) == _calib(in_sequence)


def test_stage_map_binding_syncs_hcs_wizard(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """On binding, the newer calibration wins; an uncalibrated wizard gets one."""
    from pymmcore_widgets import MDAWidget

    mda = MDAWidget(mmcore=global_mmcore)
    qtbot.addWidget(mda)
    table = mda.stage_positions
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)

    wdg.setPlatePlan(PLAN)
    wdg.setPositionTable(table)
    assert _calib(table.hcsWizard().calibration()) == _calib(PLAN)

    # unbound, the two are independent
    wdg.setPositionTable(None)
    other = useq.WellPlatePlan(plate="96-well", a1_center_xy=(0.0, 0.0), rotation=0.0)
    table.hcsWizard().setCalibration(other)
    assert _calib(wdg.platePlan()) == _calib(PLAN)

    wdg.setPositionTable(table)
    assert _calib(wdg.platePlan()) == _calib(other)


def _import(
    wdg: StageMapWidget,
    plan: useq.WellPlatePlan,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import `plan` in the map, as from the toolbar (which also stores it)."""
    file = tmp_path / "import.json"
    file.write_text(plan.model_dump_json())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(file), ""))
    wdg._import_calibration()


def test_stage_map_rebinding_keeps_the_newer_calibration(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On binding again, an older wizard calibration does not replace a newer one."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    table = mda.stage_positions
    wizard = table.hcsWizard()
    store = PlateCalibrationStore(tmp_path / "store")
    wdg.setPlatePlan(PLAN)
    assert _calib(wizard.calibration()) == _calib(PLAN)

    # unbound, the map stores a newer calibration and then shows no plate
    wdg.setPositionTable(None)
    newer = useq.WellPlatePlan(plate="96-well", a1_center_xy=(5e3, 6e3), rotation=1.0)
    _import(wdg, newer, tmp_path, monkeypatch)
    wizard._applied_at = (wizard.calibrationTime() or 0.0) - 10  # older, for sure
    wdg.setPlatePlan(None)

    wdg.setPositionTable(table)
    assert _calib(wdg.platePlan()) == _calib(newer)
    assert _calib(store.load("96-well")) == _calib(newer)
    assert _calib(wizard.calibration()) == _calib(newer)


def test_stage_map_ignores_a_cancelled_wizard_fit(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """A fit that the user cancels in the wizard reaches neither map nor store."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    table = mda.stage_positions
    wizard = table.hcsWizard()
    wdg.setPlatePlan(PLAN)

    fit = useq.WellPlatePlan(plate="96-well", a1_center_xy=(-1.0, -2.0), rotation=3.0)
    wizard.calibration_page.widget.setValue(fit)
    wizard.reject()
    wdg.setPositionTable(None)
    wdg.setPositionTable(table)

    assert _calib(wdg.platePlan()) == _calib(PLAN)
    assert PlateCalibrationStore(tmp_path / "store").load("96-well") is None
    assert _calib(wizard.calibration()) == _calib(PLAN)


def test_stage_map_deleted_calibration_stays_deleted(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a delete in the map, the wizard does not send the calibration back."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()
    store = PlateCalibrationStore(tmp_path / "store")
    _import(wdg, PLAN, tmp_path, monkeypatch)
    assert _calib(wizard.calibration()) == _calib(PLAN)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    wdg._delete_calibration()
    assert wizard.calibration() is None
    wizard.accept()  # nothing is calibrated, so nothing is sent
    assert store.load("96-well") is None
    assert wdg.platePlan() is None


def test_stage_map_asks_before_a_loaded_plan_replaces_the_stored_calibration(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded plan with another calibration asks before it replaces the stored."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()
    store = PlateCalibrationStore(tmp_path / "store")
    _import(wdg, PLAN, tmp_path, monkeypatch)
    loaded = useq.WellPlatePlan(
        plate="96-well",
        a1_center_xy=(10.0, 20.0),
        rotation=0.0,
        selected_wells=slice(0, 1),
    )
    plan_file = tmp_path / "loaded.json"
    plan_file.write_text(loaded.model_dump_json())
    ask = Mock(return_value=False)
    monkeypatch.setattr(wdg, "_ask_use_loaded_calibration", ask)

    # "Keep Stored": the wizard gets the stored calibration back
    wizard.load(str(plan_file))
    ask.assert_called_once()
    assert _calib(wdg.platePlan()) == _calib(PLAN)
    assert _calib(store.load("96-well")) == _calib(PLAN)
    assert _calib(wizard.calibration()) == _calib(PLAN)

    # "Use Loaded": the loaded calibration replaces the stored one
    ask.return_value = True
    wizard.load(str(plan_file))
    assert _calib(wdg.platePlan()) == _calib(loaded)
    assert _calib(store.load("96-well")) == _calib(loaded)

    # a calibration that the user makes in the wizard does not ask
    ask.reset_mock()
    fitted = useq.WellPlatePlan(plate="96-well", a1_center_xy=A1_XY, rotation=0.5)
    wizard.calibration_page.widget.setValue(fitted)
    wizard.accept()
    ask.assert_not_called()
    assert _calib(store.load("96-well")) == _calib(fitted)


def test_stage_map_does_not_push_while_calibrating_in_the_wizard(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """A map calibration does not discard work on the open calibration page."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()
    wizard.show()
    wizard.next()
    assert wizard.currentPage() is wizard.calibration_page
    wdg.setPlatePlan(PLAN)
    assert wizard.calibration() is None

    # on another page of the wizard, the map's calibration is applied
    wizard.back()
    moved = useq.WellPlatePlan(plate="96-well", a1_center_xy=(1.0, 2.0), rotation=0.0)
    wdg.setPlatePlan(moved)
    assert _calib(wizard.calibration()) == _calib(moved)


def test_stage_map_warns_if_the_store_cannot_be_written(
    qtbot: QtBot,
    global_mmcore: CMMCorePlus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A calibration store that cannot be written warns; the map still shows it."""
    wdg, mda = _map_with_mda(qtbot, global_mmcore, tmp_path)
    wizard = mda.stage_positions.hcsWizard()

    def _fail(plan: useq.WellPlatePlan) -> Path:
        raise OSError("read-only")

    monkeypatch.setattr(wdg._store, "save", _fail)
    with pytest.warns(UserWarning, match="Could not store"):
        wizard.setValue(PLAN)
    assert _calib(wdg.platePlan()) == _calib(PLAN)


def test_hcs_wizard_uses_the_core_of_its_table(qtbot: QtBot) -> None:
    """The HCS wizard of a position table drives the core of that table."""
    from pymmcore_plus import CMMCorePlus

    from pymmcore_widgets.mda._core_positions import CoreConnectedPositionTable

    core = CMMCorePlus()
    table = CoreConnectedPositionTable(mmcore=core)
    qtbot.addWidget(table)
    assert table.hcsWizard()._mmc is core


def test_stage_map_labels_fall_back_to_well(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """Unnamed positions are labelled with their well on the map."""
    wdg, table = _map_with_table(qtbot, global_mmcore, tmp_path)
    _set_positions(
        wdg,
        table,
        [
            useq.Position(
                x=A1_XY[0], y=A1_XY[1], name="ctrl", plate_row=0, plate_col=0
            ),
            useq.Position(x=A1_XY[0] + SPACING, y=A1_XY[1], plate_row=0, plate_col=1),
            useq.Position(x=0, y=0),
        ],
    )
    assert list(wdg._positions_overlay._labels.text) == ["ctrl", "A2", ""]


def test_stage_map_follows_palette(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """Canvas colors come from the widget palette, so the map follows the theme."""
    from qtpy.QtGui import QColor, QPalette

    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.setPlatePlan(PLAN)

    def canvas_bg() -> tuple[float, ...]:
        return tuple(wdg._stage_viewer.canvas.bgcolor.rgba[:3])

    palette = QPalette(wdg.palette())
    palette.setColor(QPalette.ColorRole.Window, QColor("#101820"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    wdg.setPalette(palette)
    assert canvas_bg() == pytest.approx((0x10 / 255, 0x18 / 255, 0x20 / 255), abs=0.01)
    # the plate is drawn in the (translucent) foreground color
    outline = wdg._plate_overlay._outline_color
    assert outline[:3] == pytest.approx((1.0, 1.0, 1.0))
    assert 0 < outline[3] < 1

    palette.setColor(QPalette.ColorRole.Window, QColor("#fafafa"))
    wdg.setPalette(palette)
    assert canvas_bg() == pytest.approx((0xFA / 255,) * 3, abs=0.01)


def test_zoom_to_fit_without_anything_to_fit(
    qtbot: QtBot, global_mmcore: CMMCorePlus, tmp_path: Path
) -> None:
    """With only the stage marker, the view frames a few fields of view."""
    wdg = StageMapWidget(mmcore=global_mmcore, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.show()
    global_mmcore.setXYPosition(0.0, 0.0)
    qtbot.waitUntil(
        lambda: global_mmcore.getXYPosition() == pytest.approx((0.0, 0.0), abs=1),
        timeout=10000,
    )
    wdg.timerEvent(None)

    fov = wdg._fov_size()
    assert fov is not None
    wdg.zoom_to_fit()
    rect = wdg._stage_viewer.view.camera.rect
    # centered on the stage, and not zoomed in onto the single field
    assert rect.left + rect.width / 2 == pytest.approx(0, abs=fov[0])
    assert rect.width >= fov[0] * 3


def test_stage_map_without_stage_device(qtbot: QtBot, tmp_path: Path) -> None:
    """A core with no devices at all must not break the widget."""
    from pymmcore_plus import CMMCorePlus
    from vispy.app.canvas import MouseEvent

    empty_core = CMMCorePlus()
    wdg = StageMapWidget(mmcore=empty_core, calibration_dir=tmp_path)
    qtbot.addWidget(wdg)
    wdg.show()

    wdg.timerEvent(None)
    assert "No XY stage device" in wdg._stage_pos_label.text()
    assert wdg._stage_controller is None
    assert wdg._fov_size() is None
    # clicking the map is a no-op rather than an error
    wdg._on_mouse_double_click(MouseEvent("mouse_double_click", pos=(10, 10), button=1))
    # ...and a plate can still be drawn
    wdg.setPlatePlan("96-well")
    assert wdg._plate_overlay._outlines.visible
    wdg.zoom_to_fit()
