import json
import logging
import re
from typing import TypeVar

from pydantic import ValidationError

from microservices.auditor_service.src.ai import SimpleAIClient
from microservices.auditor_service.src.schemas import (
    ConsultRequest,
    ConsultResponse,
    ReviewRequest,
    ReviewResponse,
)
from microservices.auditor_service.src.utils.dec_pomdp import (
    build_dec_pomdp_consultation_payload,
    is_dec_pomdp_proof_question,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AuditorService:
    """
    Auditor Service Implementation.
    Separated from the Monolith.
    """

    def __init__(self):
        self.ai = SimpleAIClient()

    async def review_work(self, request: ReviewRequest) -> ReviewResponse:
        """
        Review the work result or plan.
        """
        result = request.result
        objective = request.original_objective
        # context = request.context  # Unused in core logic currently

        # 0. Detect Plan vs Execution
        is_plan = (
            isinstance(result, dict)
            and "steps" in result
            and isinstance(result["steps"], list)
            and "strategy_name" in result
        )

        if is_plan:
            logger.info("Auditor detected a Plan. Switching to Plan Review mode.")
            return await self._review_plan(result, objective)

        # 1. Deep Review via AI
        return await self._review_execution(result, objective)

    async def consult(self, request: ConsultRequest) -> ConsultResponse:
        """
        Provide consultation.
        """
        situation = request.situation
        analysis = request.analysis

        logger.info("Auditor is being consulted...")

        if is_dec_pomdp_proof_question(situation):
            payload = build_dec_pomdp_consultation_payload("auditor")
            # Adapt payload to schema
            return ConsultResponse(
                recommendation=payload.get("recommendation", ""),
                confidence=payload.get("confidence", 0.0),
            )

        system_prompt = """
        You are "The Auditor".
        Analyze the situation for security, quality, and compliance risks.

        Provide a concise recommendation.
        Response MUST be valid JSON matching this schema:
        {
            "recommendation": "string (english)",
            "confidence": float (0-100)
        }
        """

        user_message = f"Situation: {situation}\nAnalysis: {json.dumps(analysis, default=str)}"

        # LLM Gate with Retry
        return await self._call_ai_with_validation(system_prompt, user_message, ConsultResponse)

    async def _review_plan(self, plan: dict[str, object], objective: str) -> ReviewResponse:
        """
        Review a proposed plan.
        """
        system_prompt = """
        You are "The Auditor".
        Review the proposed "Action Plan".

        Criteria:
        1. Logical steps towards the goal?
        2. Safe execution?
        3. Appropriate tools?

        If good, approve immediately.

        Response MUST be valid JSON matching this schema:
        {
            "approved": boolean,
            "feedback": "string (arabic)",
            "score": float (0.0 - 1.0),
            "final_response": "string (markdown summary)"
        }
        """

        user_message = f"""
        Objective: {objective}
        Proposed Plan:
        {json.dumps(plan, ensure_ascii=False, default=str)}

        Is this plan logical and safe?
        """

        return await self._call_ai_with_validation(system_prompt, user_message, ReviewResponse)

    async def _review_execution(self, result: dict[str, object], objective: str) -> ReviewResponse:
        """
        Review execution results.
        """
        system_prompt = """
        You are "The Auditor".
        Review the execution results against the original objective.

        Criteria:
        1. Progress made?
        2. No security errors?
        3. Partial success is acceptable if direction is correct.

        Response MUST be valid JSON matching this schema:
        {
            "approved": boolean,
            "feedback": "string (arabic)",
            "score": float (0.0 - 1.0),
            "final_response": "string (markdown formatted professional response - REQUIRED)"
        }
        """

        user_message = f"""
        Original Objective: {objective}
        Execution Results:
        {json.dumps(result, ensure_ascii=False, default=str)}

        Did we succeed? Provide critical analysis.
        """

        return await self._call_ai_with_validation(system_prompt, user_message, ReviewResponse)

    async def _call_ai_with_validation(
        self, system_prompt: str, user_message: str, model_class: type[T]
    ) -> T:
        """
        The LLM Output Gate.
        Calls AI, parses JSON, validates against Pydantic model.
        Retries on failure.
        """
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response_text = await self.ai.send_message(
                    system_prompt=system_prompt, user_message=user_message, temperature=0.1
                )

                # 1. Clean Markdown
                cleaned_json = self._clean_json_block(response_text)

                # 2. Validate with Pydantic (Strict)
                return model_class.model_validate_json(cleaned_json)

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Validation failed on attempt {attempt}: {e}")
                last_error = e
                # Add error to user message for retry
                user_message += f"\n\nPrevious response was invalid JSON or schema. Error: {e!s}. Please fix format."
            except Exception as e:
                logger.error(f"AI call failed: {e}")
                raise e

        # If retries exhausted, return a safe fallback or raise
        logger.error(f"LLM Gate failed after retries. Last error: {last_error}")
        return self._create_fallback(model_class, str(last_error))

    def _clean_json_block(self, text: str) -> str:
        """Extract JSON from text."""
        text = text.strip()
        json_code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(json_code_block_pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text

    def _create_fallback(self, model_class: type[T], error_msg: str) -> T:
        """
        Create a safe fallback response if validation fails completely.
        """
        if model_class == ReviewResponse:
            return ReviewResponse(
                approved=False,
                feedback=f"Technical Error in Auditor Validation: {error_msg}",
                score=0.0,
                final_response="**System Error:** Validation of Auditor response failed.",
            )
        if model_class == ConsultResponse:
            return ConsultResponse(
                recommendation="System Error (Validation Failed). Proceed with caution.",
                confidence=0.0,
            )
        raise ValueError("Unknown model class for fallback")
