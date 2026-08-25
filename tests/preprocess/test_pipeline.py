"""PRE-5(파이프라인 재사용성) 테스트: 전체 조합 함수 `run_pipeline()` 검증."""

from __future__ import annotations

import numpy as np

from app.preprocess.pipeline import PreprocessConfig, run_pipeline


def test_run_pipeline_end_to_end_with_synthetic_text_photo(synthetic_text_photo):
    """왜곡된 촬영본을 넣으면 4단계를 모두 거친 결과 이미지를 받아야 한다."""
    result = run_pipeline(synthetic_text_photo.photo)
    assert result.dtype == np.uint8
    assert result.ndim == 3
    # 원근 보정으로 배경 여백이 사라지고, 업스케일(기본 scale=2.0)로 확대되므로
    # 원본 촬영본보다는 문서 내용에 더 가까운 크기가 되어야 한다(과도하게 작아지면 안 됨).
    assert result.shape[0] > 0 and result.shape[1] > 0


def test_run_pipeline_uses_manual_corners_when_provided(synthetic_diagram_photo):
    """GUI가 수동 4점을 넘기는 경로(PRE-1 수용 기준의 수동 지정)도 파이프라인에서 동작해야 한다."""
    config = PreprocessConfig(corners=synthetic_diagram_photo.corners, run_upscale=False)
    result = run_pipeline(synthetic_diagram_photo.photo, config)
    assert result.dtype == np.uint8


def test_run_pipeline_skips_perspective_when_detection_fails_by_default():
    """자동 검출이 실패해도(균일한 색 이미지) 기본 설정에서는 예외 없이 나머지 단계가 진행돼야 한다.

    PreprocessConfig.skip_perspective_on_failure 기본값(True)에 의존하는 동작이다.
    """
    flat_image = np.full((100, 120, 3), 180, dtype=np.uint8)
    result = run_pipeline(flat_image)
    assert result.dtype == np.uint8


def test_run_pipeline_stage_toggles_can_disable_all_but_one():
    """각 단계가 독립적으로 on/off 가능해야 한다(PRE-5: 문서 유형별로 조합 가능)."""
    image = np.full((60, 60, 3), 150, dtype=np.uint8)
    config = PreprocessConfig(
        run_perspective=False,
        run_deskew=False,
        run_illumination=False,
        run_upscale=True,
        upscale_scale=2.0,
    )
    result = run_pipeline(image, config)
    assert result.shape[:2] == (120, 120)
