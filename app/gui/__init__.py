"""app.gui: PySide6 기반 최소 GUI (Phase1-5, GUI-1/2/4).

`python -m app.gui`로 실행할 수 있는 진입점(`main()`)을 제공한다. 실제 구현은
`main_window.py`(위젯 구성)와 `worker.py`(QThread 기반 백그라운드 파이프라인)에 있다.
"""

from __future__ import annotations

import sys


def main() -> int:
    """메인 윈도우를 띄우고 Qt 이벤트 루프를 실행한다."""
    from PySide6.QtWidgets import QApplication

    from app.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
