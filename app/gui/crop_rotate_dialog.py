"""Phase4-1(GUI-3 일부): 자르기/회전 등 기본 보정을 위한 숫자 입력 다이얼로그.

마우스 드래그로 영역을 인터랙티브하게 선택하는 대신, x/y/width/height 스핀박스와
회전 콤보박스로 값을 직접 입력받는 방식을 택했다(사용자와 합의된 설계 방향).
구현이 단순하고 pytest-qt로 자동화 테스트하기 쉬우며, 개인용 도구 규모에
적합하기 때문이다.

자르기 좌표는 `app.preprocess.manual_correction.apply_manual_correction`과 동일한
순서(회전 먼저 → 자르기)를 가정한 "회전 후 이미지" 크기를 기준으로 한다. 회전
콤보박스를 바꾸면 유효 너비/높이가 뒤바뀔 수 있으므로, 그때마다 자르기 값을
전체 프레임으로 초기화한다 — 이전 회전에서 입력한 값을 새 좌표계로 변환해
유지하는 것은 이번 범위(무한 실행취소/좌표 변환 로직 없이 단순하게) 밖이다.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

_ROTATION_CHOICES = (0, 90, 180, 270)


class CropRotateDialog(QDialog):
    """회전(90도 단위)과 자르기(x/y/width/height) 값을 입력받는 다이얼로그."""

    def __init__(
        self,
        original_width: int,
        original_height: int,
        *,
        initial_rotation_degrees: int = 0,
        initial_crop_rect: tuple[int, int, int, int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("자르기 / 회전")
        self._original_width = original_width
        self._original_height = original_height

        self.rotation_combo = QComboBox()
        for degrees in _ROTATION_CHOICES:
            self.rotation_combo.addItem(f"{degrees}°", degrees)
        index = self.rotation_combo.findData(initial_rotation_degrees)
        self.rotation_combo.setCurrentIndex(index if index >= 0 else 0)
        self.rotation_combo.currentIndexChanged.connect(self._on_rotation_changed)

        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        self.width_spin.setMinimum(1)
        self.height_spin.setMinimum(1)

        form = QFormLayout()
        form.addRow("회전", self.rotation_combo)
        form.addRow("자르기 X", self.x_spin)
        form.addRow("자르기 Y", self.y_spin)
        form.addRow("자르기 너비", self.width_spin)
        form.addRow("자르기 높이", self.height_spin)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.button_box)

        # 회전이 초기값과 다르게 복원됐다면(예: 이전에 90도 회전 후 저장된 결과를
        # 다시 열었을 때), initial_crop_rect는 이미 그 회전 기준 좌표계이므로
        # 그대로 사용해도 된다 — 최초 오픈 시에만 해당하는 경로다.
        self._apply_bounds_for_current_rotation(initial_crop_rect)

    def _effective_dimensions(self) -> tuple[int, int]:
        """현재 선택된 회전을 적용했을 때의 (너비, 높이)."""
        if self.rotation_combo.currentData() in (90, 270):
            return self._original_height, self._original_width
        return self._original_width, self._original_height

    def _on_rotation_changed(self) -> None:
        self._apply_bounds_for_current_rotation(None)

    def _apply_bounds_for_current_rotation(
        self, crop_rect: tuple[int, int, int, int] | None
    ) -> None:
        effective_width, effective_height = self._effective_dimensions()
        self.x_spin.setRange(0, max(effective_width - 1, 0))
        self.y_spin.setRange(0, max(effective_height - 1, 0))
        self.width_spin.setRange(1, max(effective_width, 1))
        self.height_spin.setRange(1, max(effective_height, 1))

        x, y, width, height = (
            crop_rect if crop_rect is not None else (0, 0, effective_width, effective_height)
        )
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)

    def rotation_degrees(self) -> int:
        return self.rotation_combo.currentData()

    def crop_rect(self) -> tuple[int, int, int, int]:
        return (
            self.x_spin.value(),
            self.y_spin.value(),
            self.width_spin.value(),
            self.height_spin.value(),
        )

    def accept(self) -> None:
        """OK를 눌렀을 때 x+width/y+height가 회전 후 이미지 범위를 넘지 않는지 최종 검증한다.

        스핀박스 각각의 범위(`setRange`)만으로는 x와 width를 조합했을 때의 초과를
        막을 수 없다(예: 너비 100인 이미지에서 x=99, width=100은 각각 유효 범위
        안이지만 더하면 범위를 넘는다) — 여기서 조합을 한 번 더 검증한다.
        """
        effective_width, effective_height = self._effective_dimensions()
        x, y, width, height = self.crop_rect()
        if x + width > effective_width or y + height > effective_height:
            QMessageBox.warning(
                self,
                "잘못된 자르기 영역",
                "자르기 영역이 이미지 범위를 벗어납니다 "
                f"(회전 후 이미지 크기: {effective_width}x{effective_height}).",
            )
            return
        super().accept()
