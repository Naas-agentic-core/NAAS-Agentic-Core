# Cutover Scoreboard

## Current metrics
| metric | value |
|---|---:|
| legacy_routes_count | 0 |
| legacy_ws_targets_count | 0 |
| monolith_required_for_default_runtime | false |
| emergency_legacy_expiry_enforced | true |
| normal_chat_owner | orchestrator-service |
| super_agent_owner | orchestrator-service |
| single_brain_architecture | true |
| app_import_count_in_microservices | 0 |
| active_copy_coupling_overlap_metric | 128 |
| stategraph_is_runtime_backbone | true |
| docs_runtime_parity | true |
| contract_gate | true |
| tracing_gate | true |

## Phase 0 forensic baseline inventory

### 1) Split-brain sources
- Runtime default topology is microservices-only (`docker-compose.yml`), while emergency legacy is isolated in `docker-compose.legacy.yml`.
- Documentation existed in markdown-only registry; machine-readable authority is now `config/route_ownership_registry.json`.
- Developer startup paths still include monolith-era helpers (`scripts/start.sh`, `scripts/start-backend.sh`) and require controlled retirement in later phases.

### 2) Gateway compatibility surfaces
- HTTP compatibility routes inventoried from `config/route_ownership_registry.json`.
- WebSocket compatibility routes: `/api/chat/ws`, `/admin/api/chat/ws`.

### 3) Phantom-limb coupling
- Import edges (`from app` داخل microservices): **0**.
- Copy-coupling overlap (`app/services/overmind` vs `microservices/orchestrator_service/src/services/overmind`): **128** shared files.
- Overmind coupling gate (phase 2b / strict_decrease): **true**.

### 4) Service lifecycle drift
- No lifecycle drift detected in Dockerfile + compose registration checks.
