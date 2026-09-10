"""اختبارات حزمة التقييم القابلة للتصدير — تحويل المعرفة إلى منتج."""

from __future__ import annotations

from shared.research.exportable_eval import example_bundle


class TestExportableBundle:
    def test_example_bundle_builds(self) -> None:
        bundle = example_bundle()
        assert bundle.total_tasks == 3
        assert bundle.calibrated_tasks == 3
        assert bundle.version == "1.0.0"
        assert bundle.cdkc_version == "1.0.0"

    def test_bundle_has_dangerous(self) -> None:
        bundle = example_bundle()
        assert bundle.dangerous_count >= 1

    def test_bundle_coverage(self) -> None:
        bundle = example_bundle()
        assert "continuity" in bundle.concept_coverage
        assert len(bundle.language_coverage) >= 1

    def test_bundle_limitations_declared(self) -> None:
        """بيان الحدود يُكتب أولاً — لا يُباع بلا حدود معلنة."""
        bundle = example_bundle()
        assert len(bundle.limitations) >= 3
        assert any("TIMEOUT" in lim or "تحقق" in lim or "لغة" in lim for lim in bundle.limitations)

    def test_bundle_commercial_note_is_proposed(self) -> None:
        bundle = example_bundle()
        assert "PROPOSED" in bundle.commercial_note
        assert "PRICING HYPOTHESIS" in bundle.commercial_note

    def test_bundle_not_mature_yet(self) -> None:
        """حزمة المثال 3 مهام فقط — غير ناضجة للبيع، وهذا مقصود."""
        bundle = example_bundle()
        assert bundle.is_mature is False
        assert bundle.avg_cdkc is not None
