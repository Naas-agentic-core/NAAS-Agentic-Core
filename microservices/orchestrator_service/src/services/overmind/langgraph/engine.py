from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph

from microservices.orchestrator_service.src.core.protocols import (
    AgentArchitect,
    AgentExecutor,
    AgentPlanner,
    AgentReflector,
)
from microservices.orchestrator_service.src.services.overmind.domain.context import (
    InMemoryCollaborationContext,
)
from microservices.orchestrator_service.src.services.overmind.langgraph.context_enricher import (
    ContextEnricher,
)
from microservices.orchestrator_service.src.services.overmind.langgraph.loop_policy import (
    LoopPolicy,
    should_continue_loop,
)

logger = logging.getLogger(__name__)


class LangGraphState(TypedDict):
    """
    حالة LangGraph المشتركة بين الوكلاء.

    تمثل هذه البنية الواجهة الموحدة لنقل البيانات عبر العقد،
    مع الحفاظ على الحواجز التجريدية وتجنب الاعتمادات المتشابكة.
    """

    objective: str
    context: dict[str, object]
    constraints: list[str]
    priority: str
    shared_memory: dict[str, object]
    plan: dict[str, object] | None
    design: dict[str, object] | None
    execution: dict[str, object] | None
    audit: dict[str, object] | None
    timeline: list[dict[str, object]]
    iteration: int
    max_iterations: int
    plan_hashes: list[str]
    loop_detected: bool
    next_step: str | None
    answer: str | None


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    """
    قرار المشرف لتوجيه تدفق العمل بين الوكلاء.
    """

    next_step: str
    reason: str


class SupervisorOrchestrator:
    """
    مشرف توزيع المهام وفق نمط Supervisor-Worker.

    يحافظ على حواجز التجريد عبر فصل منطق التوجيه عن العقد التنفيذية،
    ويُبقي قرار الانتقال بين الوكلاء نقياً دون آثار جانبية.
    """

    def __init__(self, loop_policy: LoopPolicy) -> None:
        self.loop_policy = loop_policy

    def decide(self, state: LangGraphState) -> SupervisorDecision:
        """
        تحديد العقدة التالية بناءً على حالة التنفيذ الحالية.
        """
        max_iters = state.get("max_iterations", 5)
        if state.get("iteration", 0) >= max_iters:
            return SupervisorDecision(next_step="end", reason="MAX_ITERATIONS_REACHED")

        if state.get("loop_detected"):
            if state.get("audit") is None:
                return SupervisorDecision(
                    next_step="auditor", reason="تم اكتشاف حلقة ويجب إنهاء التدقيق."
                )
            return SupervisorDecision(next_step="end", reason="تم اكتشاف حلقة وتم إنهاء المراجعة.")

        shared_memory = state.get("shared_memory", {})
        context = state.get("context", {})

        # Classification / Routing Phase based on intent mode
        mode = context.get("mission_type", "mission_complex")
        if mode == "auto":
            objective = state.get("objective", "").lower()
            if any(k in objective for k in ["بحث", "مهمة", "mission", "خطة", "استراتيجية"]):
                mode = "mission_complex"
            elif any(
                k in objective for k in ["فكر", "كيف", "لماذا", "اشرح", "reason", "why", "how"]
            ):
                mode = "reasoning"
            else:
                mode = "simple"

        if mode == "simple":
            if state.get("execution") is None:
                return SupervisorDecision(next_step="simple_responder", reason="تنفيذ دردشة عادية.")
            return SupervisorDecision(next_step="end", reason="تم إنهاء الدردشة العادية.")

        if mode == "reasoning":
            if state.get("execution") is None:
                return SupervisorDecision(
                    next_step="reasoning_responder", reason="تنفيذ دردشة مع تفكير عميق."
                )
            return SupervisorDecision(next_step="end", reason="تم إنهاء التفكير العميق.")

        # Default mission_complex flow
        # Force Research Check
        force_research = context.get("force_research")
        if force_research and not shared_memory.get("research_performed"):
            return SupervisorDecision(
                next_step="contextualizer", reason="طلب بحث إلزامي (Force Research)."
            )

        if not shared_memory.get("context_enriched"):
            return SupervisorDecision(
                next_step="contextualizer", reason="السياق لم يتم إثراؤه بعد."
            )

        if state.get("plan") is None:
            return SupervisorDecision(next_step="strategist", reason="الخطة غير متوفرة.")

        if state.get("design") is None:
            return SupervisorDecision(next_step="architect", reason="التصميم غير مكتمل.")

        if state.get("execution") is None:
            return SupervisorDecision(next_step="operator", reason="التنفيذ غير مكتمل.")

        if state.get("audit") is None:
            return SupervisorDecision(next_step="auditor", reason="المراجعة لم تتم بعد.")

        max_iterations = state.get("max_iterations", self.loop_policy.max_iterations)
        effective_policy = LoopPolicy(
            max_iterations=max_iterations,
            approval_score=self.loop_policy.approval_score,
        )
        if should_continue_loop(
            audit=state.get("audit"),
            iteration=state.get("iteration", 0),
            policy=effective_policy,
        ):
            return SupervisorDecision(next_step="loop_controller", reason="المراجعة تطلب تحسينات.")

        return SupervisorDecision(next_step="end", reason="تم اعتماد المخرجات النهائية.")


@dataclass(frozen=True, slots=True)
class LangGraphRunResult:
    """
    نتيجة تشغيل LangGraph بعد اكتمال دورة الوكلاء.
    """

    run_id: str
    state: LangGraphState


class LangGraphOvermindEngine:
    """
    محرك LangGraph لمنظومة الوكلاء الخارقين.

    يبني هذا المحرك مخططاً معرفياً متسلسلاً (Strategist -> Architect -> Operator -> Auditor)
    مع تمرير حالة مشتركة واضحة، مما يعزز الاتساق مع فلسفة Functional Core/Imperative Shell.
    """

    def __init__(
        self,
        *,
        strategist: AgentPlanner,
        architect: AgentArchitect,
        operator: AgentExecutor,
        auditor: AgentReflector,
        context_enricher: ContextEnricher | None = None,
        loop_policy: LoopPolicy | None = None,
    ) -> None:
        self.strategist = strategist
        self.architect = architect
        self.operator = operator
        self.auditor = auditor
        self.loop_policy = loop_policy or LoopPolicy()
        self.context_enricher = context_enricher or ContextEnricher()
        self.supervisor = SupervisorOrchestrator(self.loop_policy)
        self._compiled_graph = self._build_graph()
        self._observer: Callable[[str, dict], Awaitable[None]] | None = None

    async def run(
        self,
        *,
        run_id: str,
        objective: str,
        context: dict[str, object],
        constraints: list[str],
        priority: str,
        observer: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> LangGraphRunResult:
        """
        تشغيل دورة LangGraph كاملة مع الحفاظ على حالة مشتركة.

        Args:
            run_id: معرف التشغيل.
            objective: الهدف الرئيسي.
            context: سياق إضافي.
            constraints: قيود تشغيلية.
            priority: أولوية الطلب.
            observer: دالة مراقبة غير متزامنة لتلقي الأحداث.

        Returns:
            LangGraphRunResult: حالة التشغيل النهائية.
        """
        self._observer = observer

        initial_state: LangGraphState = {
            "objective": objective,
            "context": context,
            "constraints": constraints,
            "priority": priority,
            "shared_memory": {
                "request_context": context,
                "constraints": constraints,
                "priority": priority,
            },
            "plan": None,
            "design": None,
            "execution": None,
            "audit": None,
            "timeline": [],
            "iteration": 0,
            "max_iterations": self._resolve_max_iterations(context),
            "plan_hashes": [],
            "loop_detected": False,
            "next_step": None,
            "answer": None,
        }

        final_state = await self._compiled_graph.ainvoke(
            initial_state,
            config={"recursion_limit": max(10, initial_state["max_iterations"] * 2)},
        )
        return LangGraphRunResult(run_id=run_id, state=final_state)

    def _build_graph(self):
        """
        بناء مخطط LangGraph مركّب للوكلاء.
        """
        graph: StateGraph[LangGraphState] = StateGraph(LangGraphState)
        graph.add_node("supervisor", self._supervisor_node)
        graph.add_node("contextualizer", self._contextualizer_node)
        graph.add_node("strategist", self._strategist_node)
        graph.add_node("architect", self._architect_node)
        graph.add_node("operator", self._operator_node)
        graph.add_node("auditor", self._auditor_node)
        graph.add_node("loop_controller", self._loop_controller_node)
        graph.add_node("simple_responder", self._simple_responder_node)
        graph.add_node("reasoning_responder", self._reasoning_responder_node)

        graph.set_entry_point("supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self._route_from_supervisor,
            {
                "contextualizer": "contextualizer",
                "strategist": "strategist",
                "architect": "architect",
                "operator": "operator",
                "auditor": "auditor",
                "loop_controller": "loop_controller",
                "simple_responder": "simple_responder",
                "reasoning_responder": "reasoning_responder",
                "end": END,
            },
        )
        graph.add_edge("contextualizer", "supervisor")
        graph.add_edge("strategist", "supervisor")
        graph.add_edge("architect", "supervisor")
        graph.add_edge("operator", "supervisor")
        graph.add_edge("auditor", "supervisor")
        graph.add_edge("loop_controller", "supervisor")
        graph.add_edge("simple_responder", "supervisor")
        graph.add_edge("reasoning_responder", "supervisor")

        return graph.compile()

    def _build_context(self, state: LangGraphState) -> InMemoryCollaborationContext:
        """
        إنشاء سياق تعاون متوافق مع بروتوكولات الوكلاء.
        """
        return InMemoryCollaborationContext(dict(state.get("shared_memory", {})))

    def _resolve_max_iterations(self, context: dict[str, object]) -> int:
        """
        استخراج الحد الأعلى للتكرار من السياق مع حماية الحدود.
        """
        candidate = context.get("max_iterations")
        try:
            max_iterations = (
                int(candidate) if candidate is not None else self.loop_policy.max_iterations
            )
        except (TypeError, ValueError):
            max_iterations = self.loop_policy.max_iterations
        return max(1, min(max_iterations, 5))

    def _route_from_supervisor(self, state: LangGraphState) -> str:
        """
        توجيه التدفق اعتماداً على قرار المشرف.
        """
        next_step = state.get("next_step")
        if next_step in {
            "contextualizer",
            "strategist",
            "architect",
            "operator",
            "auditor",
            "loop_controller",
            "simple_responder",
            "reasoning_responder",
        }:
            return next_step
        return "end"

    def _append_timeline(
        self, state: LangGraphState, agent: str, payload: dict[str, object]
    ) -> list[dict[str, object]]:
        """
        إنشاء سجل زمني جديد مع إضافة حدث الوكيل.
        """
        return [*state.get("timeline", []), {"agent": agent, "payload": payload}]

    async def _contextualizer_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة إثراء السياق بإسناد DSPy و LlamaIndex قبل التخطيط.
        """
        # ✅ Make "RESEARCH" a real phase for the UI (wrap enrichment as research activity)
        # Note: We removed the duplicate "CONTEXT_ENRICHMENT" emission to prevent UI flickering.
        if self._observer:
            await self._observer("phase_start", {"phase": "RESEARCH", "agent": "Contextualizer"})

        enrichment = await self.context_enricher.enrich(state["objective"], state["context"])

        if self._observer:
            await self._observer(
                "phase_completed", {"phase": "RESEARCH", "agent": "Contextualizer"}
            )

        shared_memory = {
            **state.get("shared_memory", {}),
            "refined_objective": enrichment.refined_objective,
            "metadata_filters": enrichment.metadata,
            "knowledge_snippets": enrichment.snippets,
            "context_enriched": True,
            "research_performed": True,
        }

        return {
            "shared_memory": shared_memory,
            "timeline": self._append_timeline(
                state,
                "contextualizer",
                {
                    "status": "enriched",
                    "refined_objective": enrichment.refined_objective,
                    "snippets_count": len(enrichment.snippets),
                },
            ),
        }

    async def _strategist_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة الاستراتيجي في LangGraph.
        """
        if self._observer:
            await self._observer("phase_start", {"phase": "PLANNING", "agent": "Strategist"})

        context = self._build_context(state)
        objective = context.shared_memory.get("refined_objective", state["objective"])
        plan = await self.strategist.create_plan(str(objective), context)
        context.update("last_plan", plan)
        plan_hashes = list(state.get("plan_hashes", []))
        try:
            if hasattr(self.auditor, "detect_loop"):
                self.auditor.detect_loop(plan_hashes, plan)
            if hasattr(self.auditor, "compute_plan_hash"):
                plan_hashes.append(self.auditor.compute_plan_hash(plan))
        except Exception as exc:
            context.update("loop_error", str(exc))
            return {
                "plan": plan,
                "shared_memory": context.shared_memory,
                "plan_hashes": plan_hashes,
                "loop_detected": True,
                "timeline": self._append_timeline(
                    state, "strategist", {"status": "loop_detected", "error": str(exc)}
                ),
            }

        if self._observer:
            await self._observer("phase_completed", {"phase": "PLANNING", "agent": "Strategist"})

        return {
            "plan": plan,
            "shared_memory": context.shared_memory,
            "plan_hashes": plan_hashes,
            "timeline": self._append_timeline(state, "strategist", {"status": "planned"}),
        }

    async def _architect_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة المعماري في LangGraph.
        """
        if state.get("loop_detected"):
            return {
                "timeline": self._append_timeline(
                    state, "architect", {"status": "skipped_due_to_loop"}
                )
            }

        if self._observer:
            await self._observer("phase_start", {"phase": "DESIGN", "agent": "Architect"})

        context = self._build_context(state)
        plan = state.get("plan") or {}
        design = await self.architect.design_solution(plan, context)
        context.update("last_design", design)

        if self._observer:
            await self._observer("phase_completed", {"phase": "DESIGN", "agent": "Architect"})

        return {
            "design": design,
            "shared_memory": context.shared_memory,
            "timeline": self._append_timeline(state, "architect", {"status": "designed"}),
        }

    async def _operator_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة المنفذ في LangGraph.
        """
        if state.get("loop_detected"):
            return {
                "timeline": self._append_timeline(
                    state, "operator", {"status": "skipped_due_to_loop"}
                )
            }

        if self._observer:
            await self._observer("phase_start", {"phase": "EXECUTION", "agent": "Operator"})

        context = self._build_context(state)
        design = state.get("design") or {}
        execution = await self.operator.execute_tasks(design, context)
        context.update("last_execution", execution)

        if self._observer:
            await self._observer("phase_completed", {"phase": "EXECUTION", "agent": "Operator"})

        return {
            "execution": execution,
            "shared_memory": context.shared_memory,
            "timeline": self._append_timeline(state, "operator", {"status": "executed"}),
        }

    async def _auditor_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة المدقق في LangGraph.
        """
        if state.get("loop_detected"):
            return {
                "audit": {
                    "approved": False,
                    "feedback": "تم إيقاف الدورة بسبب اكتشاف حلقة تكرارية مفرغة.",
                    "score": 0.0,
                },
                "timeline": self._append_timeline(state, "auditor", {"status": "loop_stopped"}),
            }

        if self._observer:
            await self._observer("phase_start", {"phase": "REFLECTION", "agent": "Auditor"})

        context = self._build_context(state)
        execution = state.get("execution") or {}
        audit = await self.auditor.review_work(execution, state["objective"], context)
        context.update("last_audit", audit)

        if self._observer:
            await self._observer("phase_completed", {"phase": "REFLECTION", "agent": "Auditor"})

        updates = {
            "audit": audit,
            "shared_memory": context.shared_memory,
            "timeline": self._append_timeline(state, "auditor", {"status": "audited"}),
        }

        if isinstance(audit, dict) and audit.get("final_response"):
            updates["answer"] = str(audit["final_response"])

        return updates

    async def _supervisor_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة المشرف لتوزيع المهام وفق نمط Supervisor-Worker.
        """
        next_iteration = int(state.get("iteration", 0)) + 1
        max_iterations = int(state.get("max_iterations", self.loop_policy.max_iterations))

        if next_iteration >= max_iterations:
            fallback_answer = (
                "توقفت دورة التفكير تلقائياً بعد بلوغ الحد الأقصى للتكرار "
                f"({max_iterations}) لحماية الموارد. يرجى إعادة صياغة الطلب بشكل أكثر تحديداً."
            )
            return {
                "iteration": next_iteration,
                "next_step": "end",
                "answer": state.get("answer") or fallback_answer,
                "timeline": self._append_timeline(
                    state,
                    "supervisor",
                    {
                        "status": "terminated_due_to_iteration_limit",
                        "next_step": "end",
                        "reason": "MAX_ITERATIONS_GUARDRAIL",
                        "iteration": next_iteration,
                        "max_iterations": max_iterations,
                    },
                ),
            }

        decision = self.supervisor.decide(state)
        return {
            "iteration": next_iteration,
            "next_step": decision.next_step,
            "timeline": self._append_timeline(
                state,
                "supervisor",
                {"status": "routed", "next_step": decision.next_step, "reason": decision.reason},
            ),
        }

    async def _simple_responder_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة الرد البسيط للمحادثات العادية (Ordinary Chat).
        """
        from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

        if self._observer:
            await self._observer("phase_start", {"phase": "SIMPLE_CHAT", "agent": "Responder"})

        ai_client = get_ai_client()
        response = await ai_client.chat(state["objective"])
        answer_text = (
            str(response.message.content) if hasattr(response, "message") else str(response)
        )

        if self._observer:
            await self._observer("phase_completed", {"phase": "SIMPLE_CHAT", "agent": "Responder"})

        return {
            "execution": {
                "status": "success",
                "results": [{"tool": "chat", "result": answer_text}],
            },
            "answer": answer_text,
            "timeline": self._append_timeline(state, "simple_responder", {"status": "responded"}),
        }

    async def _reasoning_responder_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة الرد بالتفكير العميق (Reasoning Chat).
        """
        from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

        if self._observer:
            await self._observer(
                "phase_start", {"phase": "REASONING", "agent": "ReasoningResponder"}
            )

        ai_client = get_ai_client()

        # Here we simulate deep reasoning by giving a targeted prompt.
        prompt = f"قم بالتفكير المعمق خطوة بخطوة للرد على:\n{state['objective']}"
        response = await ai_client.chat(prompt)
        answer_text = (
            str(response.message.content) if hasattr(response, "message") else str(response)
        )

        if self._observer:
            await self._observer(
                "phase_completed", {"phase": "REASONING", "agent": "ReasoningResponder"}
            )

        return {
            "execution": {
                "status": "success",
                "results": [{"tool": "reasoning", "result": answer_text}],
            },
            "answer": answer_text,
            "timeline": self._append_timeline(state, "reasoning_responder", {"status": "reasoned"}),
        }

    async def _loop_controller_node(self, state: LangGraphState) -> dict[str, object]:
        """
        عقدة ضبط الحلقة لإعادة التخطيط استناداً إلى ملاحظات التدقيق.
        """
        if self._observer:
            await self._observer("phase_start", {"phase": "RE-PLANNING", "agent": "LoopController"})

        audit = state.get("audit") or {}
        feedback = ""
        if isinstance(audit, dict):
            feedback = str(audit.get("feedback") or "")
        shared_memory = {
            **state.get("shared_memory", {}),
            "audit_feedback": feedback,
            "iteration": state.get("iteration", 0),
        }

        if self._observer:
            await self._observer(
                "loop_start",
                {
                    "iteration": state.get("iteration", 0),
                    "chief_agent": "Strategist",
                    "graph_mode": "cognitive_loop",
                },
            )

        # ✅ Close the RE-PLANNING phase (prevents “hanging” timeline state)
        if self._observer:
            await self._observer(
                "phase_completed", {"phase": "RE-PLANNING", "agent": "LoopController"}
            )

        return {
            "plan": None,
            "design": None,
            "execution": None,
            "audit": None,
            "loop_detected": False,
            "shared_memory": shared_memory,
            "timeline": self._append_timeline(
                state,
                "loop_controller",
                {"status": "replan", "iteration": state.get("iteration", 0)},
            ),
        }
