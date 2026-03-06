# tests/services/overmind/art/test_styles.py
"""
Tests for CS73 Art Styles Module
"""

from microservices.orchestrator_service.src.services.overmind.art.styles import (
    ArtStyle,
    ColorPalette,
    VisualTheme,
)


class TestColorPalette:
    """Test ColorPalette NamedTuple"""

    def test_color_palette_creation(self):
        """Test creating a color palette"""
        palette = ColorPalette(
            primary="#000000",
            secondary="#FFFFFF",
            accent="#FF0000",
            background="#CCCCCC",
            text="#111111",
            success="#00FF00",
            warning="#FFFF00",
            error="#FF0000",
            info="#0000FF",
        )

        assert palette.primary == "#000000"
        assert palette.secondary == "#FFFFFF"
        assert palette.accent == "#FF0000"


class TestArtStyle:
    """Test ArtStyle Enum"""

    def test_art_style_values(self):
        """Test all art style values exist"""
        assert ArtStyle.MINIMALIST.value == "minimalist"
        assert ArtStyle.CYBERPUNK.value == "cyberpunk"
        assert ArtStyle.NATURE.value == "nature"
        assert ArtStyle.RETRO.value == "retro"
        assert ArtStyle.MODERN.value == "modern"
        assert ArtStyle.DARK.value == "dark"
        assert ArtStyle.LIGHT.value == "light"
        assert ArtStyle.GRADIENT.value == "gradient"


class TestVisualTheme:
    """Test VisualTheme class"""

    def test_get_palette_minimalist(self):
        """Test getting minimalist palette"""
        palette = VisualTheme.get_palette(ArtStyle.MINIMALIST)

        assert isinstance(palette, ColorPalette)
        assert palette.primary == "#2C3E50"
        assert palette.background == "#FFFFFF"

    def test_get_palette_cyberpunk(self):
        """Test getting cyberpunk palette"""
        palette = VisualTheme.get_palette(ArtStyle.CYBERPUNK)

        assert palette.primary == "#00FF41"
        assert palette.background == "#0D1B2A"

    def test_create_gradient_basic(self):
        """Test creating a basic gradient"""
        gradient = VisualTheme.create_gradient("#FF0000", "#0000FF", steps=5)

        assert len(gradient) == 5
        assert gradient[0] == "#ff0000"  # Start color
        assert gradient[-1] == "#0000ff"  # End color

    def test_create_gradient_single_step(self):
        """Test gradient with single step"""
        gradient = VisualTheme.create_gradient("#FF0000", "#0000FF", steps=1)

        assert len(gradient) == 1
        assert gradient[0] == "#ff0000"

    def test_create_gradient_progression(self):
        """Test gradient color progression"""
        gradient = VisualTheme.create_gradient("#000000", "#FFFFFF", steps=3)

        assert len(gradient) == 3
        # Should be black, gray, white
        assert gradient[0] == "#000000"
        assert gradient[1] == "#7f7f7f"  # Middle gray
        assert gradient[2] == "#ffffff"

    def test_get_contrasting_color_light_bg(self):
        """Test contrasting color for light background"""
        # Light background should return dark text
        contrast = VisualTheme.get_contrasting_color("#FFFFFF")
        assert contrast == "#000000"

    def test_get_contrasting_color_dark_bg(self):
        """Test contrasting color for dark background"""
        # Dark background should return light text
        contrast = VisualTheme.get_contrasting_color("#000000")
        assert contrast == "#FFFFFF"

    def test_get_contrasting_color_medium(self):
        """Test contrasting color for medium background"""
        # Test with a medium brightness color
        contrast = VisualTheme.get_contrasting_color("#808080")
        # Should be black or white based on luminance calculation
        assert contrast in ["#000000", "#FFFFFF"]
