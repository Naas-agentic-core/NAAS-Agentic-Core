# Architecture: Unified Control Plane & Source of Truth

## Core Principle: Single Control Plane
This system enforces a **Single Control Plane** architecture to prevent "Split-Brain" orchestration.
The **API Gateway + `microservices/orchestrator_service`** path is the designated runtime control plane for chat execution.
The monolith (`app`) keeps compatibility read/query surfaces only and must not own WebSocket execution state.

## Single Source of Truth
The **`cogniforge.db`** (application database) accessed via `app/core/domain/mission.py` models is the **Single Source of Truth** for:
- Mission State (Status, Context)
- Mission Events (Log)
- Execution Plans

Any external service attempting to manage mission state independently is a violation of this architecture.

## Execution Flow: Command -> Event -> State
All mission executions must follow the **Command Pattern**:
1.  Client (API/Chat) sends a `StartMission` command via `app/services/overmind/entrypoint.py`.
2.  Command Handler enforces **Idempotency** and **Locking**.
3.  Command Handler persists `MissionStarted` event to DB.
4.  Command Handler triggers execution (background task or worker).
5.  Execution Logic (`OvermindOrchestrator`) updates state and logs events.

## Strict Boundaries
- **No Direct Execution**: `run_mission()` must never be called directly from UI/API handlers without going through the Command Entrypoint.
- **No Dual Writes**: State changes must occur within a transaction that also logs the corresponding event.

## Chat Runtime Ownership (Split-Brain Resolution)
- **Canonical runtime entry for chat is API Gateway only**: `microservices/api_gateway` exposes `/api/chat/ws` and `/admin/api/chat/ws` and forwards to `orchestrator_service`.
- **Monolith chat WebSocket endpoints are decommissioned**: `app/api/routers/admin.py` and `app/api/routers/customer_chat.py` no longer expose WS routes to prevent dual session ownership.
- **Parity cutover is hard-enforced**: `CONVERSATION_PARITY_VERIFIED` is enforced as `true` inside gateway settings validation to avoid accidental legacy fallback behavior.

