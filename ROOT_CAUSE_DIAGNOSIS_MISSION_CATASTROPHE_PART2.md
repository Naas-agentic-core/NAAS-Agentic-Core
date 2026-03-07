# Forensic Diagnosis: The "Admin vs Customer" Mission Catastrophe

## Executive Summary
This report analyzes a critical discrepancy in the chat infrastructure:
When the "Admin" requests a file count, the system successfully processes the query. Conversely, when the "Customer" requests an exercise (e.g., probability in 2024), the application throws a catastrophic unhandled error visible in the UI: `Error: Error connecting to agent: All connection attempts failed`.

## 1. The Symptoms
* **Admin Request ("Count Python Files"):** Completes successfully.
* **Customer Request ("Probability Exercise 2024"):** Fails completely.
* **Visible Error:** The frontend UI crashes or displays `Error: Error connecting to agent: All connection attempts failed`, or logs `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`.

## 2. Root Cause Tracing
The issue stems directly from the architectural "Split-Brain" nature of the application and how different intents are routed across network boundaries.

### A. The Intent Detection Branch
1. When a user asks a question, the monolith uses `ChatOrchestrator.process()` (`app/services/chat/orchestrator.py`) to detect the intent.
2. The orchestrator delegates specific intents to the `OrchestratorAgent` (running inside the `orchestrator-service` microservice) by calling the `orchestrator_client.chat_with_agent` HTTP bridge.

### B. The Admin Scenario (Success Path)
1. **Admin asks "Count Python Files":** The intent is detected as `ADMIN_QUERY`.
2. The request is forwarded to `orchestrator-service` via `orchestrator_client`.
3. Inside `orchestrator-service`, the `AdminAgent` uses standard administrative tools (like counting files on the local filesystem of the container). These tools execute locally within the microservice without requiring external network calls.
4. The JSON chunks stream back successfully to the monolith, which forwards them to the frontend.

### C. The Customer Scenario (Failure Path)
1. **Customer asks for an exercise:** The intent is detected as `CONTENT_RETRIEVAL`.
2. The monolith delegates the request to `orchestrator-service` via `orchestrator_client.chat_with_agent`.
3. Inside `orchestrator-service`, the `OrchestratorAgent` attempts to handle `CONTENT_RETRIEVAL` by invoking the `search_content` tool (`microservices/orchestrator_service/src/services/tools/content.py`).
4. **The Catastrophe:** The `search_content` tool implements an "Advanced Two-Layer Hybrid Search System" that relies heavily on an external call to the `research-agent` microservice via `research_client.semantic_search`.
5. If the `research-agent` microservice is unreachable (e.g., missing from the `docker-compose` profile, or networking/DNS resolution fails), the underlying `httpx` client throws an `httpx.ConnectError: All connection attempts failed`.

### D. The Error Handling Cascade
1. When the connection inside `search_content` fails, or if `orchestrator-service` itself is unreachable from the monolith, the `orchestrator_client` catches the connection exception:
   ```python
   except Exception as e:
       logger.error(f"Failed to chat with agent: {e}", exc_info=True)
       yield {
           "type": "assistant_error",
           "payload": {"content": f"Error connecting to agent: {e}"},
       }
   ```
2. The `Exception` string representation becomes `"All connection attempts failed"`, resulting in the exact payload seen in the UI: `Error connecting to agent: All connection attempts failed`.
3. If this error payload isn't strictly formatted, or if the fallback raw string logic in the UI's JSON parsers fails to decode it, the `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` is thrown.

## 3. Conclusion & Diagnosis
The crash is **not** a flaw in the `Customer` logic specifically, but rather a flaw in **Microservice Interdependency** combined with **Brittle Fallback Formatting**.

1. **Service Dependency:** The `Customer`'s intent (`CONTENT_RETRIEVAL`) forcefully depends on the `research-agent` microservice being alive and reachable. The Admin's intent (`ADMIN_QUERY`) relies only on local `orchestrator-service` execution.
2. **Network Resolution:** If the frontend is communicating with the local monolith, and the monolith tries to hit `http://orchestrator-service:8006` or `orchestrator-service` tries to hit `http://research-agent:8000` when running locally outside of the Docker bridge network, it triggers the DNS/Connection failure.
3. **Stream Protocol Mismatch:** The monolith's boundary service fails to sanitize the unhandled `httpx` connection error into a valid, strict WebSocket event that the frontend can parse smoothly, leading to the JSON decode collapse.

*As requested, no codebase files have been modified. This document serves purely as the diagnostic outcome.*