"""
Tests for environment variable readers in app.infrastructure.config.env_reader.
"""

import pytest

from app.infrastructure.config.env_reader import (
    read_bool_env,
    read_float_env,
    read_int_env,
    read_str_env,
)


class TestReadIntEnv:
    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("42", 42),
            ("-5", -5),
            (" 7 ", 7),
            ("+3", 3),
        ],
    )
    def test_valid_ints(self, monkeypatch, env_value, expected):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_INT", env_value)
        assert read_int_env("NAAS_TEST_ENV_READER_INT", default=999) == expected

    @pytest.mark.parametrize(
        "env_value",
        [
            "",
            "abc",
            "3.5",
            "1e3",
        ],
    )
    def test_invalid_ints_fallback_to_default(self, monkeypatch, env_value):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_INT_INV", env_value)
        default_val = 9999
        result = read_int_env("NAAS_TEST_ENV_READER_INT_INV", default=default_val)
        assert result == default_val
        # The fallback logic `int(os.getenv(name, str(default)))` casts the string back to an int,
        # which creates a new integer object for values outside the Python small int cache (-5 to 256).
        # Therefore we cannot assert identity `is` for the parsed fallback default.

    def test_unset_fallback_to_default(self, monkeypatch):
        monkeypatch.delenv("NAAS_TEST_ENV_READER_INT_UNSET", raising=False)
        default_val = 9999
        result = read_int_env("NAAS_TEST_ENV_READER_INT_UNSET", default=default_val)
        assert result == default_val

    def test_exception_fallback(self, monkeypatch):
        """Dedicated test proving fallback on ValueError specifically."""
        monkeypatch.setenv("NAAS_TEST_ENV_READER_INT_EXC", "invalid_number")
        assert read_int_env("NAAS_TEST_ENV_READER_INT_EXC", default=42) == 42


class TestReadFloatEnv:
    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("3.14", 3.14),
            ("1e3", 1000.0),
            ("-0.5", -0.5),
            ("42", 42.0),
        ],
    )
    def test_valid_floats(self, monkeypatch, env_value, expected):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_FLOAT", env_value)
        assert read_float_env("NAAS_TEST_ENV_READER_FLOAT", default=99.9) == expected

    @pytest.mark.parametrize(
        "env_value",
        [
            "",
            "abc",
        ],
    )
    def test_invalid_floats_fallback_to_default(self, monkeypatch, env_value):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_FLOAT_INV", env_value)
        default_val = 99.9
        result = read_float_env("NAAS_TEST_ENV_READER_FLOAT_INV", default=default_val)
        assert result == default_val
        assert result is default_val

    def test_unset_fallback_to_default(self, monkeypatch):
        monkeypatch.delenv("NAAS_TEST_ENV_READER_FLOAT_UNSET", raising=False)
        default_val = 99.9
        result = read_float_env("NAAS_TEST_ENV_READER_FLOAT_UNSET", default=default_val)
        assert result == default_val
        # Note: in Python, small integers share identity, but floats don't always,
        # but in this case, `return default` simply returns the same object.
        # Wait, the fallback is: `return float(os.getenv(name, str(default)))`
        # Because it casts string to float, it creates a NEW float! It is not identical.
        # Let's verify this and not assert `is` since the fallback casts `str(default)` to float.

    def test_nan_inf_behavior(self, monkeypatch):
        """
        Document current behavior for nan and inf.
        Python's float() handles 'nan', 'inf', '-inf' naturally.
        This test notes that these values are accepted and parsed as float.
        """
        monkeypatch.setenv("NAAS_TEST_ENV_READER_FLOAT_NAN", "nan")
        import math

        assert math.isnan(read_float_env("NAAS_TEST_ENV_READER_FLOAT_NAN", default=0.0))

        monkeypatch.setenv("NAAS_TEST_ENV_READER_FLOAT_INF", "inf")
        assert math.isinf(read_float_env("NAAS_TEST_ENV_READER_FLOAT_INF", default=0.0))
        assert read_float_env("NAAS_TEST_ENV_READER_FLOAT_INF", default=0.0) > 0


class TestReadBoolEnv:
    @pytest.mark.parametrize(
        "env_value",
        [
            "true",
            "True",
            "TRUE",
            "1",
            "yes",
            "on",
        ],
    )
    def test_truthy_values(self, monkeypatch, env_value):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_BOOL", env_value)
        assert read_bool_env("NAAS_TEST_ENV_READER_BOOL", default=False) is True

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("", False),
            ("maybe", False),
            ("  ", False),
            ("YES ", True),  # strip() makes it "yes", which is truthy
        ],
    )
    def test_falsy_values(self, monkeypatch, env_value, expected):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_BOOL", env_value)
        # Verify the actual output for various non-truthy values
        # Default is True, to ensure that parsing explicitly overrides it and evaluates to expected boolean
        assert read_bool_env("NAAS_TEST_ENV_READER_BOOL", default=True) is expected

    def test_strip_behavior(self, monkeypatch):
        """Test that .strip() makes padded string work."""
        monkeypatch.setenv("NAAS_TEST_ENV_READER_BOOL_STRIP", " yes ")
        assert read_bool_env("NAAS_TEST_ENV_READER_BOOL_STRIP", default=False) is True

    def test_unset_fallback_to_default_true(self, monkeypatch):
        monkeypatch.delenv("NAAS_TEST_ENV_READER_BOOL_UNSET", raising=False)
        assert read_bool_env("NAAS_TEST_ENV_READER_BOOL_UNSET", default=True) is True

    def test_unset_fallback_to_default_false(self, monkeypatch):
        monkeypatch.delenv("NAAS_TEST_ENV_READER_BOOL_UNSET", raising=False)
        assert read_bool_env("NAAS_TEST_ENV_READER_BOOL_UNSET", default=False) is False


class TestReadStrEnv:
    def test_set_value(self, monkeypatch):
        monkeypatch.setenv("NAAS_TEST_ENV_READER_STR", "hello")
        assert read_str_env("NAAS_TEST_ENV_READER_STR", default="world") == "hello"

    def test_unset_value(self, monkeypatch):
        monkeypatch.delenv("NAAS_TEST_ENV_READER_STR_UNSET", raising=False)
        assert read_str_env("NAAS_TEST_ENV_READER_STR_UNSET", default="world") == "world"

    def test_empty_string(self, monkeypatch):
        """
        Tests that an explicitly empty string is returned as empty string
        and does NOT fall back to default.
        """
        monkeypatch.setenv("NAAS_TEST_ENV_READER_STR_EMPTY", "")
        # os.getenv returns "" for explicitly set empty env vars.
        # Implementation: return os.getenv(name, default)
        assert read_str_env("NAAS_TEST_ENV_READER_STR_EMPTY", default="default_str") == ""

    def test_none_default(self, monkeypatch):
        """Test default=None if signature permits (it allows default: str, but duck typing works)"""
        monkeypatch.delenv("NAAS_TEST_ENV_READER_STR_NONE", raising=False)
        # Type signature is default: str = "", but passing None works at runtime.
        assert read_str_env("NAAS_TEST_ENV_READER_STR_NONE", default=None) is None
