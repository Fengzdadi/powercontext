"""Unit tests for coverage judgment logic."""
from examradar.coverage import _compute_coverage_score, _judge_level, _normalize_kw


class TestNormalizeKw:
    def test_zero(self):
        assert _normalize_kw(0.0, 10.0) == 0.0

    def test_none(self):
        assert _normalize_kw(None, 10.0) == 0.0

    def test_half_scale(self):
        assert _normalize_kw(5.0, 10.0) == 0.5

    def test_at_scale(self):
        assert _normalize_kw(10.0, 10.0) == 1.0

    def test_above_scale_capped(self):
        assert _normalize_kw(20.0, 10.0) == 1.0


class TestComputeCoverageScore:
    def test_both_zero(self):
        score = _compute_coverage_score(0.0, 0.0, 10.0)
        assert score == 0.0

    def test_semantic_only(self):
        score = _compute_coverage_score(1.0, 0.0, 10.0)
        assert abs(score - 0.6) < 0.001

    def test_keyword_only(self):
        score = _compute_coverage_score(0.0, 10.0, 10.0)
        assert abs(score - 0.4) < 0.001

    def test_both_high(self):
        score = _compute_coverage_score(0.8, 10.0, 10.0)
        assert abs(score - (0.6 * 0.8 + 0.4 * 1.0)) < 0.001

    def test_none_scores(self):
        score = _compute_coverage_score(None, None, 10.0)
        assert score == 0.0


class TestJudgeLevel:
    def test_covered(self):
        assert _judge_level(0.60) == "covered"

    def test_thin(self):
        assert _judge_level(0.30) == "thin"

    def test_missing(self):
        assert _judge_level(0.10) == "missing"

    def test_boundary_covered(self):
        assert _judge_level(0.55) == "covered"

    def test_boundary_thin(self):
        assert _judge_level(0.20) == "thin"

    def test_just_below_covered(self):
        assert _judge_level(0.54) == "thin"

    def test_just_below_thin(self):
        assert _judge_level(0.19) == "missing"
