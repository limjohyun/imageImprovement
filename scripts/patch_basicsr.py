"""basicsr의 torchvision 호환성 패치 스크립트.

최신 torchvision(0.17+)에서 `torchvision.transforms.functional_tensor` 모듈이
삭제되어 basicsr==1.4.2의 `degradations.py`가 import 시점에 깨진다.
venv를 재생성하면 이 패치도 함께 사라지므로, 재생성 후 이 스크립트를 다시 실행한다.

사용법: .venv/bin/python scripts/patch_basicsr.py
"""

from __future__ import annotations

import logging
import sysconfig
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OLD_IMPORT = "from torchvision.transforms.functional_tensor import rgb_to_grayscale"
NEW_IMPORT = "from torchvision.transforms.functional import rgb_to_grayscale"


def patch_degradations_file() -> None:
    """basicsr/data/degradations.py의 손상된 import 구문을 한 줄 치환한다."""
    site_packages = Path(sysconfig.get_paths()["purelib"])
    target = site_packages / "basicsr" / "data" / "degradations.py"

    if not target.exists():
        raise FileNotFoundError(f"basicsr가 설치되어 있지 않습니다: {target}")

    text = target.read_text(encoding="utf-8")

    if NEW_IMPORT in text:
        logger.info("이미 패치가 적용되어 있습니다: %s", target)
        return

    if OLD_IMPORT not in text:
        logger.warning("예상한 import 구문을 찾지 못했습니다. 수동 확인이 필요합니다: %s", target)
        return

    target.write_text(text.replace(OLD_IMPORT, NEW_IMPORT), encoding="utf-8")
    logger.info("패치 완료: %s", target)


if __name__ == "__main__":
    patch_degradations_file()
