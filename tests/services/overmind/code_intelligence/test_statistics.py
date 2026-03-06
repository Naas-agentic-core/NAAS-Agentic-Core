from microservices.orchestrator_service.src.services.overmind.code_intelligence.analyzers.statistics import StatisticsAnalyzer


class TestStatisticsAnalyzer:
    def setup_method(self):
        self.analyzer = StatisticsAnalyzer()

    def test_count_lines(self):
        lines = ["import os", "", "# comment", "  # indented comment", "def main():", "    pass"]
        stats = self.analyzer.count_lines(lines)
        assert stats.code_lines == 3
        assert stats.comment_lines == 2
        assert stats.blank_lines == 1

    def test_calculate_complexity_stats_empty(self):
        stats = self.analyzer.calculate_complexity_stats([])
        assert stats.avg_complexity == 0.0
        assert stats.max_complexity == 0

    def test_calculate_complexity_stats(self):
        functions = [
            {"name": "func1", "complexity": 5, "nesting_depth": 1},
            {"name": "func2", "complexity": 15, "nesting_depth": 3},
            {"name": "func3", "complexity": 10, "nesting_depth": 2},
        ]
        stats = self.analyzer.calculate_complexity_stats(functions)

        assert stats.avg_complexity == 10.0
        assert stats.max_complexity == 15
        assert stats.max_func_name == "func2"
        assert stats.avg_nesting == 2.0
        assert 4.0 < stats.std_dev < 4.1
