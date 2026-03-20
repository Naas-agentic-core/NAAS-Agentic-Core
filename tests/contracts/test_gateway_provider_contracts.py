"""اختبارات تحقق provider لعقود gateway بين chat/content (HTTP + WS)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.fitness.check_gateway_provider_contracts import main as verify_provider_contracts

CONTRACT_FILE = Path("docs/contracts/consumer/gateway_chat_content_contracts.json")


def test_gateway_provider_contract_verification_script_passes() -> None:
    """يتأكد أن التحقق الآلي للعقود ينجح ويعمل كبوابة منع drift في CI."""
    assert verify_provider_contracts() == 0


def test_ws_contract_envelope_minimum_shape() -> None:
    """يتأكد أن عقد WS يفرض حقول envelope الدنيا حفاظًا على التوافق."""
    data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    websocket_contracts: list[dict[str, object]] = data["websocket"]

    for item in websocket_contracts:
        envelope = item["envelope"]
        incoming_fields = envelope["incoming_required_fields"]
        outgoing_fields = envelope["outgoing_required_fields"]
        assert "question" in incoming_fields
        assert "status" in outgoing_fields
        assert "response" in outgoing_fields
