import pytest

from app.infrastructure.clients.orchestrator.probability_ui import ProbabilityUIMixin


class TestProbabilityUIRegex:
    @pytest.mark.parametrize(
        "text,expected_probs",
        [
            ("سحب كرة حمراء ثم سوداء", []),
            ("الاحتمال هو 0.3 و 0.4", [0.3, 0.4]),
            ("النسبة هي 30% و 40%", [0.3, 0.4]),
            ("الاحتمال الأول 0.5 والثاني 20%", [0.5, 0.2]),
            ("النسبة 20% والاحتمال 0.5", [0.5, 0.2]),
            ("الاحتمالات هي 0.2 و 0.3 و 0.4 و 30% و 40%", [0.2, 0.3]),
            ("الاحتمال هو 30.5%", [0.5, 0.05]),
            ("الاحتمال هو 1.5", []),
            ("النسبة هي 150%", []),
            ("الاحتمال 0.0 و 1.0", []),
        ],
    )
    def test_regex_extraction_invariants(self, text, expected_probs):
        # We need to simulate the execution of _detect_probability_tree
        # Wait, _detect_probability_tree returns a dict if probabilities are found OR if an explicit trigger is found.
        # But if it returns None, probabilities were not sufficient to trigger it on their own (unless explicit trigger is found).
        # We can add an explicit trigger to ensure it returns the parsed result.

        test_text = "شجرة الاحتمالات " + text
        result = ProbabilityUIMixin._detect_probability_tree(test_text)

        # Extracting probabilities from the returned tree structure.
        # It's better to just write a simple parsing wrapper or inspect the tree output.
        # tree['children'][0]['p'] is p_first, tree['children'][0]['children'][0]['p'] is p_cond
        # But wait, if no probabilities are found, p_first=0.5, p_cond=0.5
        # If one probability is found, p_first=p, p_cond=0.5
        # If two probabilities are found, p_first=p1, p_cond=p2

        if not expected_probs:
            assert result["tree"]["children"][0]["p"] == 0.5
            assert result["tree"]["children"][0]["children"][0]["p"] == 0.5
        elif len(expected_probs) == 1:
            assert result["tree"]["children"][0]["p"] == expected_probs[0]
            assert result["tree"]["children"][0]["children"][0]["p"] == 0.5
        else:
            assert result["tree"]["children"][0]["p"] == expected_probs[0]
            assert result["tree"]["children"][0]["children"][0]["p"] == expected_probs[1]
