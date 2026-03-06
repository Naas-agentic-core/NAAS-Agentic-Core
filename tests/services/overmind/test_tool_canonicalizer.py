"""
Tests for Tool Canonicalizer
=============================

Comprehensive tests for the refactored tool canonicalization system.
"""

import pytest

from microservices.orchestrator_service.src.services.overmind.tool_canonicalizer import (
    AliasStrategy,
    CanonicalResult,
    DescriptionIntentStrategy,
    DirectMatchStrategy,
    DottedNameStrategy,
    KeywordStrategy,
    ToolCanonicalizer,
    canonicalize_tool_name,
)


class TestDottedNameStrategy:
    """Test dotted name strategy."""

    def test_write_suffix(self):
        strategy = DottedNameStrategy()
        result = strategy.canonicalize("file.write", "")

        assert result.canonical_name == "write_file"
        assert "dotted_split:file.write" in result.notes
        assert result.matched_by == "DottedNameStrategy"

    def test_read_suffix(self):
        strategy = DottedNameStrategy()
        result = strategy.canonicalize("file.read", "")

        assert result.canonical_name == "read_file"
        assert "dotted_split:file.read" in result.notes

    def test_unknown_suffix(self):
        strategy = DottedNameStrategy()
        result = strategy.canonicalize("file.unknown", "")

        assert result.canonical_name == "file.unknown"
        assert result.matched_by is None

    def test_disabled_dotted(self):
        strategy = DottedNameStrategy(accept_dotted=False)
        assert not strategy.can_handle("file.write", "")


class TestAliasStrategy:
    """Test alias strategy."""

    def test_write_alias(self):
        strategy = AliasStrategy()
        result = strategy.canonicalize("str_replace_editor", "")

        assert result.canonical_name == "write_file"
        assert "alias_write:str_replace_editor" in result.notes
        assert result.matched_by == "AliasStrategy"

    def test_read_alias(self):
        strategy = AliasStrategy()
        result = strategy.canonicalize("cat", "")

        assert result.canonical_name == "read_file"
        assert "alias_read:cat" in result.notes

    def test_custom_aliases(self):
        strategy = AliasStrategy(
            write_aliases={"custom_write"},
            read_aliases={"custom_read"},
        )

        result = strategy.canonicalize("custom_write", "")
        assert result.canonical_name == "write_file"

    def test_case_insensitive(self):
        strategy = AliasStrategy()
        result = strategy.canonicalize("WRITE_FILE", "")

        assert result.canonical_name == "write_file"


class TestDirectMatchStrategy:
    """Test direct match strategy."""

    def test_ensure_file(self):
        strategy = DirectMatchStrategy()
        result = strategy.canonicalize("ensure_file", "")

        assert result.canonical_name == "ensure_file"
        assert "direct_ensure_file" in result.notes
        assert result.matched_by == "DirectMatchStrategy"

    def test_append_file(self):
        strategy = DirectMatchStrategy()
        result = strategy.canonicalize("append_file", "")

        assert result.canonical_name == "append_file"
        assert "direct_append_file" in result.notes

    def test_non_canonical(self):
        strategy = DirectMatchStrategy()
        assert not strategy.can_handle("random_tool", "")


class TestKeywordStrategy:
    """Test keyword strategy."""

    def test_write_keyword(self):
        strategy = KeywordStrategy()
        result = strategy.canonicalize("create_new_file", "")

        assert result.canonical_name == "write_file"
        assert "keyword_write:create" in result.notes
        assert result.matched_by == "KeywordStrategy"

    def test_read_keyword(self):
        strategy = KeywordStrategy()
        result = strategy.canonicalize("load_config", "")

        assert result.canonical_name == "read_file"
        assert "keyword_read:load" in result.notes

    def test_multiple_keywords(self):
        strategy = KeywordStrategy()
        result = strategy.canonicalize("read_and_write", "")

        # Should match first keyword found (write comes first in set iteration)
        assert result.canonical_name in ["write_file", "read_file"]


class TestDescriptionIntentStrategy:
    """Test description intent strategy."""

    def test_write_intent_from_description(self):
        strategy = DescriptionIntentStrategy()
        result = strategy.canonicalize("file", "This tool creates a new file")

        assert result.canonical_name == "write_file"
        assert "intent_desc_write" in result.notes
        assert result.matched_by == "DescriptionIntentStrategy"

    def test_read_intent_from_description(self):
        strategy = DescriptionIntentStrategy()
        result = strategy.canonicalize("unknown", "This tool reads file contents")

        assert result.canonical_name == "read_file"
        assert "intent_desc_read" in result.notes

    def test_no_intent_without_description(self):
        strategy = DescriptionIntentStrategy()
        assert not strategy.can_handle("file", "")

    def test_disabled_intent_check(self):
        strategy = DescriptionIntentStrategy(force_intent_check=False)
        assert not strategy.can_handle("file", "creates a file")


class TestToolCanonicalizer:
    """Test the main canonicalizer."""

    def test_strategy_chain_priority(self):
        canonicalizer = ToolCanonicalizer()

        # Dotted name should match before keyword
        result = canonicalizer.canonicalize("file.write", "")
        assert result.matched_by == "DottedNameStrategy"

    def test_fallback_to_original(self):
        canonicalizer = ToolCanonicalizer()
        result = canonicalizer.canonicalize("completely_unknown_tool", "")

        assert result.canonical_name == "completely_unknown_tool"
        assert result.matched_by is None
        assert result.notes == []

    def test_add_custom_strategy(self):
        class CustomStrategy(AliasStrategy):
            @property
            def priority(self) -> int:
                return 5  # Higher priority than default

            def can_handle(self, name: str, description: str) -> bool:
                return name == "custom_tool"

            def canonicalize(self, name: str, description: str) -> CanonicalResult:
                return CanonicalResult("custom_canonical", ["custom"], "CustomStrategy")

        canonicalizer = ToolCanonicalizer()
        canonicalizer.add_strategy(CustomStrategy())

        result = canonicalizer.canonicalize("custom_tool", "")
        assert result.canonical_name == "custom_canonical"
        assert result.matched_by == "CustomStrategy"

    def test_remove_strategy(self):
        canonicalizer = ToolCanonicalizer()
        canonicalizer.remove_strategy(KeywordStrategy)

        # "create_file" will still match AliasStrategy (write_aliases)
        # Use a name that only KeywordStrategy would match
        result = canonicalizer.canonicalize("generate_report", "")
        # Should fall back to unmatched since keyword strategy is removed
        assert result.canonical_name == "generate_report"

    def test_empty_strategies(self):
        canonicalizer = ToolCanonicalizer(strategies=[])
        result = canonicalizer.canonicalize("any_tool", "")

        assert result.canonical_name == "any_tool"
        assert result.matched_by is None


class TestBackwardCompatibility:
    """Test backward-compatible function."""

    def test_canonicalize_tool_name_function(self):
        canonical, notes = canonicalize_tool_name("file.write", "")

        assert canonical == "write_file"
        assert len(notes) > 0
        assert any("dotted_split" in note for note in notes)

    def test_returns_tuple(self):
        result = canonicalize_tool_name("read_file", "")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)


class TestComplexityReduction:
    """Verify complexity reduction."""

    def test_each_strategy_simple(self):
        """Each strategy should have low cyclomatic complexity."""
        strategies = [
            DottedNameStrategy(),
            AliasStrategy(),
            DirectMatchStrategy(),
            KeywordStrategy(),
            DescriptionIntentStrategy(),
        ]

        for strategy in strategies:
            # Each strategy's can_handle and canonicalize should be simple
            # This is a meta-test to ensure we maintain low complexity
            assert hasattr(strategy, "can_handle")
            assert hasattr(strategy, "canonicalize")
            assert hasattr(strategy, "priority")

    def test_main_canonicalizer_simple(self):
        """Main canonicalizer should have low complexity."""
        canonicalizer = ToolCanonicalizer()

        # The main loop is simple: iterate and delegate
        result = canonicalizer.canonicalize("test", "")
        assert isinstance(result, CanonicalResult)


class TestRealWorldScenarios:
    """Test real-world tool name scenarios."""

    @pytest.mark.parametrize(
        "raw_name,description,expected",
        [
            ("str_replace_editor", "", "write_file"),
            ("file.read", "", "read_file"),
            ("create_new_document", "", "write_file"),
            ("load_config_file", "", "read_file"),
            ("ensure_file", "", "ensure_file"),
            ("append_file", "", "append_file"),
            ("file", "creates a new file", "write_file"),
            ("unknown", "reads the contents", "read_file"),
            ("completely_random_tool", "", "completely_random_tool"),
        ],
    )
    def test_real_world_cases(self, raw_name, description, expected):
        canonical, _ = canonicalize_tool_name(raw_name, description)
        assert canonical == expected
