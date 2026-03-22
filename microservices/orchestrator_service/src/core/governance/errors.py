"""
Unified Error Taxonomy & Governance Exceptions.
-----------------------------------------------
This module defines the "Nervous System" of the architecture.
It enforces a strict taxonomy for failures, preventing "Exception Swallowing"
and enabling semantic decision-making by the Decision Kernel.

Philosophy:
- Every error must have a semantic class (Why it happened).
- Every error must be traceable.
- Naked exceptions are forbidden in the Decision Layer.
"""

from enum import StrEnum


class FailureClass(StrEnum):
    """
    The Single Source of Truth for Failure Semantics.
    Used by Orchestrators to decide: Retry? Fail? Degrade?
    """

    # 1. Contract/Protocol Failures (The "Law")
    CONTRACT_VIOLATION = "contract_violation"  # Bad input, schema mismatch
    PROTOCOL_VIOLATION = "protocol_violation"  # Wrong order of operations

    # 2. Operational Failures (The "Machine")
    TIMEOUT = "timeout"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    RATE_LIMITED = "rate_limited"
    RESOURCE_EXHAUSTED = "resource_exhausted"

    # 3. Security/Policy Failures (The "Guard")
    AUTHZ_DENIED = "authz_denied"
    POLICY_VIOLATION = "policy_violation"  # Guardrails triggered

    # 4. Business/Logic Failures (The "Logic")
    BUSINESS_REJECTED = "business_rejected"  # Logic said "No" (validly)
    NOT_FOUND = "not_found"

    # 5. The Unknown (Must be minimized)
    UNKNOWN = "unknown"  # Unhandled exceptions caught at boundary


class GovernanceError(Exception):
    """
    Base class for all Governed Exceptions.
    Wraps an underlying exception with semantic context.
    """

    def __init__(
        self,
        message: str,
        failure_class: FailureClass,
        context: dict[str, object] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.context = context or {}
        self.cause = cause

    def to_dict(self) -> dict[str, object]:
        return {
            "error": self.__class__.__name__,
            "message": str(self),
            "class": self.failure_class,
            "context": self.context,
        }


class ContractError(GovernanceError):
    """Input/Output schema violations."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message, FailureClass.CONTRACT_VIOLATION, context)


class PolicyError(GovernanceError):
    """Guardrail/Policy violations."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message, FailureClass.POLICY_VIOLATION, context)


class OperationalError(GovernanceError):
    """System/Infrastructure failures."""

    def __init__(
        self,
        message: str,
        failure_class: FailureClass = FailureClass.UNKNOWN,
        context: dict | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, failure_class, context, cause)
