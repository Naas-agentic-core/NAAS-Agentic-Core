# Architecture Report: Split-Brain Resolution

**Date:** 2025-05-20
**Status:** RESOLVED (Single Control Plane Enforced)

## 1. The Problem: Split-Brain Architecture
The system previously suffered from a "Split-Brain" condition where the orchestration logic existed in two places:
1.  **In-Process (Monolith):** مسارات الدردشة/المهام في المونوليث خُفّضت إلى Facades توافقية بلا تنفيذ محلي.
2.  **Microservice:** `microservices/orchestrator_service` existed but was either bypassed or duplicated the logic.

This resulted in:
*   **Coupling:** The Gateway (`app`) imported microservice code, breaking process isolation.
*   **State Drift:** Changes in one orchestrator were not reflected in the other.
*   **Deployment Fragility:** Updating the orchestrator required redeploying the monolith.

## 2. The Solution: Strict Microservices
We have refactored the system to enforce the **Microservices Constitution**.

### 2.1. Migration of Authority
*   **Moved Logic:** The domain logic for Missions (creation, state management, execution) was consolidated into `microservices/orchestrator_service`.
*   **Database Ownership:** The `missions` table is now exclusively managed by the Orchestrator Service.

### 2.2. Gateway Refactoring
*   **Removed Imports:** Deleted `OvermindOrchestrator` logic from `app`.
*   **HTTP Delegation:** `app/api/routers/overmind.py` now uses `httpx` to call `http://orchestrator-service:8000/missions`.
*   **Streaming BFF:** Implemented `RedisEventBridge` in `app/core/redis_bus.py`.
    *   **Old Way:** The monolith listened to local Python events.
    *   **New Way:** The Orchestrator Service publishes events to Redis (`mission:{id}`). The Gateway subscribes to Redis and forwards events to the WebSocket.

### 2.3. Infrastructure
*   **Redis:** Added a Redis container (`redis:6379`) to serve as the Event Backbone.

## 3. Boundary Verification
*   **Check:** No imports of `microservices` exist within `app`.
*   **Test:** `tests/unit/test_redis_bridge.py` verifies the event streaming pipeline.

## 4. Future Work
*   Implement `tools/ci/check_import_boundaries.py` to prevent regression.
*   Add distributed tracing (OpenTelemetry) for deeper observability.


## 5. Compatibility Facade Guard
- `COMPATIBILITY_FACADE_MODE=True` remains enabled in legacy routers.
- Canonical authority is now `orchestrator-service:/agent/chat`.
- Local execution is explicitly blocked with `LEGACY_LOCAL_EXECUTION_BLOCKED=True`.
