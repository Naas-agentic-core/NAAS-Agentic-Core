import json
from unittest.mock import MagicMock

import pytest

from microservices.orchestrator_service.src.services.overmind.agents.auditor import AuditorAgent


class TestAuditorJsonRepair:
    @pytest.fixture
    def auditor(self):
        mock_ai = MagicMock()
        return AuditorAgent(mock_ai)

    def test_repair_missing_comma_between_properties(self, auditor):
        bad_json = '{"approved": false "feedback": "foo"}'
        # false is followed by "feedback":
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"approved": False, "feedback": "foo"}

    def test_repair_missing_comma_string_string_array(self, auditor):
        bad_json = '{"list": ["a" "b"]}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"list": ["a", "b"]}

    def test_repair_trailing_comma_object(self, auditor):
        bad_json = '{"a": 1,}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"a": 1}

    def test_repair_trailing_comma_array(self, auditor):
        bad_json = '{"a": [1,]}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"a": [1]}

    def test_repair_mixed_errors(self, auditor):
        # Missing comma AND trailing comma
        bad_json = '{"approved": true "score": 0.9,}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"approved": True, "score": 0.9}

    def test_repair_numbers(self, auditor):
        bad_json = '{"a": 123 "b": 4.56}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"a": 123, "b": 4.56}

    def test_repair_complex_nested(self, auditor):
        # Nested object with missing comma: "val" "inner2":
        bad_json = '{"outer": {"inner": "val" "inner2": "val2"}}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"outer": {"inner": "val", "inner2": "val2"}}

    def test_does_not_break_strings_with_digits(self, auditor):
        # "val2" followed by }
        bad_json = '{"key": "val2"}'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == {"key": "val2"}

    def test_does_not_break_valid_json(self, auditor):
        valid_json = '{"a": 1, "b": 2}'
        repaired = auditor._repair_json(valid_json)
        assert json.loads(repaired) == {"a": 1, "b": 2}

    def test_array_objects_missing_comma(self, auditor):
        bad_json = '[{"a":1} {"b":2}]'
        repaired = auditor._repair_json(bad_json)
        assert json.loads(repaired) == [{"a": 1}, {"b": 2}]
