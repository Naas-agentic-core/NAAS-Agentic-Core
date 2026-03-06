# tests/services/overmind/art/test_visualizer.py
"""
Tests for CS73 Art Visualizer Module
"""

from microservices.orchestrator_service.src.services.overmind.art.styles import ArtStyle
from microservices.orchestrator_service.src.services.overmind.art.visualizer import (
    CodeArtVisualizer,
    DataArtGenerator,
    MissionFlowArtist,
)


class TestCodeArtVisualizer:
    """Test CodeArtVisualizer class"""

    def test_init_with_default_style(self):
        """Test initialization with default style"""
        visualizer = CodeArtVisualizer()
        assert visualizer.style == ArtStyle.MINIMALIST

    def test_init_with_custom_style(self):
        """Test initialization with custom style"""
        visualizer = CodeArtVisualizer(ArtStyle.CYBERPUNK)
        assert visualizer.style == ArtStyle.CYBERPUNK

    def test_create_complexity_art(self):
        """Test creating complexity art"""
        visualizer = CodeArtVisualizer(ArtStyle.MODERN)

        complexity_data = {"avg_complexity": 5.2, "max_complexity": 15, "functions": 42}

        svg = visualizer.create_complexity_art(complexity_data)

        # Check it's SVG
        assert svg.startswith("<svg")
        assert "</svg>" in svg

        # Check it contains data
        assert "42" in svg  # functions count
        assert "5.2" in svg or "5" in svg  # avg complexity

    def test_create_complexity_art_with_title(self):
        """Test complexity art with custom title"""
        visualizer = CodeArtVisualizer()

        svg = visualizer.create_complexity_art(
            {"avg_complexity": 3.0, "max_complexity": 10, "functions": 20}, title="My Custom Title"
        )

        assert "My Custom Title" in svg

    def test_create_metrics_dashboard(self):
        """Test creating metrics dashboard"""
        visualizer = CodeArtVisualizer(ArtStyle.NATURE)

        metrics = {"lines": 1500, "classes": 12, "functions": 42, "complexity": 5.2}

        html = visualizer.create_metrics_dashboard(metrics)

        # Check it's HTML
        assert "<div" in html
        assert "</div>" in html

        # Check it contains metrics
        assert "1500" in html
        assert "12" in html
        assert "42" in html


class TestMissionFlowArtist:
    """Test MissionFlowArtist class"""

    def test_init(self):
        """Test initialization"""
        artist = MissionFlowArtist(ArtStyle.CYBERPUNK)
        assert artist.style == ArtStyle.CYBERPUNK

    def test_create_mission_timeline_empty(self):
        """Test timeline with no events"""
        artist = MissionFlowArtist()

        svg = artist.create_mission_timeline({"events": []})

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_create_mission_timeline_with_events(self):
        """Test timeline with events"""
        artist = MissionFlowArtist(ArtStyle.MODERN)

        mission_data = {
            "events": [
                {"name": "Start", "type": "start"},
                {"name": "Planning", "type": "info"},
                {"name": "Success", "type": "success"},
            ]
        }

        svg = artist.create_mission_timeline(mission_data)

        assert "Start" in svg
        assert "Planning" in svg
        assert "Success" in svg


class TestDataArtGenerator:
    """Test DataArtGenerator class"""

    def test_init(self):
        """Test initialization"""
        generator = DataArtGenerator(ArtStyle.GRADIENT)
        assert generator.style == ArtStyle.GRADIENT

    def test_generate_code_pattern(self):
        """Test generating code pattern"""
        generator = DataArtGenerator()

        code_data = {"functions": 42, "classes": 12, "lines": 1500}

        svg = generator.generate_code_pattern(code_data, size=(400, 400))

        assert svg.startswith("<svg")
        assert 'width="400"' in svg
        assert 'height="400"' in svg

    def test_create_data_sculpture_empty(self):
        """Test data sculpture with empty data"""
        generator = DataArtGenerator()

        svg = generator.create_data_sculpture({})

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_create_data_sculpture_with_data(self):
        """Test data sculpture with data"""
        generator = DataArtGenerator(ArtStyle.DARK)

        data = {"performance": 8.5, "quality": 9.0, "maintainability": 7.8}

        svg = generator.create_data_sculpture(data, title="Test Sculpture")

        assert "Test Sculpture" in svg
        assert "performance" in svg
        assert "8.5" in svg or "8.50" in svg
