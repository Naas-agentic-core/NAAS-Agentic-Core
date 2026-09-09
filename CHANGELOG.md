# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.0] - 2026-01-02 - API-First Architecture

### ⭐ API-First Architecture - Complete Transformation

#### Added
- ✨ **API-First Architecture 100%**: System now fully designed as API-First
  - Created `app/middleware/static_files_middleware.py` - Separate static files serving
  - Support for API-only mode (without frontend)
  - Configuration to enable/disable static files
  - Complete separation between API Core and Frontend
- 📚 **Comprehensive Documentation**: Added `docs/API_FIRST_ARCHITECTURE.md`
  - Full explanation of API-First principle
  - Examples of correct and incorrect usage
  - Migration guide for developers
  - Compliance rules and testing guidelines

#### Changed
- 🔄 **Kernel Refactoring**: Updated `app/kernel.py`
  - Added `enable_static_files` parameter to control Frontend
  - Separated static file setup from API core
  - Improved documentation to reflect API-First
  - Removed completed TODO comments
- 📝 **Documentation Updates**: Updated README.md
  - Added API-First badge
  - Clarified principle and benefits
  - Link to comprehensive guide

#### Deprecated
- ⚠️ **static_handler.py**: Marked `app/core/static_handler.py` as Deprecated
  - Added note to use `static_files_middleware` instead
  - Will be removed in next major version
  - Clear migration guide provided

### Impact
- ✅ **Zero Breaking Changes**: All API endpoints work as before
- ✅ **Backward Compatible**: Static files still work by default
- ✅ **Enhanced Flexibility**: Can now run in API-only mode
- ✅ **Better Separation**: Clear separation between Presentation and Business Logic

---

## [Unreleased]

### Added - 2026-08-20 - D-240: Transition Service (multi-agent AI work-transition layer)
- `microservices/transition_service/` — 13 specialized agents (early warning, occupation
  exposure, skills gap, career transition, education/curriculum, job creation, social
  protection, governance classification, equity monitoring, policy simulation, social
  dialogue, KPI evaluation, red team) plus a four-level human-oversight governance gate
  with a full audit log (INFORMATIVE → REQUIRES_REVIEW → COMMITTEE_APPROVAL →
  HIGH_RISK_REJECT).
- Deterministic-first core: every number is computed from a documented atlas (occupations,
  tasks, skills, training units) and pure math (Eloundou β-weighted exposure,
  Acemoglu–Restrepo displacement/reinstatement simulation) — the LLM is narrative-only
  and `LLM_MOCK_MODE=1` is the default.
- 61 tests (unit + E2E on all 23 endpoints), registered in the OpenAPI parity gate
  (15/15 API-first), the image build matrix (16 images), `docker-compose.yml` (:8012),
  and all architectural guardrails.
- Charter: `docs/charter/AI_TRANSITION_CHARTER.md` (Arabic, scientific references).

### Changed - 2026-08-15 - CodeScene X-Ray hotspots decommissioned (D-253/D-254/D-255/D-256/D-258/D-259 · zero behavior change)
- `app/services/chat/tools/content.py` hotspot decommissioned (D-255 + D-259):
  `search_content` is now an A(1) reception shell; role logic lives in pure shards
  `app/services/chat/tools/content_support/` (`search.py`, `branch.py`, `_sources.py`).
- **D-259**: removed residual `normalize_branch` code duplication — single authoritative
  shard `content_support/branch.py` (labels + thresholds). Fixed real bug: manifest
  referenced a nonexistent `branch.py` (silent `FileNotFoundError` for text-based
  doctrine guardians). Error scanning is now one dispatch table into three pure shards
  (`_scan_dict_error`, `_scan_iter_error`, `_scan_json_string_error`) — Bumpy Road closed.
- Companion decommissionings: `agents/orchestrator.py` (D-253), `api_gateway/main.py` (D-254),
  `infrastructure/clients/orchestrator_client.py` (D-256), `tests/conftest.py` (D-258).
- Verified: ruff 0.14.0 green · radon max A(5) · unit 656 passed · fitness guards 114 passed ·
  live E2E (Supabase + OpenRouter + Tavily MCP + FastAPI) ALL PASS.

### Added - 2026-08-15 - Live E2E runtime proof
- `tests/e2e_d259_live_runtime.py`: production DB (43 tables incl. `users`/`missions`),
  OpenRouter PRIMARY model (`openai/gpt-oss-20b:free` Arabic response), live Tavily MCP
  `tavily_search`, full content-tool delegation chain, FastAPI `/health` via full kernel.
  Runs outside CI (never commits secrets — `spec.md` §3): `TAVILY_MCP_URL` + `DATABASE_URL` +
  `OPENROUTER_API_KEY` from runtime environment.

### Added - 2026-01-03 - Phase 17: Comprehensive Review & Planning
- **Documentation Enhancement**: Comprehensive Git history review and continuous simplification planning
  - Added Phase 17 section to `SIMPLIFICATION_PROGRESS_REPORT.md` (150+ lines of analysis)
  - Added Phase 17 section to `GIT_HISTORY_SIMPLIFICATION_SUMMARY.md` (100+ lines)
  - Updated `PROJECT_METRICS.md` with accurate statistics and technical debt tracking
  - Fixed broken reference in `docs/archive/reports_archive/README.md`
- **Analysis & Planning**: Complete project assessment
  - Analyzed 430 Python files (45,809 lines of code)
  - Identified 115 TODO/FIXME items (60+ large functions, 40+ functions with many parameters)
  - Documented 20+ large files (>300 lines) requiring refactoring
  - Identified 5 critical files >400 lines (strategy.py: 656, generators.py: 544, etc.)
  - Verified 67 service classes and 23 DDD-structured services
  - Documented 184 unsafe type usages (mostly related to JSON handling)
- **Roadmap Creation**: Comprehensive improvement plan
  - Short-term: KISS violations resolution (1-2 weeks)
  - Medium-term: Large file refactoring (1-2 months)
  - Long-term: Quality goals achievement (quarterly)
- **Principles Applied**:
  - **Analysis First**: Comprehensive understanding before changes
  - **Documentation**: Everything tracked and documented
  - **Continuous Improvement**: Ongoing process with clear milestones
  - **Quality Focus**: No rush, understand first

**Impact**: 
- ✅ Zero code changes (analysis phase)
- ✅ Complete project health assessment
- ✅ Clear roadmap for 115+ improvements
- ✅ Documentation accuracy improved
- 🎯 Ready for Phase 18 (KISS Violations Resolution)

### Removed - 2026-01-03 - Phase 15: Boundaries Layer Elimination
- **BREAKING**: Removed entire `app/boundaries/` module (839 lines of unused abstraction)
  - Removed `app/boundaries/service_boundaries.py` - Service boundary patterns
  - Removed `app/boundaries/data_boundaries.py` - Data boundary patterns
  - Removed `app/boundaries/policy_boundaries.py` - Policy boundary patterns
  - Removed `app/boundaries/README.md` - Documentation
- Removed `tests/test_separation_of_concerns.py` (660 lines of tests for unused code)
- Removed `docs/BOUNDARIES_ARCHITECTURE_GUIDE.md` (15 KB theoretical documentation)
- Removed `scripts/cs61_simplify.py` (script that was never executed)

**Rationale**: Applied YAGNI (You Aren't Gonna Need It) principle. The boundaries layer was:
- Only used in tests, never in actual application code
- Purely theoretical architectural patterns
- Adding unnecessary complexity without practical benefit
- Total removal: **1,499+ lines** of unused abstraction

**Impact**: Zero - no production code was using these modules

**Principles Applied**:
- YAGNI (You Aren't Gonna Need It)
- KISS (Keep It Simple, Stupid)
- Practical over Theoretical

### Changed - Phase 14: Core Cleanup & Standardization (2026-01-03)
- **Removed 1000+ lines of dead code from `app/core/`**
  - Deleted `app/core/startup.py` - obsolete initialization code
  - Deleted `app/core/self_healing_db.py` - unused component
  - Deleted `app/core/cs61_concurrency.py` - experimental academic module
  - Deleted `app/core/cs61_memory.py` - experimental academic module  
  - Deleted `app/core/cs61_profiler.py` - experimental academic module
  - Deleted `app/core/factories.py` - unused patterns
- **Enforced Domain-Driven Design structure**
  - Relocated `app/models.py` → `app/core/domain/models.py`
  - Updated 26+ import references across application and tests
  - Proper domain layer organization
- **Cleaned root directory**
  - Moved verification scripts to `tests/verification/`
  - Removed temporary files and obsolete entry points
- **Simplified `app/core/database.py`**
  - Removed dependencies on deleted academic modules
  - Reduced initialization overhead
- **Impact**: 
  - Core directory is now pristine with only active components
  - "Supernatural cleanliness" achieved
  - Better performance with reduced import overhead
  - Clear DDD structure enforcement

### Changed - Documentation Updates (2026-01-03)
- **Updated `PROJECT_HISTORY.md`**
  - Added Phase 14 details
  - Documented all 14 completed phases
  - Updated timeline with recent achievements
- **Updated `PROJECT_METRICS.md`**
  - Current statistics: 435 files, 94,730 lines
  - Added Phase 14 cleanup metrics
  - Updated completed refactorings list
  - Adjusted target metrics based on progress
- **Updated `SIMPLIFICATION_PROGRESS_REPORT.md`**
  - Marked Phase 14 as complete
  - Updated overall progress statistics
  - Clarified next steps

### Changed - Documentation Simplification Phase 8 (2026-01-03)
- **Converted `app/services/overmind/__index__.py` to proper Markdown documentation**
- Created `docs/OVERMIND_ARCHITECTURE.md` - comprehensive Overmind system architecture guide
  - Converted 612 lines of Python documentation to well-structured Markdown
  - Bilingual documentation (Arabic/English) preserved
  - Better organization with table of contents and sections
  - Improved accessibility and readability
- Removed `app/services/overmind/__index__.py` (612 lines)
- **Impact**: Reduced codebase by 612 lines
- **Result**: Documentation in proper format, easier to maintain and access
- **Principle**: Separation of concerns - documentation should be in `.md`, not `.py`

### Removed - Code Cleanup (2026-01-03)
- **Removed obsolete file `app/services/overmind/database_tools_old.py` (930 lines)**
  - This file was already refactored into modular components in `app/services/overmind/database_tools/`
  - The new structure provides better separation of concerns:
    - `table_manager.py` - Table operations
    - `column_manager.py` - Column operations
    - `data_manager.py` - Data operations
    - `index_manager.py` - Index operations
    - `query_executor.py` - Query execution
    - `operations_logger.py` - Operation logging
    - `facade.py` - Unified interface
  - **Impact**: Reduced codebase by 930 lines of obsolete code
  - **Result**: Cleaner project structure with better maintainability

### Added - Comprehensive Simplification Analysis (2026-01-02)
- **Created comprehensive simplification analysis and planning system**
- Added `docs/reports/SIMPLIFICATION_ANALYSIS_2026.md` - detailed analysis report with:
  - Full project statistics (401 files, 48,446 lines, 1,737 functions)
  - Identified 34 large files (>300 lines) requiring refactoring
  - Identified 63 complex files (cyclomatic complexity >10)
  - Documented architectural decisions regarding boundaries pattern
  - Created phased simplification plan with clear priorities
- Added `app/boundaries/README.md` - comprehensive documentation for:
  - Abstract architectural patterns (ServiceBoundary, DataBoundary, PolicyBoundary)
  - Clean Architecture principles and DDD patterns
  - Clarified distinction from concrete service implementations
- Added `app/services/boundaries/README.md` - comprehensive documentation for:
  - Concrete service implementations using Facade pattern
  - AdminChatBoundaryService, AuthBoundaryService, CrudBoundaryService, ObservabilityBoundaryService
  - Architecture, design principles, and testing guidance
- **Result**: Clear architectural documentation and actionable simplification roadmap

### Added - Super Cleanup System (2026-01-02)
- **Created comprehensive super cleanup and organization system**
- Added `scripts/super_cleanup.py` - automated cleanup tool with features:
  - Python cache cleanup (__pycache__, *.pyc, *.pyo)
  - Build artifacts cleanup (build/, dist/, *.egg-info)
  - Temporary files cleanup (*.tmp, *.log, .DS_Store)
  - Test artifacts cleanup (.pytest_cache, .coverage, htmlcov/)
  - Type checking cache cleanup (.mypy_cache, .dmypy.json)
  - Dry-run mode for safe testing
  - Detailed statistics and reporting
- Created `docs/SUPER_CLEANUP_GUIDE.md` - comprehensive cleanup guide
- **Result**: Professional cleanup system with 100% clean project status

### Changed - Documentation Simplification Phase 4 (2026-01-02)
- **Continued simplification based on comprehensive Git log review**
- Moved `QUICK_OVERVIEW_PHASE3.md` to archive as completed phase documentation
  - Renamed to `docs/archive/planning/PHASE3_QUICK_OVERVIEW.md`
  - Content is redundant with PROJECT_HISTORY.md, CHANGELOG.md, and GIT_HISTORY_REVIEW_2026.md
- Reduced root-level MD files from 12 to 11
- **Result**: Cleaner root directory with only essential, active documentation

### Changed - Archive Organization Phase 3 (2026-01-02)
- **Comprehensive Git log review and archive reorganization**
- Analyzed complete Git history and project structure
- Reorganized 37 archive documents into 3 clear categories:
  - `docs/archive/delivery_reports/` (12 delivery reports)
  - `docs/archive/fix_reports/` (12 fix reports)
  - `docs/archive/planning/` (13 planning documents)
- Created `docs/archive/README.md` - comprehensive archive guide
- Created `docs/reports/GIT_HISTORY_REVIEW_2026.md` - complete review report
- Updated DOCUMENTATION_INDEX.md to reflect new archive structure
- Updated PROJECT_HISTORY.md with Phase 3 achievements
- **Result**: Organized archive with clear structure and improved searchability

### Changed - Documentation Simplification Phase 2 (2026-01-02)
- **Comprehensive Git log review and documentation cleanup**
- Merged duplicate simplification guides (SIMPLIFICATION_DEVELOPER_GUIDE.md → SIMPLIFICATION_GUIDE.md)
- Moved 13 historical/completed documents to `docs/archive/`:
  - Fix summaries: FIX_SUMMARY.txt, IMPLEMENTATION_SUMMARY.txt
  - Specific fix references: QUICK_REFERENCE.md (boundaries fix)
  - Completed PHASE documents: PHASE1_COMPLETION_SUMMARY.md, PHASE3_WAVE*.md (5 files)
  - Fix documentation: ASYNC_GENERATOR_FIX.md, ASYNC_GENERATOR_LOGIN_FIX.md, ENUM_CASE_SENSITIVITY_FIX.md
  - Implementation summaries: CS51_IMPLEMENTATION_SUMMARY.md
  - Future architecture: QUICK_START.md (microservices)
- Removed duplicate `docs/INDEX.md` (DOCUMENTATION_INDEX.md is more comprehensive)
- Updated DOCUMENTATION_INDEX.md to reflect all changes
- Cleaned up empty docs/guides/ directory
- **Result**: 16 files reorganized, improved documentation discoverability

### Changed - Documentation Simplification Phase 1 (2026-01-02)
- **Major documentation reorganization and simplification**
- Reduced root-level documentation files from 38 to 11 (71% reduction)
- Moved redundant and historical documentation to `docs/archive/`
- Organized reports into `docs/reports/`
- Created new comprehensive documentation:
  - `PROJECT_HISTORY.md` - Consolidated project history and evolution
  - `DOCUMENTATION_INDEX.md` - Complete guide to all documentation
- Updated `README.md` with new documentation structure
- Preserved all critical information while removing duplication

### Changed - Previous
- Refactored `AIServiceGateway` to be a class-based, dependency-injected service.
- Decoupled `AIServiceGateway` from the legacy web framework and the `requests` library by introducing an `HttpClientProtocol`.
- Moved `AIServiceGateway` to `app/gateways/ai_service_gateway.py`.
- Added backward-compatibility wrappers for `AIServiceGateway` in `app/services/ai_service_gateway.py`.
- Added smoke tests for `AIServiceGateway`.
- Added documentation for `AIServiceGateway`.
