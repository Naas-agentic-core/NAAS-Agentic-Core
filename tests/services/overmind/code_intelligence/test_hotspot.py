from microservices.orchestrator_service.src.services.overmind.code_intelligence.analyzers.hotspot import HotspotAnalyzer
from microservices.orchestrator_service.src.services.overmind.code_intelligence.models import FileMetrics


class TestHotspotAnalyzer:
    def setup_method(self):
        self.analyzer = HotspotAnalyzer()

    def create_metrics(self, path, complexity, commits, god_class=False):
        return FileMetrics(
            file_path=path,
            relative_path=path,
            file_complexity=complexity,
            commits_last_12months=commits,
            is_god_class=god_class,
        )

    def test_calculate_hotspot_scores(self):
        m1 = self.create_metrics("file1.py", 100, 50, True)  # High everything
        m2 = self.create_metrics("file2.py", 10, 5, False)  # Low everything

        metrics_list = [m1, m2]
        self.analyzer.calculate_hotspot_scores(metrics_list)

        assert m1.hotspot_score == 1.0
        assert m1.priority_tier == "CRITICAL"
        assert m2.hotspot_score == 0.08
        assert m2.priority_tier == "LOW"

    def test_calculate_and_sort_hotspots(self):
        m1 = self.create_metrics("low.py", 10, 5, False)
        m2 = self.create_metrics("high.py", 100, 50, True)

        metrics = [m1, m2]
        self.analyzer.calculate_and_sort_hotspots(metrics)

        assert metrics[0].relative_path == "high.py"
        assert metrics[1].relative_path == "low.py"

    def test_identify_hotspots(self):
        metrics = []
        for i in range(25):
            metrics.append(self.create_metrics(f"file_{i}.py", 100 - i, 100 - i, False))

        hotspots = self.analyzer.identify_hotspots(metrics)

        assert len(hotspots.critical) == 20
        assert len(hotspots.high) == 5
