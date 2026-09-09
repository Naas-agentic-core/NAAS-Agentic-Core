/**
 * api.d.ts — أنواع مُولَّدة من عقود OpenAPI المُلتزَمة (D-185).
 *
 * ⚠️ مُولَّد آلياً — لا تُحرّره يدوياً.
 * المصدر: docs/contracts/openapi/*.json
 * التوليد: python scripts/contracts/generate_frontend_types.py
 *
 * لماذا: المستودع «API-first» لكن الواجهة كانت تقرأ كل حقل نصّياً بلا أي ربط
 * بالعقود — فأي تغيير في عقد خدمة لم يكن يُكتشَف إلا في المتصفح. هذه الأنواع
 * تجعل انحراف العقد خطأ ترجمة في CI (`npm run typecheck`).
 */

// ── api_gateway (CogniForge API Gateway) ─────────
export interface ApiGatewayValidationError { loc: string | number[]; msg: string; type: string }

// ── auditor_service (Auditor Microservice) ─────────
export interface AuditorServiceConsultRequest { situation: string; analysis: Record<string, unknown> }
export interface AuditorServiceConsultResponse { recommendation: string; confidence: number }
export interface AuditorServiceReviewRequest { result: Record<string, unknown>; original_objective: string; context?: Record<string, unknown> }
export interface AuditorServiceReviewResponse { approved: boolean; feedback: string; score: number; final_response: string }
export interface AuditorServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── content_retrieval_skill (content-retrieval-skill) ─────────
export interface ContentRetrievalSkillContentItemResponse { id: string; title: string; subject: string; year: string; tags: string[]; content_preview: string; file_path: string }
export interface ContentRetrievalSkillDeepDiveResponse { formula: string; explanation: string; why_zero: string }
export interface ContentRetrievalSkillHealthResponse { status: string; service: string; step: string; kb_path: string; kb_files: number; version: string }
export interface ContentRetrievalSkillImpossibleCaseRequest { bag_count: number; requested: number; item_name?: string }
export interface ContentRetrievalSkillImpossibleCaseResponse { is_impossible: boolean; case_type: string; stage_1?: ContentRetrievalSkillStage1SceneResponse | null; stage_2?: ContentRetrievalSkillStage2QuestionResponse | null; stage_3?: ContentRetrievalSkillStage3AnimationResponse | null; stage_4?: ContentRetrievalSkillStage4MessageResponse | null; deep_dive?: ContentRetrievalSkillDeepDiveResponse | null }
export interface ContentRetrievalSkillRetrieveRequest { question: string; subject?: string | null; year?: string | null; max_results?: number }
export interface ContentRetrievalSkillRetrieveResponse { intent: string; intent_confidence: number; intent_reason: string; items: ContentRetrievalSkillContentItemResponse[]; total: number; duration_ms: number; kb_path: string; query_subject: string | null; query_year: string | null }
export interface ContentRetrievalSkillStage1SceneResponse { bag_count: number; requested: number; bag_label: string; request_label: string }
export interface ContentRetrievalSkillStage2QuestionResponse { question: string }
export interface ContentRetrievalSkillStage3AnimationResponse { animation: string; duration_ms: number }
export interface ContentRetrievalSkillStage4MessageResponse { message: string; tone: string }
export interface ContentRetrievalSkillValidationError { loc: string | number[]; msg: string; type: string }

// ── conversation_service (CogniForge Conversation Service) ─────────
export interface ConversationServiceChatRequest { question: string; thread_id?: string | null; history?: Record<string, unknown>[]; correlation_id?: string | null }
export interface ConversationServiceChatResponse { response: string; intent: string; subject?: string; thread_id: string; correlation_id: string; graph_ready: boolean; step?: string; ui_component?: Record<string, unknown> | null }
export interface ConversationServiceHealthResponse { status: string; service: string; version: string; step: string; graph_ready: boolean; ws_enabled: boolean }
export interface ConversationServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── foundations_service (foundations-service) ─────────
export interface FoundationsServiceComputeRequest { domain: string; operation: string; args?: Record<string, unknown> }
export interface FoundationsServiceComputeResponse { domain: string; operation: string; ok: boolean; result?: unknown; error?: string | null; duration_ms: number }
export interface FoundationsServiceHealthResponse { status: string; service: string; step: string; version: string; domains: string[]; llm_backend: string }
export interface FoundationsServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── memory_agent (Memory Agent) ─────────
export interface MemoryAgentConcept { concept_id: string; name_ar: string; name_en?: string; description?: string; subject?: string; level?: string; difficulty?: number; tags?: string[] }
export interface MemoryAgentHealthResponse { service: string; status: string; database?: string | null }
export interface MemoryAgentMemoryCreateRequest { content: string; tags?: string[] }
export interface MemoryAgentMemoryResponse { entry_id: string; content: string; tags: string[] }
export interface MemoryAgentMemorySearchFilters { tags?: string[] }
export interface MemoryAgentMemorySearchRequest { query?: string; filters?: MemoryAgentMemorySearchFilters; limit?: number }
export interface MemoryAgentPathRequest { from_concept: string; to_concept: string }
export interface MemoryAgentReadinessRequest { concept_id: string; mastery_levels: Record<string, unknown> }
export interface MemoryAgentReadinessResponse { concept_id: string; concept_name: string; is_ready: boolean; readiness_score: number; missing_prerequisites: string[]; weak_prerequisites: string[]; recommendation: string }
export interface MemoryAgentValidationError { loc: string | number[]; msg: string; type: string }

// ── monolith_api (CogniForge) ─────────
export interface MonolithApiAEKProcessRequest { question: string; history?: Record<string, unknown>[]; state?: MonolithApiAEKRuntimeState | null; learner_capability?: MonolithApiLearnerCapability }
export interface MonolithApiAEKProcessResponse { channel_a: Record<string, unknown>; channel_b: Record<string, unknown>; updated_state: Record<string, unknown>; processing_ms: number }
export interface MonolithApiAEKRuntimeState { current_cognitive_state?: MonolithApiCognitiveState; current_cognitive_intent?: MonolithApiCognitiveIntent; current_exercise_scope?: MonolithApiExerciseScope; topic_lock?: boolean; current_step_index?: number; cognitive_load_index?: number; learner_capability?: MonolithApiLearnerCapability; current_runtime_mode?: string; transition_log?: string[] }
export interface MonolithApiAEKStatesResponse { states: string[]; transitions: Record<string, unknown>; intents: string[]; scopes: string[] }
export interface MonolithApiAIOpsMetricsResponse { anomaly_score: number; self_healing_events?: number; predictions?: Record<string, unknown> | null }
export interface MonolithApiAdminCreateUserRequest { full_name: string; email: string; password: string; is_admin?: boolean }
export interface MonolithApiAdminUserCountResponse { count: number }
export interface MonolithApiAlertResponse { id: string; severity: string; message: string; timestamp: string; status: string }
export interface MonolithApiAuthResponse { access_token: string; refresh_token?: string | null; token_type?: string; user: MonolithApiUserResponse; status?: string; landing_path?: string }
export interface MonolithApiChangePasswordRequest { current_password: string; new_password: string }
export type MonolithApiCognitiveIntent = string;
export type MonolithApiCognitiveState = string;
export interface MonolithApiCohortItem { cohort_date: string; size: number; retained: Record<string, unknown> }
export interface MonolithApiComputeRequest { domain: string; operation: string; args?: Record<string, unknown> }
export interface MonolithApiComputeResponse { domain: string; operation: string; ok: boolean; result?: unknown; error?: string | null }
export interface MonolithApiConceptIllusionOut { concept_id: string; confidence: number; durable_mastery: number; gap: number; quadrant: string; observations: number }
export interface MonolithApiConceptMeasurement { concept_id: string; confidence: number; durable_mastery: number; unaided_observations: number; elapsed_days?: number | null; stability?: number | null }
export interface MonolithApiConceptProgressItem { concept_id: string; title: string; subject: string; interactions: number; assisted_mastery: number; durable_mastery: number; illusion_gap: number; improved: boolean; fragile: boolean }
export interface MonolithApiContentItemResponse { id: string; type: string; title?: string | null; level?: string | null; subject?: string | null; year?: number | null; lang?: string | null; relevance?: number | null; matched_terms?: string[] }
export interface MonolithApiContentSearchResponse { items: MonolithApiContentItemResponse[]; ranking?: string }
export interface MonolithApiConversationDetailsResponse { conversation_id: number | string; title?: string | null; messages: MonolithApiMessageResponse[]; metadata?: Record<string, unknown> | null }
export interface MonolithApiConversationSummaryResponse { id: number | string; conversation_id?: number | string | null; title?: string | null; created_at?: string | null; updated_at?: string | null; message_count?: number }
export interface MonolithApiCustomerConversationDetails { conversation_id: number; title: string; messages: MonolithApiCustomerMessageOut[] }
export interface MonolithApiCustomerConversationSummary { id: number; conversation_id: number; title: string; created_at: string; updated_at?: string | null }
export interface MonolithApiCustomerMessageOut { role: string; content: string; created_at: string; policy_flags?: Record<string, unknown> | null; ui_component?: Record<string, unknown> | null }
export interface MonolithApiDataContractRequest { domain: string; schema_definition: Record<string, unknown>; sla?: Record<string, unknown> | null; owner: string }
export interface MonolithApiDataContractResponse { id?: string | number | null; domain: string; schema_definition: Record<string, unknown>; status?: string }
export interface MonolithApiDataMeshMetricsResponse { active_contracts?: number; throughput?: number; error_rate?: number }
export interface MonolithApiDueReviewItem { concept_id: string; title: string; due_at: string; overdue_days: number; stability: number; difficulty: number; lapses: number; exam_weight: number }
export interface MonolithApiDueReviewResponse { total: number; stream: string; generated_at: string; items: MonolithApiDueReviewItem[] }
export interface MonolithApiEndpointAnalyticsResponse { path: string; avg_latency: number; p95_latency: number; error_count?: number; total_calls?: number }
export interface MonolithApiEntitlementResponse { active: boolean; plan?: string | null; expires_at?: string | null }
export interface MonolithApiErrorMetrics { error_rate: number; error_count: number }
export type MonolithApiExerciseScope = string;
export interface MonolithApiFunnelStepItem { event_name: string; users: number; conversion_from_start: number; conversion_from_previous: number }
export interface MonolithApiGitOpsMetricsResponse { status: string; sync_rate: number; last_sync?: string | null }
export interface MonolithApiGoldenSignalsResponse { latency: MonolithApiLatencyMetrics; traffic: MonolithApiTrafficMetrics; errors: MonolithApiErrorMetrics; saturation: MonolithApiSaturationMetrics }
export interface MonolithApiHealthComponent { status: string; details?: Record<string, unknown> | null }
export interface MonolithApiHealthzResponse { status: string; detail?: string | null }
export interface MonolithApiIllusionGapInput { stream: string; measurements?: MonolithApiConceptMeasurement[] }
export interface MonolithApiIllusionGapReport { stream: string; index?: number | null; concepts?: MonolithApiConceptIllusionOut[]; dangerous?: MonolithApiConceptIllusionOut[]; quadrants?: Record<string, unknown>; immature_suppressed?: number; reason?: string }
export interface MonolithApiIssueRequest { plan?: string; duration_days?: number; quantity?: number }
export interface MonolithApiIssueResponse { codes: string[] }
export interface MonolithApiLatencyMetrics { p50: number; p95: number; p99: number; "p99.9": number; avg: number }
export type MonolithApiLearnerCapability = string;
export interface MonolithApiLinkCodeResponse { link_code: string }
export interface MonolithApiLinkRequest { link_code: string }
export interface MonolithApiLinkedStudentItem { student_user_id: number; linked_since: string }
export interface MonolithApiLogoutRequest { refresh_token: string }
export interface MonolithApiMCPRequest { action?: string; tool_name?: string | null; arguments?: Record<string, unknown> | null }
export interface MonolithApiMessageResponse { id?: number | null; role: string; content: string; timestamp?: string | null }
export interface MonolithApiNotationRequest { question: string }
export interface MonolithApiNotationResponse { found: boolean; symbol?: string | null; title?: string | null; definition?: string | null; example?: string | null; concept_id?: string | null }
export interface MonolithApiPasswordResetConfirmRequest { token: string; new_password: string }
export interface MonolithApiPasswordResetRequest { email: string }
export interface MonolithApiPasswordResetResponse { status?: string; reset_token?: string | null; expires_in?: number | null }
export interface MonolithApiPerformanceSnapshotResponse { cpu_usage: number; memory_usage: number; active_requests: number }
export interface MonolithApiProfileUpdateRequest { full_name?: string | null; email?: string | null }
export interface MonolithApiQuestionRequest { question: string }
export interface MonolithApiReasonRequest { question?: string; premises?: string[] | null; conclusion?: string | null; edges?: string[][] | null; classify_pair?: string[] | null; counterfactual_node?: string | null; instances?: Record<string, unknown>[] | null; sequence?: number[] | null; source?: Record<string, unknown> | null; target?: Record<string, unknown> | null; relations?: string[][] | null; dynamics?: string[][] | null; concept_name?: string | null; compute?: Record<string, unknown> | null }
export interface MonolithApiReasonResponse { question: string; modes: string[]; results: Record<string, unknown>; narrative: string }
export interface MonolithApiReauthRequest { password: string }
export interface MonolithApiReauthResponse { reauth_token: string; expires_in: number }
export interface MonolithApiRedeemRequest { code: string }
export interface MonolithApiRedeemResponse { plan: string; expires_at: string; already_redeemed_by_you?: boolean }
export interface MonolithApiRefineRequest { text: string; question?: string; intent?: string }
export interface MonolithApiRefineResponse { text: string; applied_steps: string[]; failed_steps: string[] }
export interface MonolithApiRefreshRequest { refresh_token: string }
export interface MonolithApiRegisterResponse { status?: string; message: string; user: MonolithApiUserResponse }
export interface MonolithApiRetentionResponse { generated_for: string; horizons: number[]; overall: Record<string, unknown>; cohorts: MonolithApiCohortItem[] }
export interface MonolithApiRetrieveRequest { query: string; top_k?: number; top_n?: number; documents?: string[] | null; filters?: Record<string, unknown> | null }
export interface MonolithApiRoleAssignmentRequest { role_name: string; reauth_password?: string | null; reauth_token?: string | null; justification?: string | null }
export interface MonolithApiSaturationMetrics { active_requests: number; queue_depth: number; active_spans?: number | null; resource_utilization?: number | null }
export interface MonolithApiSkillsListResponse { total: number; active: number; flagged: number; skills: Record<string, unknown>[] }
export interface MonolithApiStatusUpdateRequest { status: MonolithApiUserStatus }
export interface MonolithApiSystemInfoResponse { version: string; environment: string; details?: Record<string, unknown> | null }
export interface MonolithApiTokenGenerateResponse { access_token: string; refresh_token: string; token_type?: string }
export interface MonolithApiTokenPair { access_token: string; refresh_token: string; token_type?: string }
export interface MonolithApiTokenRequest { user_id?: number | null; scopes?: string[] }
export interface MonolithApiTokenVerifyRequest { token?: string | null }
export interface MonolithApiTokenVerifyResponse { status: string; data: Record<string, unknown> }
export interface MonolithApiTraceResponse { trace_id: string; start_time: number; end_time?: number | null; total_duration_ms?: number | null; error_count?: number; critical_path_ms?: number | null; spans?: MonolithApiTraceSpanResponse[]; correlated_logs?: Record<string, unknown>[] }
export interface MonolithApiTraceSpanResponse { span_id: string; parent_span_id?: string | null; operation_name: string; service_name: string; start_time: number; end_time?: number | null; duration_ms?: number | null; status: string; tags?: Record<string, unknown>; metrics?: Record<string, unknown>; error_message?: string | null }
export interface MonolithApiTrafficMetrics { requests_per_second: number; total_requests: number }
export interface MonolithApiUserOut { id: number; email: string; full_name: string; is_active: boolean; status: MonolithApiUserStatus; roles?: string[] }
export interface MonolithApiUserResponse { id: number; name: string; full_name?: string | null; email: string; is_admin?: boolean }
export type MonolithApiUserStatus = string;
export interface MonolithApiValidationError { loc: string | number[]; msg: string; type: string }
export interface MonolithApiVisualPedagogyRequest { question: string; history?: Record<string, unknown>[] | null }
export interface MonolithApiWeeklyReportResponse { student_user_id: number; period_start: string; period_end: string; active_days: number; current_streak: number; longest_streak: number; sessions: number; concepts_practised: number; reviews_completed: number; reviews_due_now: number; strongest: MonolithApiConceptProgressItem[]; needs_attention: MonolithApiConceptProgressItem[] }
export interface MonolithApiapp__api__schemas__observability__HealthResponse { status: string; components?: Record<string, unknown> | null }
export interface MonolithApiapp__api__schemas__security__HealthResponse { status: string; data: Record<string, unknown> }
export interface MonolithApiapp__api__schemas__security__LoginRequest { email: string; password: string }
export interface MonolithApiapp__api__schemas__security__RegisterRequest { full_name: string; email: string; password: string }
export interface MonolithApiapp__api__schemas__system__responses__HealthResponse { application: string; database: string; version: string }
export interface MonolithApiapp__api__schemas__ums__LoginRequest { email: string; password: string }
export interface MonolithApiapp__api__schemas__ums__RegisterRequest { full_name: string; email: string; password: string }

// ── notation_service (notation-service) ─────────
export interface NotationServiceDefineRequest { symbol: string }
export interface NotationServiceDefineResponse { found: boolean; symbol?: NotationServiceSymbolPayload | null; error?: Record<string, unknown> | null; registry_version: string; duration_ms: number; trace_id: string }
export interface NotationServiceHealthResponse { status: string; service: string; step: string; version: string; registry_version: string; symbols_loaded: number; startup_state: string; llm_backend: string }
export interface NotationServiceResolveRequest { text: string }
export interface NotationServiceResolveResponse { found: boolean; symbol?: NotationServiceSymbolPayload | null; registry_version: string; duration_ms: number; trace_id: string }
export interface NotationServiceSymbolPayload { symbol: string; title: string; definition: string; example: string; concept_id?: string | null; property_id?: string | null }
export interface NotationServiceSymbolsResponse { symbols: NotationServiceSymbolPayload[]; count: number; registry_version: string }
export interface NotationServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── observability_service (Observability Service) ─────────
export interface ObservabilityServiceAlertItem { id: string; severity: string; message: string; timestamp: string; status: string; service_name: string; metrics: Record<string, unknown> }
export interface ObservabilityServiceAlertsResponse { alerts: ObservabilityServiceAlertItem[] }
export interface ObservabilityServiceCalculateMetricsRequest { findings: ObservabilityServiceSecurityFindingSchema[]; code_metrics?: Record<string, unknown> | null }
export interface ObservabilityServiceCalculateRiskRequest { findings: ObservabilityServiceSecurityFindingSchema[]; code_metrics?: Record<string, unknown> | null }
export interface ObservabilityServiceCalculateRiskResponse { risk_score: number }
export interface ObservabilityServiceCapacityPlanPayload { plan_id: string; service_name: string; current_capacity: number; recommended_capacity: number; forecast_horizon_hours: number; expected_peak_load: number; confidence: number; created_at: string }
export interface ObservabilityServiceCapacityPlanRequest { service_name: string; forecast_horizon_hours?: number }
export interface ObservabilityServiceCapacityPlanResponse { plan: ObservabilityServiceCapacityPlanPayload }
export interface ObservabilityServiceEndpointAnalyticsResponse { path: string; avg_latency: number; p95_latency: number; error_count?: number; total_calls?: number }
export interface ObservabilityServiceErrorMetrics { error_rate: number; error_count: number }
export interface ObservabilityServiceForecastRequest { service_name: string; metric_type: ObservabilityServiceMetricType; hours_ahead?: number }
export interface ObservabilityServiceForecastResponse { forecast_id: string; predicted_load: number; confidence_interval: unknown[] }
export interface ObservabilityServiceGoldenSignalsResponse { latency: ObservabilityServiceLatencyMetrics; traffic: ObservabilityServiceTrafficMetrics; errors: ObservabilityServiceErrorMetrics; saturation: ObservabilityServiceSaturationMetrics }
export interface ObservabilityServiceHealthResponse { service: string; status: string; database?: string | null }
export interface ObservabilityServiceLatencyMetrics { p50: number; p95: number; p99: number; "p99.9": number; avg: number }
export type ObservabilityServiceMetricType = string;
export interface ObservabilityServiceMetricsResponse { metrics: Record<string, unknown> }
export interface ObservabilityServicePerformanceSnapshotResponse { cpu_usage: number; memory_usage: number; active_requests: number }
export interface ObservabilityServiceRiskPredictionRequest { historical_metrics: ObservabilityServiceSecurityMetricsResponse[]; days_ahead?: number }
export interface ObservabilityServiceRiskPredictionResponse { predicted_risk: number; confidence: number; trend: string; slope: number; current_risk: number }
export interface ObservabilityServiceRootResponse { message: string }
export interface ObservabilityServiceSaturationMetrics { active_requests: number; queue_depth: number; active_spans?: number | null; resource_utilization?: number | null }
export interface ObservabilityServiceSecurityFindingSchema { id: string; severity: ObservabilityServiceSeverity; rule_id: string; file_path: string; line_number: number; message: string; cwe_id?: string | null; owasp_category?: string | null; first_seen?: string | null; last_seen?: string | null; false_positive?: boolean; fixed?: boolean; fix_time_hours?: number | null; developer_id?: string | null }
export interface ObservabilityServiceSecurityMetricsResponse { total_findings: number; critical_count: number; high_count: number; medium_count: number; low_count: number; findings_per_1000_loc: number; new_findings_last_24h: number; fixed_findings_last_24h: number; false_positive_rate: number; mean_time_to_detect: number; mean_time_to_fix: number; overall_risk_score: number; security_debt_score: number; trend_direction: string; findings_per_developer: Record<string, unknown>; fix_rate_per_developer: Record<string, unknown>; timestamp: string }
export type ObservabilityServiceSeverity = string;
export interface ObservabilityServiceTelemetryRequest { metric_id: string; service_name: string; metric_type: ObservabilityServiceMetricType; value: number; timestamp?: string; labels?: Record<string, unknown>; unit?: string }
export interface ObservabilityServiceTelemetryResponse { status: string; metric_id: string }
export interface ObservabilityServiceTrafficMetrics { requests_per_second: number; total_requests: number }
export interface ObservabilityServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── orchestrator_service (Orchestrator Service) ─────────
export interface OrchestratorServiceChatRequest { question: string; user_id: number; conversation_id?: number | null; history_messages?: Record<string, unknown>[]; context?: Record<string, unknown> }
export interface OrchestratorServiceComposeRequest { query: string; correlation_id?: string | null }
export interface OrchestratorServiceComposeResponse { correlation_id: string; query: string; composed_answer: string; pipeline_mode: string; skills_active: string[]; total_duration_ms: number; composition_confidence?: number; plan: OrchestratorServiceSkillResultSchema; research: OrchestratorServiceSkillResultSchema; reasoning: OrchestratorServiceSkillResultSchema }
export type OrchestratorServiceJsonObject = Record<string, unknown>;
export interface OrchestratorServiceMissionCreate { objective: string; context?: Record<string, unknown>; priority?: number }
export interface OrchestratorServiceMissionEventResponse { event_type: string; mission_id: number; timestamp?: string; payload?: Record<string, unknown> }
export interface OrchestratorServiceMissionResponse { id: number; objective: string; status: OrchestratorServiceMissionStatusEnum; outcome?: string | null; created_at: string; updated_at: string; result?: Record<string, unknown> | null; steps?: OrchestratorServiceMissionStepResponse[] }
export type OrchestratorServiceMissionStatusEnum = string;
export interface OrchestratorServiceMissionStepResponse { id?: number | null; name: string; description?: string | null; status?: OrchestratorServiceStepStatusEnum; result?: string | null; tool_used?: string | null; created_at: string; completed_at?: string | null }
export interface OrchestratorServiceOutboxRelayResponse { processed: number; published: number; failed: number; skipped: number }
export interface OrchestratorServiceOutboxStatusResponse { pending: number; processing: number; failed: number; published: number; oldest_pending_age_seconds: number | null; generated_at: string }
export interface OrchestratorServiceSkillResultSchema { skill: string; status: string; data: Record<string, unknown>; duration_ms: number; error?: string | null }
export type OrchestratorServiceStepStatusEnum = string;
export interface OrchestratorServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── planning_agent (Planning Agent) ─────────
export interface PlanningAgentHealthResponse { service: string; status: string; database?: string | null }
export interface PlanningAgentPlanRequest { objective: string; context?: Record<string, unknown> | unknown[] }
export interface PlanningAgentPlanResponse { plan_id: string; goal: string; strategy_name: string; reasoning: string; steps: PlanningAgentPlanStep[] }
export interface PlanningAgentPlanStep { name: string; description: string; tool_hint?: string | null }
export interface PlanningAgentValidationError { loc: string | number[]; msg: string; type: string }

// ── reasoning_agent (Reasoning Agent) ─────────
export interface ReasoningAgentAgentRequest { caller_id: string; target_service?: string; action: string; payload?: Record<string, unknown>; security_token?: string | null }
export interface ReasoningAgentAgentResponse { status: string; data?: unknown | null; error?: string | null; metrics?: Record<string, unknown> }
export interface ReasoningAgentValidationError { loc: string | number[]; msg: string; type: string }

// ── research_agent (Research Agent) ─────────
export interface ResearchAgentAgentRequest { caller_id: string; target_service?: string; action: string; payload?: Record<string, unknown>; security_token?: string | null }
export interface ResearchAgentAgentResponse { status: string; data?: unknown | null; error?: string | null; metrics?: Record<string, unknown> }
export interface ResearchAgentValidationError { loc: string | number[]; msg: string; type: string }

// ── transition_service (Transition Service) ─────────
export interface TransitionServiceDecisionResponse { allowed: boolean; decision_level: string; reason: string; human_action_description: string; decision_log: Record<string, unknown> }
export interface TransitionServiceDialogueRequest { stakeholder: string; feedback_text: string }
export interface TransitionServiceEarlyWarningRequest { scope?: string; occupation_codes?: string[]; worker?: TransitionServiceWorkerInput | null }
export interface TransitionServiceEducationRequest { institution_type?: string; target_skills?: string[]; current_curriculum_skills?: string[]; for_occupation?: string | null }
export interface TransitionServiceEquityRequest { population: TransitionServiceWorkerInput[] }
export interface TransitionServiceEvaluationRequest { kpi_code: string; measured_value: number; target_value: number; period?: string }
export interface TransitionServiceExposureRequest { occupation_code: string; task_breakdown?: Record<string, unknown>[] | null }
export interface TransitionServiceGovernanceApprovalRequest { request_id: string; agent: string; action_key: string; description: string; duration_days?: number; budget?: number }
export interface TransitionServiceGovernanceRequest { system_type: string; decision_description: string; affected_groups?: string[] }
export interface TransitionServiceJobCreationRequest { region?: string; sectors?: string[] }
export interface TransitionServiceRedTeamRequest { test_kind: string; payload?: Record<string, unknown> }
export interface TransitionServiceSimulationRequest { policy_name: string; displacement_rate: number; reinstatement_rate: number; horizon_years?: number; sector_codes?: string[] }
export interface TransitionServiceSkillsGapRequest { worker: TransitionServiceWorkerInput; target_occupation?: string | null }
export interface TransitionServiceSocialProtectionRequest { worker: TransitionServiceWorkerInput; transition_horizon_months?: number }
export interface TransitionServiceStandardResponse { status?: string; agent: string; result: Record<string, unknown>; governance?: Record<string, unknown> | null }
export interface TransitionServiceTransitionRequest { worker: TransitionServiceWorkerInput; target_occupation?: string | null; max_paths?: number }
export interface TransitionServiceValidationError { loc: string | number[]; msg: string; type: string }
export interface TransitionServiceWorkerInput { worker_id: string; current_occupation: string; region?: string; age_band?: string; gender_band?: string; current_skills?: string[]; income_band?: string; disability_band?: string }

// ── user_service (user-service) ─────────
export interface UserServiceAdminCreateUserRequest { full_name: string; email: string; password: string; is_admin?: boolean }
export interface UserServiceAuthResponse { access_token: string; token_type?: string; user: UserServiceUserResponse; status?: string; landing_path?: string }
export interface UserServiceChangePasswordRequest { current_password: string; new_password: string }
export interface UserServiceHealthResponse { service: string; status: string; environment?: string | null }
export interface UserServiceLoginRequest { email: string; password: string }
export interface UserServiceLogoutRequest { refresh_token: string }
export interface UserServicePasswordResetConfirmRequest { token: string; new_password: string }
export interface UserServicePasswordResetRequest { email: string }
export interface UserServicePasswordResetResponse { status?: string; reset_token?: string | null; expires_in?: number | null }
export interface UserServiceProfileUpdateRequest { full_name?: string | null; email?: string | null }
export interface UserServiceReauthRequest { password: string }
export interface UserServiceReauthResponse { reauth_token: string; expires_in: number }
export interface UserServiceRefreshRequest { refresh_token: string }
export interface UserServiceRegisterRequest { full_name: string; email: string; password: string }
export interface UserServiceRegisterResponse { status?: string; message: string; user: UserServiceUserResponse }
export interface UserServiceRoleAssignmentRequest { role_name: string; reauth_password?: string | null; reauth_token?: string | null; justification?: string | null }
export interface UserServiceStatusUpdateRequest { status: UserServiceUserStatus }
export interface UserServiceTokenGenerateResponse { access_token: string; refresh_token: string; token_type?: string }
export interface UserServiceTokenVerifyRequest { token?: string | null }
export interface UserServiceTokenVerifyResponse { status: string; data: Record<string, unknown> }
export interface UserServiceUserOut { id: number; email: string; full_name: string; is_active: boolean; status: UserServiceUserStatus; roles?: string[] }
export interface UserServiceUserResponse { id: number; name: string; full_name?: string | null; email: string; is_admin?: boolean }
export type UserServiceUserStatus = string;
export interface UserServiceValidationError { loc: string | number[]; msg: string; type: string }

// ── WebSocket chat event contract (shared/chat_protocol) ─────────
export type ChatEventType =
    | 'conversation_init'
    | 'assistant_delta'
    | 'assistant_final'
    | 'persisted'
    | 'complete'
    | 'error';

export interface ChatEvent {
    type: ChatEventType;
    payload?: {
        content?: string;
        conversation_id?: number;
        request_id?: string;
        ui_component?: Record<string, unknown> | null;
        code?: string;
    };
    persisted?: boolean;
}
