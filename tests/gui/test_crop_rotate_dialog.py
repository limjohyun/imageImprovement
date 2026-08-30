"""Phase4-1(GUI-3 일부) 수용 기준 검증: `CropRotateDialog` 숫자 입력 다이얼로그.

마우스 드래그 대신 스핀박스/콤보박스 숫자 입력 방식이므로 pytest-qt로 값 설정과
버튼 클릭만으로 검증할 수 있다.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from app.gui.crop_rotate_dialog import CropRotateDialog


def test_default_crop_is_full_frame(qtbot):
    dialog = CropRotateDialog(400, 300)
    qtbot.addWidget(dialog)

    assert dialog.rotation_degrees() == 0
    assert dialog.crop_rect() == (0, 0, 400, 300)


def test_rotation_90_swaps_effective_bounds(qtbot):
    dialog = CropRotateDialog(400, 300)
    qtbot.addWidget(dialog)

    dialog.rotation_combo.setCurrentIndex(dialog.rotation_combo.findData(90))

    assert dialog.crop_rect() == (0, 0, 300, 400)
    assert dialog.width_spin.maximum() == 300
    assert dialog.height_spin.maximum() == 400


def test_initial_values_are_restored(qtbot):
    dialog = CropRotateDialog(
        400, 300, initial_rotation_degrees=180, initial_crop_rect=(10, 20, 100, 50)
    )
    qtbot.addWidget(dialog)

    assert dialog.rotation_degrees() == 180
    assert dialog.crop_rect() == (10, 20, 100, 50)


def test_accept_rejects_out_of_bounds_combination(qtbot, monkeypatch):
    """x+width가 개별 스핀박스 범위 안이어도 합쳐서 초과하면 다이얼로그가 닫히지 않아야 한다."""
    dialog = CropRotateDialog(100, 100)
    qtbot.addWidget(dialog)

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.gui.crop_rotate_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[-1]) or None,
    )

    dialog.x_spin.setValue(90)
    dialog.width_spin.setValue(50)  # 90 + 50 = 140 > 100

    dialog.accept()

    assert warnings, "범위 초과 조합에는 경고가 떠야 한다."
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_accept_succeeds_for_valid_combination(qtbot):
    dialog = CropRotateDialog(100, 100)
    qtbot.addWidget(dialog)

    dialog.x_spin.setValue(10)
    dialog.width_spin.setValue(50)
    dialog.y_spin.setValue(5)
    dialog.height_spin.setValue(60)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.crop_rect() == (10, 5, 50, 60)
