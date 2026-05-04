# ADR 005: Conditional Persistence and Dual-Write Immunity

## Status
Accepted

## Context
A dual-write bug caused duplicated messages in the customer chat endpoints. The monolithic facade and the new microservice orchestrator were independently persisting the same assistant messages into the database, leading to a race condition and duplicates in the frontend.

## Decision
We implemented a **Conditional Persistence Architecture** to serve as an immune system against dual writes:

1. **Orchestrator-Led Signal**: The monolith orchestrates the WebSocket stream but delegates primary persistence to the orchestrator.
2. **Fail-Safe Monolith Write**: If the orchestrator explicitly signals `persisted=True`, the monolith skips writing. **If no signal is received (or `persisted=False`), the monolith defaults to ALWAYS writing.**
3. **Absence of Signal = Failure**: The system treats an absent signal as a failure. Durability is prioritized over optimization. 
4. **Duplicate Guard**: To catch edge cases (e.g., race conditions, retries), the `CustomerChatPersistence` layer implements a 10-second sliding window Duplicate Detection Guard that suppresses identical `(conversation_id, role, content)` writes.

## Consequences
- **Zero Data Loss**: Even if the stream drops or the orchestrator fails to persist, the monolith will safely store the conversation.
- **Observability**: Explicit `[WRITE_DECISION]` logs are emitted at every branch to ensure forensics can trace who wrote what.
- **System Immunity**: The system natively blocks duplicates at the DB level via the short-window Duplicate Detection Guard.

## Lock Warning
This architecture MUST NOT be "simplified" by removing the monolith fallback or the duplicate guard. Doing so will re-introduce either silent data loss or the dual-write bug.
