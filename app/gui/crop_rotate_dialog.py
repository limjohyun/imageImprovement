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

PRE-1(GUI 수동 코너 오버라이드): `PerspectiveCorrectionDialog`도 같은 이유(숫자
입력, 드래그 금지)로 같은 파일에 둔다 — 좌상/우상/우하/좌하 4점 각각 (x, y)
스핀박스 8개로 `app.preprocess.perspective.correct_perspective(image,
corners=...)`가 기대하는 (4, 2) 좌표 배열을 입력받는다.
"""

from __future__ import annotations

import numpy as np
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


class PerspectiveCorrectionDialog(QDialog):
    """PRE-1: 원근 보정 4모서리 좌표를 사용자가 직접 입력하는 다이얼로그.

    자동 검출(`detect_document_corners`)이 실패했을 때(가장 흔한 실제 케이스 —
    배경 없이 프레임을 꽉 채운 사진) 또는 자동 검출 결과가 마음에 들지 않을 때
    쓴다. `CropRotateDialog`와 동일하게 마우스 드래그 대신 스핀박스로 좌표를
    입력받는다.

    좌표계는 호출부가 넘긴 `image_width`/`image_height` 기준이다 — 자르기/회전이
    이미 적용된 이미지(`apply_manual_correction`을 거친 결과)를 기준으로 좌표를
    받아야 하므로, 어떤 이미지를 기준으로 할지는 호출부(`MainWindow`)가 결정한다.
    """

    _CORNER_LABELS = ("좌상단", "우상단", "우하단", "좌하단")
    """`app.preprocess.perspective.warp_to_corners`가 기대하는 (좌상, 우상, 우하,
    좌하) 순서와 반드시 일치해야 한다."""

    def __init__(
        self,
        image_width: int,
        image_height: int,
        *,
        initial_corners: np.ndarray | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("원근 보정 (모서리 직접 지정)")
        self._image_width = image_width
        self._image_height = image_height

        if initial_corners is None:
            # 자동 검출도 실패하고 이전에 지정한 값도 없으면, 사용자가 처음부터
            # 다시 입력하지 않고 조정만 하면 되도록 이미지 네 귀퉁이를 기본값으로 채운다.
            initial_corners = np.array(
                [
                    [0, 0],
                    [image_width - 1, 0],
                    [image_width - 1, image_height - 1],
                    [0, image_height - 1],
                ],
                dtype=np.float32,
            )

        form = QFormLayout()
        self._x_spins: list[QSpinBox] = []
        self._y_spins: list[QSpinBox] = []
        for label, (x, y) in zip(self._CORNER_LABELS, initial_corners, strict=True):
            x_spin = QSpinBox()
            x_spin.setRange(0, max(image_width - 1, 0))
            x_spin.setValue(int(round(float(x))))
            y_spin = QSpinBox()
            y_spin.setRange(0, max(image_height - 1, 0))
            y_spin.setValue(int(round(float(y))))
            form.addRow(f"{label} X", x_spin)
            form.addRow(f"{label} Y", y_spin)
            self._x_spins.append(x_spin)
            self._y_spins.append(y_spin)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.button_box)

    def corners(self) -> np.ndarray:
        """(좌상, 우상, 우하, 좌하) 순서의 (4, 2) float32 좌표 배열.

        각 스핀박스가 이미 `0 <= 값 < 이미지 크기` 범위로 제한돼 있으므로 여기서
        추가로 검증하지 않는다 — 4점이 정확히 볼록사각형을 이루는지까지는 검증하지
        않지만, shape이 항상 (4, 2)라는 최소 방어는 `warp_to_corners`가 이미
        `ValueError`로 보장한다.
        """
        return np.array(
            [[x_spin.value(), y_spin.value()] for x_spin, y_spin in zip(
                self._x_spins, self._y_spins, strict=True
            )],
            dtype=np.float32,
        )
