"""سياسات التوجيه والـ fallback لعميل orchestrator بشكل مركزي وقابل للاختبار."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatRoutingPolicy:
    """يمثل سياسة توجيه موحدة لمسار chat مع كسر زجاجي صريح."""

    candidate_bases: list[str]
    fallback_enabled: bool
    breakglass_multi_target: bool
    contract_version: str

    @classmethod
    def from_environment(cls, canonical_base_url: str) -> ChatRoutingPolicy:
        """يبني السياسة من المتغيرات البيئية مع افتراض canonical صارم افتراضيًا."""
        breakglass_multi_target = os.getenv("ORCHESTRATOR_ALLOW_MULTI_TARGET_CHAT", "0") == "1"
        bases: list[str] = [canonical_base_url.rstrip("/")]

        if breakglass_multi_target:
            fallback_urls_raw = os.getenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "")
            fallback_bases = [
                url.strip().rstrip("/") for url in fallback_urls_raw.split(",") if url.strip()
            ]
            bases.extend(fallback_bases)

        deduped: list[str] = []
        for base in bases:
            if base and base not in deduped:
                deduped.append(base)

        return cls(
            candidate_bases=deduped,
            fallback_enabled=os.getenv("ORCHESTRATOR_LOCAL_FALLBACK_ENABLED", "1") != "0",
            breakglass_multi_target=breakglass_multi_target,
            contract_version=os.getenv("CHAT_CONTRACT_VERSION", "v1"),
        )

    def candidate_urls(self) -> list[str]:
        """يعيد عناوين chat المرشحة وفق السياسة الموحّدة."""
        return [f"{base}/agent/chat" for base in self.candidate_bases]
