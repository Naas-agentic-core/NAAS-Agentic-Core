# tests/services/overmind/art/test_generators.py
"""
Tests for CS73 Art Generators Module
"""

from microservices.orchestrator_service.src.services.overmind.art.generators import (
    CodePatternArtist,
    MetricsArtist,
    NetworkArtist,
)
from microservices.orchestrator_service.src.services.overmind.art.styles import ArtStyle


class TestCodePatternArtist:
    """Test CodePatternArtist class"""

    def test_init(self):
        """Test initialization"""
        artist = CodePatternArtist(ArtStyle.CYBERPUNK)
        assert artist.style == ArtStyle.CYBERPUNK

    def test_generate_fractal_tree_basic(self):
        """Test generating a basic fractal tree"""
        artist = CodePatternArtist()

        svg = artist.generate_fractal_tree(complexity=3)

        assert svg.startswith("<svg")
        assert "</svg>" in svg
        assert "Fractal Code Tree" in svg

    def test_generate_fractal_tree_with_seed(self):
        """Test fractal tree with seed for reproducibility"""
        artist = CodePatternArtist(ArtStyle.NATURE)

        svg1 = artist.generate_fractal_tree(complexity=4, seed=42)
        svg2 = artist.generate_fractal_tree(complexity=4, seed=42)

        # Should be identical with same seed
        assert svg1 == svg2

    def test_generate_fractal_tree_different_complexity(self):
        """Test fractal trees with different complexity"""
        artist = CodePatternArtist()

        simple = artist.generate_fractal_tree(complexity=2)
        complex = artist.generate_fractal_tree(complexity=5)

        # More complex should have more content
        assert len(complex) > len(simple)

    def test_generate_spiral_code(self):
        """Test generating spiral code"""
        artist = CodePatternArtist(ArtStyle.GRADIENT)

        svg = artist.generate_spiral_code(iterations=50, data_seed=42)

        assert svg.startswith("<svg")
        assert "Code Evolution Spiral" in svg


class TestMetricsArtist:
    """Test MetricsArtist class"""

    def test_init(self):
        """Test initialization"""
        artist = MetricsArtist(ArtStyle.NATURE)
        assert artist.style == ArtStyle.NATURE

    def test_create_radial_chart_empty(self):
        """Test radial chart with no metrics"""
        artist = MetricsArtist()

        svg = artist.create_radial_chart({})

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_create_radial_chart_with_metrics(self):
        """Test radial chart with metrics"""
        artist = MetricsArtist(ArtStyle.MODERN)

        metrics = {"performance": 8.5, "quality": 9.0, "maintainability": 7.8}

        svg = artist.create_radial_chart(metrics, title="Test Metrics")

        assert "Test Metrics" in svg
        assert "performance" in svg
        assert "8.5" in svg

    def test_create_bar_art_empty(self):
        """Test bar art with no data"""
        artist = MetricsArtist()

        svg = artist.create_bar_art({})

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_create_bar_art_with_data(self):
        """Test bar art with data"""
        artist = MetricsArtist(ArtStyle.CYBERPUNK)

        data = {"metric1": 5.0, "metric2": 8.5, "metric3": 3.2}

        svg = artist.create_bar_art(data, title="Bar Chart")

        assert "Bar Chart" in svg
        assert "metric1" in svg
        assert "5.0" in svg


class TestNetworkArtist:
    """Test NetworkArtist class"""

    def test_init(self):
        """Test initialization"""
        artist = NetworkArtist(ArtStyle.DARK)
        assert artist.style == ArtStyle.DARK

    def test_create_dependency_web_empty(self):
        """Test dependency web with no nodes"""
        artist = NetworkArtist()

        svg = artist.create_dependency_web(nodes=[], edges=[])

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_create_dependency_web_with_nodes(self):
        """Test dependency web with nodes"""
        artist = NetworkArtist(ArtStyle.RETRO)

        nodes = [
            {"id": "auth", "label": "Auth"},
            {"id": "users", "label": "Users"},
            {"id": "db", "label": "Database"},
        ]

        edges = [("users", "auth"), ("users", "db")]

        svg = artist.create_dependency_web(nodes, edges, title="Dependencies")

        assert "Dependencies" in svg
        assert "Auth" in svg
        assert "Users" in svg
        assert "Database" in svg

    def test_create_dependency_web_with_invalid_edges(self):
        """Test dependency web with edges referencing non-existent nodes"""
        artist = NetworkArtist()

        nodes = [{"id": "node1", "label": "Node 1"}]

        edges = [("node1", "non_existent"), ("another_missing", "node1")]

        # Should not crash, just skip invalid edges
        svg = artist.create_dependency_web(nodes, edges)

        assert svg.startswith("<svg")
        assert "Node 1" in svg
