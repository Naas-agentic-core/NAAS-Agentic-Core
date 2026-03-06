# tests/services/overmind/art/test_integration.py
"""
Tests for CS73 Art Integration Module
"""

from microservices.orchestrator_service.src.services.overmind.art.integration import (
    OvermindArtIntegration,
    create_art_from_overmind_data,
)
from microservices.orchestrator_service.src.services.overmind.art.styles import ArtStyle


class TestOvermindArtIntegration:
    """Test OvermindArtIntegration class"""

    def test_init_default(self):
        """Test initialization with default style"""
        integration = OvermindArtIntegration()
        assert integration.default_style == ArtStyle.MODERN

    def test_init_custom_style(self):
        """Test initialization with custom style"""
        integration = OvermindArtIntegration(ArtStyle.CYBERPUNK)
        assert integration.default_style == ArtStyle.CYBERPUNK

    def test_visualize_code_intelligence(self):
        """Test visualizing code intelligence"""
        integration = OvermindArtIntegration()

        analysis_result = {
            "avg_complexity": 5.2,
            "max_complexity": 15,
            "functions": 42,
            "classes": 12,
            "lines": 1500,
        }

        visualizations = integration.visualize_code_intelligence(analysis_result)

        # Should have multiple visualizations
        assert "complexity_art" in visualizations
        assert "metrics_dashboard" in visualizations
        assert "pattern_art" in visualizations
        assert "fractal_tree" in visualizations

        # Check they're SVG/HTML
        assert visualizations["complexity_art"].startswith("<svg")
        assert "<div" in visualizations["metrics_dashboard"]

    def test_visualize_mission_journey(self):
        """Test visualizing mission journey"""
        integration = OvermindArtIntegration(ArtStyle.NATURE)

        mission_data = {
            "id": 123,
            "events": [
                {"name": "Start", "type": "start"},
                {"name": "Planning", "type": "info"},
                {"name": "Success", "type": "success"},
            ],
        }

        visualizations = integration.visualize_mission_journey(mission_data)

        assert "timeline" in visualizations
        assert "evolution_spiral" in visualizations

        assert "Start" in visualizations["timeline"]
        assert visualizations["evolution_spiral"].startswith("<svg")

    def test_visualize_metrics_default(self):
        """Test visualizing metrics with defaults"""
        integration = OvermindArtIntegration()

        metrics = {"performance": 8.5, "quality": 9.0, "maintainability": 7.8}

        visualizations = integration.visualize_metrics(metrics)

        # Should have all default types
        assert "radial_chart" in visualizations
        assert "bar_chart" in visualizations
        assert "data_sculpture" in visualizations

    def test_visualize_metrics_custom_types(self):
        """Test visualizing metrics with custom types"""
        integration = OvermindArtIntegration()

        metrics = {"metric1": 5.0}

        visualizations = integration.visualize_metrics(metrics, visualization_types=["radial"])

        assert "radial_chart" in visualizations
        assert "bar_chart" not in visualizations
        assert "data_sculpture" not in visualizations

    def test_visualize_dependencies(self):
        """Test visualizing dependencies"""
        integration = OvermindArtIntegration(ArtStyle.DARK)

        modules = ["auth", "users", "database"]
        dependencies = [("users", "auth"), ("users", "database")]

        svg = integration.visualize_dependencies(modules, dependencies)

        assert svg.startswith("<svg")
        assert "auth" in svg
        assert "users" in svg
        assert "database" in svg

    def test_create_full_report(self):
        """Test creating a full report"""
        integration = OvermindArtIntegration()

        analysis_data = {
            "code_analysis": {"avg_complexity": 5.2, "functions": 42},
            "mission_data": {"id": 123, "events": [{"name": "Start", "type": "start"}]},
            "metrics": {"performance": 8.5},
            "dependencies": {"modules": ["module1", "module2"], "edges": [("module1", "module2")]},
        }

        report = integration.create_full_report(analysis_data)

        # Check report structure
        assert "style" in report
        assert "visualizations" in report

        # Check all sections are present
        assert "code_intelligence" in report["visualizations"]
        assert "mission_journey" in report["visualizations"]
        assert "metrics" in report["visualizations"]
        assert "dependencies" in report["visualizations"]


class TestCreateArtFromOvermindData:
    """Test create_art_from_overmind_data helper function"""

    def test_create_art_basic(self):
        """Test creating art with basic data"""
        overmind_data = {"code_analysis": {"avg_complexity": 3.0, "functions": 10}}

        result = create_art_from_overmind_data(overmind_data)

        assert "visualizations" in result
        assert "code_intelligence" in result["visualizations"]

    def test_create_art_with_style(self):
        """Test creating art with custom style"""
        overmind_data = {"metrics": {"quality": 9.0}}

        result = create_art_from_overmind_data(overmind_data, style=ArtStyle.CYBERPUNK)

        assert result["style"] == "cyberpunk"
