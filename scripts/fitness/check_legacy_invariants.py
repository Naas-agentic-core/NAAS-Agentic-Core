#!/usr/bin/env python3
"""Legacy-workflow invariants gate (D-173 Stage 1).

Table-driven, stdlib-only replacement for the ~22 single-issue/step GitHub
workflows deleted in D-173 (iss-*.yml, microservices-step*.yml,
microservices-transition.yml, microservices-d045-user-routing.yml,
streaming-fix*.yml, ai-quality-gate.yml, bac2016-knowledge-gate.yml).

Every FATAL `grep -q` structural assertion those workflows carried was
transcribed here (polarity-aware extractor over the workflow sources + a
hand-transcribed remainder for loops / derived-variable / scoped checks).
WARN-only steps were intentionally NOT transcribed (they never failed CI).
The pytest suites those workflows ran are covered by ci.yml's
test-monolith / test-microservices jobs (verified in D-173).

DROPPED assertions (superseded by later ADRs — documented, not silent):
  - iss-069 `reasoning→content` redirect asserts (ai_client reasoning_chunks/
    reasoning_only_response): REVERSED by D-067 («No reasoning→content leak»).
  - iss-070 local_graph math-routing asserts (_detect_subject/_enrich_question/
    invoke_math_pipeline/subject == "math"): superseded by D-097 (math UI
    preempt disabled) + D-080 contract now lives in conversation_service tests.
  - iss-052 doc-content asserts on docs/ai_skills/bac-exercise-explanation.md
    (ExamBadge/katex/…): superseded by D-156 doc consolidation; the UI contract
    is enforced by frontend node tests.
  - step12 `add_edge intent→response` topology assert: graph became
    intent→context→response (current topology asserted instead).
  - d045 supervisor `launch_<svc> … 6543→5432` block check: WARN-only in the
    original (never fatal).

REATTRIBUTED (shell `$GRAPH`/`$F` variable collisions in the originals bound
patterns to the wrong file; D-173 re-verified each against the tree):
  - conversation-graph node/subject/math-routing asserts moved from
    local_graph.py to conversation_graph.py; math_pipeline asserts replaced by
    the real D-080 topology (classify/solve/normalize/enrich);
  - greeting-fastpath assert moved from graph/search.py to graph/main.py
    (ChatFallbackNode's home); stale 2-node `intent→response` edge assert
    replaced by the live `context_node→response_node` edge.

Rule types:
  REQUIRED[path]        -> every pattern must match the file
  ANY_OF                -> at least one alternative matches
  FORBIDDEN_NONCOMMENT  -> pattern must NOT appear outside full-line comments
  LINE_SCOPED_FORBIDDEN -> lines containing anchor must not contain banned
  SECTION_REQUIRED      -> text between two markers must contain pattern

Matching: plain substring first; on miss the pattern is retried as a regex
(re.M) with BRE alternation `\\|` converted to `|`.

Maintenance law (D-173): when a file listed here is decomposed (verbatim
extraction), update the path in the same commit — an assertion is never
dropped without an ADR note in this docstring.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED: dict[str, list[str]] = {
    ".devcontainer/supervisor.sh": [
        "8001",  # microservices-step5-user-service.yml
        "8002",  # microservices-step6-planning-agent.yml
        "8003",  # microservices-step12-conversation-service.yml
        "8007",  # microservices-step7-research-agent.yml
        "8008",  # microservices-step8-reasoning-agent.yml
        "ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR.*true",  # microservices-d045-user-routing.yml
        'OUTBOX_RELAY_ENABLED="true"',  # microservices-step5-user-service.yml
        "STEP 4H\\|4H",  # microservices-step8-reasoning-agent.yml
        "STEP 4J",  # microservices-step12-conversation-service.yml
        "export ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR",  # microservices-d045-user-routing.yml
        "export CODESPACES",  # microservices-d045-user-routing.yml
        "export ORCHESTRATOR_CHAT_ENDPOINT",  # microservices-d045-user-routing.yml
        "export ORCHESTRATOR_SERVICE_URL",  # microservices-d045-user-routing.yml
        "export PLANNING_AGENT_URL",  # microservices-d045-user-routing.yml
        "export REASONING_AGENT_URL",  # microservices-d045-user-routing.yml
        "export RESEARCH_AGENT_URL",  # microservices-d045-user-routing.yml
        "export USER_SERVICE_URL",  # microservices-d045-user-routing.yml
        "launch_conversation_service",  # microservices-step12-conversation-service.yml
        "launch_planning_agent",  # microservices-step6-planning-agent.yml
        "launch_reasoning_agent",  # microservices-step8-reasoning-agent.yml
        "launch_research_agent",  # microservices-step7-research-agent.yml
        "launch_user_service",  # microservices-step5-user-service.yml
        "localhost:8006",  # microservices-d045-user-routing.yml
        "orchestrator",  # microservices-d045-user-routing.yml
        "planning",  # microservices-d045-user-routing.yml
        "postgresql+asyncpg\\|asyncpg",  # microservices-d045-user-routing.yml
        "user",  # microservices-d045-user-routing.yml
        "uvicorn microservices.planning_agent",  # microservices-step6-planning-agent.yml
        "uvicorn microservices.user_service",  # microservices-step5-user-service.yml
    ],
    ".ona/automations.yaml": [
        "8007",  # microservices-step7-research-agent.yml
        "8008",  # microservices-step8-reasoning-agent.yml
        "docker-compose-stack",  # microservices-step6-planning-agent.yml
        "planning-agent:",  # microservices-step6-planning-agent.yml
        "reasoning-agent:",  # microservices-step8-reasoning-agent.yml
        "research-agent",  # microservices-step7-research-agent.yml
        "restart-reasoning-agent",  # microservices-step8-reasoning-agent.yml
        "run-step6-tests",  # microservices-step6-planning-agent.yml
        "run-step7-tests",  # microservices-step7-research-agent.yml
        "run-step8-tests",  # microservices-step8-reasoning-agent.yml
        "verify-step6-planning-agent",  # microservices-step6-planning-agent.yml
        "verify-step7-research-agent",  # microservices-step7-research-agent.yml
        "verify-step8-reasoning-agent",  # microservices-step8-reasoning-agent.yml
    ],
    "AGENTS.md": [
        "bac-exercise-explanation",  # bac2016-knowledge-gate.yml
    ],
    "CLAUDE.md": [
        "ISS-052",  # iss-052-bac-display-streaming.yml
    ],
    "app/core/ai_config.py": [
        'PRIMARY = _resolve_primary_model("openai/gpt-oss-20b:free")',  # iss-079-catastrophic-trio-gate.yml
    ],
    "app/services/capabilities/exercise_retrieval.py": [
        '"أريد شرح"',  # iss-075-greeting-explanation-gate.yml
        '"اشرح للسؤال"\\|"شرح للسؤال"\\|"اشرح للجزء"\\|"اشرح للفقرة"',  # iss-075-greeting-explanation-gate.yml
        '"شرح مفصل"',  # iss-075-greeting-explanation-gate.yml
        '"ممكن تشرح"',  # iss-075-greeting-explanation-gate.yml
    ],
    "app/services/chat/local_graph.py": [
        "LaTeX",  # ai-quality-gate.yml
        "_CHAT_META_PATTERNS",  # iss-075-greeting-explanation-gate.yml
        "_EXERCISE_EXPLANATION_SYSTEM_PROMPT",  # ai-quality-gate.yml
        "_FOREIGN_REPLACEMENTS",  # iss-075-greeting-explanation-gate.yml
        "_GREETING_PATTERNS",  # iss-075-greeting-explanation-gate.yml
        "_SYSTEM_PROMPTS",  # iss-070-math-pipeline-gate.yml
        "_sanitize_local_graph_response",  # iss-075-greeting-explanation-gate.yml
        "boxed",  # iss-070-math-pipeline-gate.yml
        "chat",  # iss-070-math-pipeline-gate.yml
        "educational",  # iss-070-math-pipeline-gate.yml
        "general",  # iss-070-math-pipeline-gate.yml
        "النموذجية",  # ai-quality-gate.yml
        "عليكم",  # iss-075-greeting-explanation-gate.yml
    ],
    "app/services/skills/__init__.py": [
        "GreetingSkill",  # iss-079-catastrophic-trio-gate.yml
        "MathSkill",  # iss-074-latex-stream-normalizer-gate.yml
    ],
    "app/services/skills/greeting_skill.py": [
        "_EDUCATIONAL_BLOCKERS",  # iss-079-catastrophic-trio-gate.yml
        "class GreetingSkill",  # iss-079-catastrophic-trio-gate.yml
        "class GreetingSkillFailure",  # iss-079-catastrophic-trio-gate.yml
        "class GreetingSkillInput",  # iss-079-catastrophic-trio-gate.yml
        "class GreetingSkillOutput",  # iss-079-catastrophic-trio-gate.yml
        "skill.greeting.invocations.total",  # iss-079-catastrophic-trio-gate.yml
    ],
    "app/telemetry/path_observer.py": [
        "_GREETING_PATTERNS",  # iss-075-greeting-explanation-gate.yml
        "عليكم",  # iss-075-greeting-explanation-gate.yml
    ],
    "docker-compose.step6.yml": [
        "8002",  # microservices-step6-planning-agent.yml
        "OPENROUTER_API_KEY",  # microservices-step6-planning-agent.yml
    ],
    "microservices/conversation_service/main.py": [
        '"/chat/message"',  # microservices-step12-conversation-service.yml
        '"/chat/ws"',  # microservices-step12-conversation-service.yml
        '"/health"',  # microservices-step12-conversation-service.yml
        '"/metrics"',  # microservices-step12-conversation-service.yml
    ],
    "microservices/conversation_service/prom_metrics.py": [
        "CollectorRegistry()",  # microservices-step12-conversation-service.yml
        "cogniforge_conversation_active_connections",  # reclassified(step5/step12)
        "cogniforge_conversation_db_operations_total",  # reclassified(step5/step12)
        "cogniforge_conversation_graph_duration_seconds",  # reclassified(step5/step12)
        "cogniforge_conversation_graph_errors_total",  # reclassified(step5/step12)
        "cogniforge_conversation_graph_invocations_total",  # reclassified(step5/step12)
        "cogniforge_conversation_messages_total",  # reclassified(step5/step12)
        "cogniforge_conversation_request_duration_seconds",  # reclassified(step5/step12)
        "cogniforge_conversation_requests_total",  # reclassified(step5/step12)
        "cogniforge_conversation_session_duration_seconds",  # reclassified(step5/step12)
        "cogniforge_conversation_sessions_total",  # reclassified(step5/step12)
        "cogniforge_conversation_startup_info",  # reclassified(step5/step12)
        "def get_metrics_output",  # reclassified(step5/step12)
        "def record_db_operation",  # reclassified(step5/step12)
        "def record_graph_error",  # reclassified(step5/step12)
        "def record_graph_invocation",  # reclassified(step5/step12)
        "def record_message",  # reclassified(step5/step12)
        "def record_request",  # reclassified(step5/step12)
        "def record_session",  # reclassified(step5/step12)
        "def record_ws_connection",  # reclassified(step5/step12)
        "def set_startup_info",  # reclassified(step5/step12)
        "registry=REGISTRY",  # microservices-step12-conversation-service.yml
    ],
    "microservices/conversation_service/src/conversation_graph.py": [
        '"subject"',  # reattributed(iss-070/step12 $GRAPH)
        "_detect_subject",  # reattributed(iss-070/step12 $GRAPH)
        "_enrich_question",  # reattributed(iss-070/step12 $GRAPH)
        "async def intent_node",  # reattributed(iss-070/step12 $GRAPH)
        "async def context_node",  # reattributed(iss-070/step12 $GRAPH)
        "async def response_node",  # reattributed(iss-070/step12 $GRAPH)
        "invoke_math_pipeline",  # reattributed(iss-070/step12 $GRAPH)
        'subject == "math"',  # reattributed(iss-070/step12 $GRAPH)
        'add_edge("context_node", "response_node")',  # reattributed(iss-070/step12 $GRAPH)
        "ConversationState",  # microservices-step12-conversation-service.yml
        "OPENROUTER_API_KEY",  # microservices-step12-conversation-service.yml
        "StateGraph",  # microservices-step12-conversation-service.yml
        "TimeoutError",  # microservices-step12-conversation-service.yml
        "_CYRILLIC_REPLACEMENTS",  # iss-074-latex-stream-normalizer-gate.yml
        '_DEFAULT_MODEL = "openai/gpt-oss-20b:free"',  # iss-079-catastrophic-trio-gate.yml
        "_build_fallback_response",  # microservices-step12-conversation-service.yml
        "_normalize_latex_response",  # iss-071-latex-normalize-gate.yml
        "_strip_chat_meta_narration",  # iss-074-latex-stream-normalizer-gate.yml
        "add_edge.*START.*intent_node",  # microservices-step12-conversation-service.yml
        "add_edge.*intent_node.*context_node",  # reclassified(step5/step12)
        "add_edge.*response_node.*END",  # microservices-step12-conversation-service.yml
        "add_node.*intent_node",  # microservices-step12-conversation-service.yml
        "add_node.*response_node",  # microservices-step12-conversation-service.yml
        "asyncio.wait_for",  # microservices-step12-conversation-service.yml
        "record_graph_error",  # microservices-step12-conversation-service.yml
        "record_graph_invocation",  # microservices-step12-conversation-service.yml
    ],
    "microservices/conversation_service/src/math_pipeline.py": [
        "async def classify_node",  # D-080 topology (replaces misattributed rows)
        "async def solve_node",  # D-080 topology (replaces misattributed rows)
        "async def normalize_node",  # D-080 topology (replaces misattributed rows)
        "async def enrich_node",  # D-080 topology (replaces misattributed rows)
        "MathPipelineState",  # iss-070-math-pipeline-gate.yml
        "StateGraph",  # iss-070-math-pipeline-gate.yml
        '_DEFAULT_MODEL = "openai/gpt-oss-20b:free"',  # iss-079-catastrophic-trio-gate.yml
        "_SYSTEM_PROMPT_ECHO_MARKERS",  # iss-074-latex-stream-normalizer-gate.yml
        "_build_fallback_solution",  # iss-070-math-pipeline-gate.yml
        "_clean_foreign_scripts",  # iss-074-latex-stream-normalizer-gate.yml
        "_strip_meta_prefix",  # iss-074-latex-stream-normalizer-gate.yml
        "boxed",  # iss-070-math-pipeline-gate.yml
        "complex",  # iss-070-math-pipeline-gate.yml
        "def _normalize_latex",  # iss-071-latex-normalize-gate.yml
        "derivative",  # iss-070-math-pipeline-gate.yml
        "differential_eq",  # iss-070-math-pipeline-gate.yml
        "equation",  # iss-070-math-pipeline-gate.yml
        "function_study",  # iss-070-math-pipeline-gate.yml
        "geometry",  # iss-070-math-pipeline-gate.yml
        "integral",  # iss-070-math-pipeline-gate.yml
        "limit",  # iss-070-math-pipeline-gate.yml
        "matrix",  # iss-070-math-pipeline-gate.yml
        'msg.get("content") or msg.get("reasoning")',  # iss-071-latex-normalize-gate.yml
        "normalize_node",  # iss-071-latex-normalize-gate.yml
        "probability",  # iss-070-math-pipeline-gate.yml
        "sequence",  # iss-070-math-pipeline-gate.yml
        "العربية الفصحى",  # iss-070-math-pipeline-gate.yml
    ],
    "microservices/orchestrator_service/main.py": [
        '"/metrics"',  # microservices-step4.yml
        "checkpointer_backend",  # microservices-step10-postgres-checkpointer.yml
        "pipeline_enabled=True",  # microservices-step9-skills-pipeline.yml
    ],
    "microservices/orchestrator_service/requirements.txt": [
        "prometheus-client",  # microservices-step4.yml
    ],
    "microservices/orchestrator_service/src/api/routes.py": [
        "/checkpointer/status",  # microservices-step10-postgres-checkpointer.yml
        "/compose",  # microservices-step10-postgres-checkpointer.yml
    ],
    "microservices/orchestrator_service/src/core/ai_config.py": [
        "PRIMARY = _resolve_primary_model(AvailableModels.GPT_OSS_20B_FREE)",  # iss-079-catastrophic-trio-gate.yml
    ],
    "microservices/orchestrator_service/src/core/config.py": [
        '"8002"',  # microservices-step9-skills-pipeline.yml
        '"8007"',  # microservices-step9-skills-pipeline.yml
        '"8008"',  # microservices-step9-skills-pipeline.yml
    ],
    "microservices/orchestrator_service/src/core/database.py": [
        "_InstrumentedCheckpointer",  # microservices-step10-postgres-checkpointer.yml
        "_build_psycopg_conninfo",  # microservices-step10-postgres-checkpointer.yml
        "async def aget",  # microservices-step10-postgres-checkpointer.yml
        "async def aput",  # microservices-step10-postgres-checkpointer.yml
        "async def setup",  # microservices-step10-postgres-checkpointer.yml
        "non-fatal\\|non_fatal",  # microservices-step10-postgres-checkpointer.yml
    ],
    "microservices/orchestrator_service/src/core/prom_metrics.py": [
        "checkpointer_backend",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_active_threads",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_backend_info",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_duration_seconds",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_errors_total",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_reads_total",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_checkpointer_writes_total",  # microservices-step10-postgres-checkpointer.yml
        "cogniforge_pipeline_active_gauge",  # microservices-step9-skills-pipeline.yml
        "cogniforge_pipeline_duration_seconds",  # microservices-step9-skills-pipeline.yml
        "cogniforge_pipeline_errors_total",  # microservices-step9-skills-pipeline.yml
        "cogniforge_pipeline_invocations_total",  # microservices-step9-skills-pipeline.yml
        "cogniforge_pipeline_skill_calls_total",  # microservices-step9-skills-pipeline.yml
        "pipeline_enabled",  # microservices-step9-skills-pipeline.yml
    ],
    "microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py": [
        "LatexStreamNormalizer\\|normalize_latex",  # iss-074-latex-stream-normalizer-gate.yml
    ],
    "microservices/orchestrator_service/src/services/overmind/graph/nodes.py": [
        # D-173 Stage 2c: node classes (ChatFallbackNode, …) moved main.py → nodes.py
        "get_greeting_fastpath_response",  # iss-076 (ChatFallbackNode)
        "LatexStreamNormalizer\\|normalize_latex",  # iss-074-latex-stream-normalizer-gate.yml
    ],
    "microservices/orchestrator_service/src/services/overmind/graph/search.py": [
        "LatexStreamNormalizer\\|normalize_latex",  # iss-074-latex-stream-normalizer-gate.yml
        "sanitize_response",  # iss-076-response-sanitizer-gate.yml
    ],
    "microservices/orchestrator_service/src/services/overmind/response_sanitizer.py": [
        "def get_greeting_fastpath_response",  # iss-076-response-sanitizer-gate.yml
        "def sanitize_response",  # iss-076-response-sanitizer-gate.yml
    ],
    "microservices/orchestrator_service/src/services/skills_pipeline.py": [
        "ConnectError",  # microservices-step9-skills-pipeline.yml
        "X-Correlation-ID",  # microservices-step9-skills-pipeline.yml
        "async def run_skills_pipeline",  # microservices-step9-skills-pipeline.yml
        "asyncio.gather",  # microservices-step9-skills-pipeline.yml
    ],
    "microservices/planning_agent/main.py": [
        '"/metrics"',  # microservices-step6-planning-agent.yml
        "export_prometheus_text",  # microservices-step6-planning-agent.yml
        "set_startup_info",  # microservices-step6-planning-agent.yml
    ],
    "microservices/planning_agent/prom_metrics.py": [
        "cogniforge_planning_active_connections",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_db_duration_seconds",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_db_operations_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_dspy_errors_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_dspy_invocations_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_fallback_plans_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_plan_duration_seconds",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_plans_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_request_duration_seconds",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_requests_total",  # microservices-step6-planning-agent.yml
        "cogniforge_planning_startup_info",  # microservices-step6-planning-agent.yml
    ],
    "microservices/planning_agent/requirements.txt": [
        "prometheus-client",  # microservices-step6-planning-agent.yml
    ],
    "microservices/reasoning_agent/main.py": [
        '"/metrics"',  # microservices-step8-reasoning-agent.yml
        "export_prometheus_text",  # microservices-step8-reasoning-agent.yml
        'step.*8\\|"8"',  # microservices-step8-reasoning-agent.yml
    ],
    "microservices/reasoning_agent/prom_metrics.py": [
        "cogniforge_reasoning_active_connections",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_fallback_responses_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_invocation_duration_seconds",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_invocations_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_llm_calls_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_llm_errors_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_mcts_errors_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_mcts_expansions_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_request_duration_seconds",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_requests_total",  # microservices-step8-reasoning-agent.yml
        "cogniforge_reasoning_startup_info",  # microservices-step8-reasoning-agent.yml
    ],
    "microservices/reasoning_agent/requirements.txt": [
        "prometheus-client",  # microservices-step8-reasoning-agent.yml
    ],
    "microservices/reasoning_agent/src/ai_client.py": [],
    "microservices/research_agent/main.py": [
        '"/metrics"',  # microservices-step7-research-agent.yml
        "export_prometheus_text",  # microservices-step7-research-agent.yml
        "from microservices.research_agent import prom_metrics",  # microservices-step7-research-agent.yml
        "set_startup_info",  # microservices-step7-research-agent.yml
    ],
    "microservices/research_agent/prom_metrics.py": [
        "cogniforge_research_active_connections",  # microservices-step7-research-agent.yml
        "cogniforge_research_db_duration_seconds",  # microservices-step7-research-agent.yml
        "cogniforge_research_db_operations_total",  # microservices-step7-research-agent.yml
        "cogniforge_research_deep_research_total",  # microservices-step7-research-agent.yml
        "cogniforge_research_request_duration_seconds",  # microservices-step7-research-agent.yml
        "cogniforge_research_requests_total",  # microservices-step7-research-agent.yml
        "cogniforge_research_search_duration_seconds",  # microservices-step7-research-agent.yml
        "cogniforge_research_searches_total",  # microservices-step7-research-agent.yml
        "cogniforge_research_startup",  # microservices-step7-research-agent.yml
        "cogniforge_research_tavily_calls_total",  # microservices-step7-research-agent.yml
        "cogniforge_research_tavily_errors_total",  # microservices-step7-research-agent.yml
    ],
    "microservices/research_agent/requirements.txt": [
        "prometheus-client",  # microservices-step7-research-agent.yml
        "tavily-python",  # microservices-step7-research-agent.yml
    ],
    "microservices/user_service/main.py": [
        '"/metrics"',  # microservices-step5-user-service.yml
        "export_prometheus_text",  # microservices-step5-user-service.yml
        "set_startup_info",  # microservices-step5-user-service.yml
    ],
    "microservices/user_service/requirements.txt": [
        "prometheus-client>=0.20",  # microservices-step5-user-service.yml
    ],
    "microservices/user_service/src/core/prom_metrics.py": [
        "CollectorRegistry",  # reclassified(step5/step12)
        "cogniforge_user_auth_operations_total",  # reclassified(step5/step12)
        "cogniforge_user_db_operations_total",  # reclassified(step5/step12)
        "cogniforge_user_logins_total",  # reclassified(step5/step12)
        "cogniforge_user_registrations_total",  # reclassified(step5/step12)
        "cogniforge_user_requests_total",  # reclassified(step5/step12)
        "cogniforge_user_startup_info",  # reclassified(step5/step12)
        "export_prometheus_text",  # reclassified(step5/step12)
        "set_startup_info",  # reclassified(step5/step12)
    ],
    "observability/native/prometheus.yml": [
        "8002",  # microservices-step6-planning-agent.yml
        "8007",  # microservices-step7-research-agent.yml
        "8008",  # microservices-step8-reasoning-agent.yml
        "conversation-service",  # microservices-step12-conversation-service.yml
        "job_name: user-service",  # microservices-step5-user-service.yml
        "localhost:8001",  # microservices-step5-user-service.yml
        "localhost:8003",  # microservices-step12-conversation-service.yml
        "planning-agent",  # microservices-step6-planning-agent.yml
        "postgres-checkpointer",  # microservices-step10-postgres-checkpointer.yml
        "reasoning-agent",  # microservices-step8-reasoning-agent.yml
        "research-agent",  # microservices-step7-research-agent.yml
        "skills-pipeline",  # microservices-step9-skills-pipeline.yml
        'step.*"8"',  # microservices-step8-reasoning-agent.yml
        'step: "10"',  # microservices-step10-postgres-checkpointer.yml
        'step: "12"',  # microservices-step12-conversation-service.yml
        'step: "4"',  # microservices-step4.yml
        'step: "7"',  # microservices-step7-research-agent.yml
    ],
}
ANY_OF: list[tuple[str, list[str]]] = [
    # streaming-fix-gate.yml — noop filter present (either quote style).
    # D-173 Stage 3 (2026-08-13): hotspot `chat_stream_ws` فُكِّك — تصفية noop
    # انتقلت إلى `customer_chat_support/turn_lifecycle.py` (دورة الدور الواحدة)،
    # والحاجز يقرأها من هناك.
    ("app/api/routers/customer_chat_support/turn_lifecycle.py", ['"noop"', "'noop'"]),
    ("app/api/routers/admin.py", ['"noop"', "'noop'"]),
    # streaming-fix-002 — configurable orchestrator model
    (
        "microservices/orchestrator_service/src/services/llm/client.py",
        ["ORCHESTRATOR_LLM_MODEL", "deepseek"],
    ),
    (
        "app/core/ai_config.py",
        ["_resolve_primary_model", "OPENROUTER_PRIMARY_MODEL"],
    ),
    # microservices-step9 — /compose endpoint present (either quote style)
    (
        "microservices/orchestrator_service/src/api/routes.py",
        ['"/compose"', "'/compose'"],
    ),
    # microservices-step4 — outbox relay enabled in Ona automations
    (
        ".ona/automations.yaml",
        ['OUTBOX_RELAY_ENABLED="true"', "OUTBOX_RELAY_ENABLED=true"],
    ),
    # iss-074 — orchestrator leaf nodes import the LaTeX stream normalizer
    (
        "microservices/orchestrator_service/src/services/overmind/graph/search.py",
        ["LatexStreamNormalizer", "normalize_latex"],
    ),
    (
        "microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py",
        ["LatexStreamNormalizer", "normalize_latex"],
    ),
    (
        "microservices/orchestrator_service/src/services/overmind/graph/nodes.py",
        ["LatexStreamNormalizer", "normalize_latex"],
    ),  # D-173 Stage 2c: node classes moved to nodes.py
]

# Dead/banned models must not appear outside full-line comments (iss-070 +
# ai-quality-gate; reasoning ai_client must not reference the banned family).
FORBIDDEN_NONCOMMENT: list[tuple[str, list[str]]] = [
    (
        "app/core/ai_config.py",
        [
            '"google/gemini-2.0-flash-exp:free"',
            '"meta-llama/llama-3.2-11b-vision-instruct:free"',
        ],
    ),
    (
        "microservices/orchestrator_service/src/core/ai_config.py",
        [
            '"google/gemini-2.0-flash-exp:free"',
            '"meta-llama/llama-3.2-11b-vision-instruct:free"',
        ],
    ),
    ("microservices/reasoning_agent/src/ai_client.py", ["inclusionai"]),
    # streaming-fix-002 / ISS-069 — reasoning-only model must never be referenced
    ("app/core/ai_config.py", ["nemotron-3-nano-omni-30b-a3b-reasoning"]),
    # iss-071 — creative temperatures are forbidden in math/conversation LLM calls
    ("microservices/conversation_service/src/conversation_graph.py", []),
]

# (path, anchor_substring, banned_substrings)
LINE_SCOPED_FORBIDDEN: list[tuple[str, str, list[str]]] = [
    (
        "app/core/ai_config.py",
        "PRIMARY = _resolve_primary_model",
        ["inclusionai", "nemotron-3-nano-omni", "reasoning:free"],
    ),
    (
        "microservices/orchestrator_service/src/core/ai_config.py",
        "PRIMARY = _resolve_primary_model",
        ["inclusionai", "nemotron-3-nano-omni", "reasoning:free"],
    ),
    # ai-quality-gate — MCTS depth must stay 1 (ISS-068) + timeout sane
    (
        "microservices/reasoning_agent/src/services/reasoning_service.py",
        "strategy.execute",
        ["depth=2", "depth=3", "depth=4", "depth=5"],
    ),
    (
        "microservices/reasoning_agent/src/services/reasoning_service.py",
        "timeout=",
        ["timeout=300"],
    ),
    # iss-071 — temperature must stay low in math/conversation prompts
    (
        "microservices/conversation_service/src/conversation_graph.py",
        '"temperature"',
        ['"temperature": 0.6', '"temperature": 0.7', '"temperature": 0.8', '"temperature": 0.9'],
    ),
    (
        "microservices/conversation_service/src/math_pipeline.py",
        '"temperature"',
        [
            '"temperature": 0.4',
            '"temperature": 0.5',
            '"temperature": 0.6',
            '"temperature": 0.7',
            '"temperature": 0.8',
            '"temperature": 0.9',
        ],
    ),
    # step8 (ISS-039-B) — ai_service must stay a lazy singleton (no module-level import)
    (
        "microservices/reasoning_agent/main.py",
        "from microservices.reasoning_agent.src.services.ai_service import ai_service",
        ["import ai_service"],
    ),
]

# (path, start_marker, end_marker, required_pattern)
SECTION_REQUIRED: list[tuple[str, str, str, str]] = [
    # ai-quality-gate — educational prompt section must mandate LaTeX
    ("app/services/chat/local_graph.py", '"educational":', '"general":', "$$"),
]

# Hand-transcribed loop/derived checks (see docstring)
_EXTRA_REQUIRED: dict[str, list[str]] = {
    # streaming-fix-gate.yml (ISS-STREAM-001)
    # microservices-step10 — /checkpointer/status handler exposes backend
    "microservices/orchestrator_service/src/api/routes.py": [
        "delta_parts",
        "delta_parts.append",
        "ISS-STREAM-001",
        "/checkpointer/status",
        '"backend"',
    ],
    # iss080-conversation-spinner-gate.yml — D-068 markers
    "frontend/app/hooks/useAgentSocket.js": [
        "ISS-STREAM-001",
        "incoming.startsWith(current)",
        "current.endsWith(incoming)",
        "content ?",
        "isComplete: true",
        "ISS-080",
        "D-068",
        "setMessagesSafe = useCallback",
        "isComplete !== true",
    ],
    # streaming-fix-002-gate.yml (ISS-STREAM-002)
    "microservices/orchestrator_service/src/services/llm/client.py": [
        "def extract_stream_content",
        'hasattr(chunk, "choices")',
        "isinstance(chunk, dict)",
        "ISS-STREAM-002",
    ],
    # iss-076 — sanitize_response wired in orchestrator leaf nodes
    # (paths follow the node classes; update on decomposition — D-173 law)
    "microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py": [
        "extract_stream_content",
        "sanitize_response",
    ],
    "microservices/orchestrator_service/src/services/overmind/graph/search.py": [
        "extract_stream_content",
        "no-docs streaming",
        "sanitize_response",
    ],
    # microservices-step9 metric loop
    "microservices/orchestrator_service/src/core/prom_metrics.py": [
        "cogniforge_streaming_chunks_total",
        "cogniforge_streaming_chars_total",
        "cogniforge_streaming_sessions_total",
        "cogniforge_streaming_duration_seconds",
        "record_streaming_chunk",
        "record_streaming_session",
        "cogniforge_pipeline_invocations_total",
        "cogniforge_pipeline_duration_seconds",
        "cogniforge_pipeline_skill_calls_total",
        "cogniforge_pipeline_errors_total",
        "cogniforge_pipeline_active_gauge",
    ],
    "observability/grafana/dashboards/170-streaming-iss-stream-002.json": [
        "cogniforge-streaming-002",
    ],
    # iss-070 REQUIRED loop + ai-quality-gate prompt checks
    "app/services/chat/local_graph.py": [
        "$$",
        "boxed",
        "LaTeX",
        "العربية الفصحى",
        '"educational":',
        '"general":',
        '"chat":',
    ],
    # microservices-d045 — prometheus dependency per service requirements
    "microservices/orchestrator_service/requirements.txt": [],
    "microservices/user_service/requirements.txt": [],
    "microservices/planning_agent/requirements.txt": [],
    "microservices/conversation_service/requirements.txt": [],
    "microservices/research_agent/requirements.txt": [],
    "microservices/reasoning_agent/requirements.txt": [],
    "microservices/content_retrieval_skill/requirements.txt": [],
    # microservices-d045 — supervisor launches the core services
    ".devcontainer/supervisor.sh": [
        "launch_orchestrator_service",
        "launch_user_service",
        "launch_planning_agent",
    ],
}


# Composed-source checks (glob-based so future decomposition slices are covered
# automatically — mirrors the streaming-fix-gate originals).
COMPOSED_REQUIRED: list[tuple[str, list[str], list[str]]] = [
    # (label, [files/globs], [required patterns])
    (
        "tutor sources (client + brain + orchestrator mixins)",
        [
            "app/infrastructure/clients/orchestrator_client.py",
            "app/infrastructure/clients/orchestrator_client_support/*.py",  # D-256
            "app/services/skills/probability_tutor_brain.py",
            "app/services/skills/probability_brain/*.py",
            "app/infrastructure/clients/orchestrator/*.py",
        ],
        [
            "_PASSTHROUGH_EVENT_TYPES",
            "_TEXT_EVENT_TYPES",
            '"noop"',
            '"phase_start"',
            '"RUN_STARTED"',
        ],
    ),
    (
        "orchestrator api sources",
        ["microservices/orchestrator_service/src/api/*.py"],
        [
            ".astream(",
            '"custom"',
            '"updates"',
            "ISS-STREAM-002",
            "stream_mode=",
            "record_streaming_chunk",
        ],
    ),
]

# Generic parse checks folded from the step-gates (dashboard/YAML validity).
JSON_PARSE_GLOBS = ["observability/grafana/dashboards/*.json"]
YAML_PARSE_FILES = [
    ".ona/automations.yaml",
    "observability/native/prometheus.yml",
    "observability/compose/prometheus.yml",
    "docker-compose.yml",
]


def _matches(pattern: str, text: str) -> bool:
    if pattern in text:
        return True
    try:
        return re.search(pattern.replace(r"\|", "|"), text, re.M) is not None
    except re.error:
        return False


def main() -> int:
    failures: list[str] = []
    merged: dict[str, list[str]] = {}
    for table in (REQUIRED, _EXTRA_REQUIRED):
        for path, pats in table.items():
            merged.setdefault(path, []).extend(pats)

    for rel, patterns in sorted(merged.items()):
        fp = ROOT / rel
        if not fp.is_file():
            failures.append(f"missing file: {rel}")
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        for pat in patterns:
            if not _matches(pat, text):
                failures.append(f"{rel}: required pattern not found: {pat!r}")

    for rel, alternatives in ANY_OF:
        fp = ROOT / rel
        if not fp.is_file():
            failures.append(f"missing file: {rel}")
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        if not any(_matches(p, text) for p in alternatives):
            failures.append(f"{rel}: none of the alternatives found: {alternatives!r}")

    for rel, banned in FORBIDDEN_NONCOMMENT:
        fp = ROOT / rel
        if not fp.is_file():
            failures.append(f"missing file: {rel}")
            continue
        noncomment = "\n".join(
            ln
            for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines()
            if not ln.lstrip().startswith("#")
        )
        for pat in banned:
            if pat in noncomment:
                failures.append(f"{rel}: forbidden pattern present (non-comment): {pat!r}")

    for rel, anchor, banned in LINE_SCOPED_FORBIDDEN:
        fp = ROOT / rel
        if not fp.is_file():
            failures.append(f"missing file: {rel}")
            continue
        for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            if anchor in ln and not ln.lstrip().startswith("#"):
                for pat in banned:
                    if pat in ln:
                        failures.append(
                            f"{rel}: line with anchor {anchor!r} contains banned {pat!r}"
                        )

    for rel, start, end, pat in SECTION_REQUIRED:
        fp = ROOT / rel
        if not fp.is_file():
            failures.append(f"missing file: {rel}")
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        s = text.find(start)
        e = text.find(end, s + 1) if s != -1 else -1
        if s == -1 or e == -1:
            failures.append(f"{rel}: section markers not found: {start!r}..{end!r}")
        elif pat not in text[s:e]:
            failures.append(f"{rel}: section {start!r}..{end!r} missing {pat!r}")

    for label, sources, patterns in COMPOSED_REQUIRED:
        texts = []
        for pat in sources:
            for fp in sorted(ROOT.glob(pat)) if "*" in pat else [ROOT / pat]:
                if fp.is_file():
                    texts.append(fp.read_text(encoding="utf-8", errors="replace"))
        combined = "\n".join(texts)
        if not texts:
            failures.append(f"composed source empty: {label}")
            continue
        for pat in patterns:
            if not _matches(pat, combined):
                failures.append(f"composed [{label}]: required pattern not found: {pat!r}")

    import json as _json

    for g in JSON_PARSE_GLOBS:
        for fp in sorted(ROOT.glob(g)):
            try:
                _json.loads(fp.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"invalid JSON: {fp.relative_to(ROOT)}: {exc}")

    try:
        import yaml as _yaml  # type: ignore[import-untyped]
    except ImportError:
        _yaml = None
    if _yaml is not None:
        for rel in YAML_PARSE_FILES:
            fp = ROOT / rel
            if not fp.is_file():
                failures.append(f"missing file: {rel}")
                continue
            try:
                _yaml.safe_load(fp.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"invalid YAML: {rel}: {exc}")

    total = (
        sum(len(v) for v in merged.values())
        + len(ANY_OF)
        + sum(len(b) for _, b in FORBIDDEN_NONCOMMENT)
        + len(LINE_SCOPED_FORBIDDEN)
        + len(SECTION_REQUIRED)
        + sum(len(p) for _, _, p in COMPOSED_REQUIRED)
    )
    if failures:
        print(f"❌ legacy-invariants gate: {len(failures)} failure(s) of {total} checks")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ legacy-invariants gate: all {total} transcribed checks hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
