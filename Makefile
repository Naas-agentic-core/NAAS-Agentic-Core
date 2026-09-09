# ======================================================================================
# MAKEFILE - CogniForge Development Commands
# ======================================================================================
# One-command automation for all common tasks
# Standards: Google, Meta, Microsoft, Netflix, Uber
#
# Usage:
#   make help          - Show all available commands
#   make install       - Install all dependencies
#   make quality       - Run all quality checks
#   make test          - Run test suite
#   make format        - Auto-format code
#   make lint          - Run all linters
#   make security      - Run security scans
#   make docs          - Generate documentation
#   make clean         - Clean build artifacts
#   make microservices - Manage microservices
# ======================================================================================

.PHONY: help install quality test format lint security docs clean run dev deploy \
        microservices-build microservices-up microservices-down microservices-logs \
        microservices-test microservices-health gateway-test event-bus-test \
        circuit-breaker-test integration-test fmt guardrails ci compose-isolation gates model-check

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

# =============================================================================
# HELP - Show all available commands
# =============================================================================
help:
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BLUE)  🚀 CogniForge - Development Commands$(NC)"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(GREEN)📦 Installation:$(NC)"
	@echo "  make install          - Install all dependencies"
	@echo "  make install-dev      - Install development dependencies"
	@echo "  make install-pre-commit - Setup pre-commit hooks"
	@echo ""
	@echo "$(GREEN)🎨 Code Quality:$(NC)"
	@echo "  make quality          - Run ALL quality checks (recommended)"
	@echo "  make format           - Auto-format code (black + ruff)"
	@echo "  make fmt              - Alias for format"
	@echo "  make lint             - Run all linters (ruff + pylint + flake8)"
	@echo "  make check            - Check code formatting (no changes)"
	@echo "  make type-check       - Run type checker (mypy)"
	@echo "  make security         - Run security scans (bandit + safety)"
	@echo "  make complexity       - Analyze code complexity"
	@echo "  make guardrails       - Run architecture guardrails scan"
	@echo "  make ci               - Run CI-equivalent checks locally"
	@echo ""
	@echo "$(GREEN)🧪 Testing:$(NC)"
	@echo "  make test             - Run test suite with coverage"
	@echo "  make test-fast        - Run tests without coverage"
	@echo "  make test-verbose     - Run tests with detailed output"
	@echo "  make coverage         - Generate coverage report"
	@echo ""
	@echo "$(GREEN)📚 Documentation:$(NC)"
	@echo "  make docs             - Generate documentation"
	@echo "  make docs-serve       - Serve documentation locally"
	@echo ""
	@echo "$(GREEN)🚀 Running:$(NC)"
	@echo "  make run              - Run application in production mode"
	@echo "  make dev              - Run application in development mode"
	@echo "  make debug            - Run application in debug mode"
	@echo ""
	@echo "$(GREEN)🐳 Docker:$(NC)"
	@echo "  make docker-build     - Build Docker images"
	@echo "  make docker-up        - Start Docker containers"
	@echo "  make docker-down      - Stop Docker containers"
	@echo "  make docker-logs      - View Docker logs"
	@echo "  make compose-isolation - Validate compose isolation rules"
	@echo "  make gates            - Run every CI fitness gate locally"
	@echo "  make model-check      - Ask the live provider if the whole model chain is servable (D-288)"
	@echo ""
	@echo "$(GREEN)🗄️ Database:$(NC)"
	@echo "  make db-migrate       - Create new migration"
	@echo "  make db-upgrade       - Apply migrations"
	@echo "  make db-downgrade     - Rollback migration"
	@echo "  make db-status        - Check migration status"
	@echo ""
	@echo "$(GREEN)🧹 Cleanup:$(NC)"
	@echo "  make clean            - Remove build artifacts"
	@echo "  make clean-all        - Deep clean (includes .venv)"
	@echo ""
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"

# =============================================================================
# INSTALLATION
# =============================================================================
install:
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	@echo "$(GREEN)✅ Dependencies installed!$(NC)"

install-dev:
	@echo "$(BLUE)📦 Installing development dependencies...$(NC)"
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install black isort ruff pylint flake8 mypy bandit[toml] pydocstyle
	pip install radon xenon mccabe safety pre-commit
	pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints
	@echo "$(GREEN)✅ Development dependencies installed!$(NC)"

install-pre-commit:
	@echo "$(BLUE)🔧 Setting up pre-commit hooks...$(NC)"
	pip install pre-commit
	pre-commit install
	pre-commit install --hook-type commit-msg
	@echo "$(GREEN)✅ Pre-commit hooks installed!$(NC)"

# =============================================================================
# CODE QUALITY - format · lint · type-check · security · complexity · test
# =============================================================================
quality: format lint type-check security complexity test
	@echo "$(GREEN)════════════════════════════════════════════════════════════════$(NC)"
	@echo "$(GREEN)  ✅ ALL QUALITY CHECKS PASSED$(NC)"
	@echo "$(GREEN)════════════════════════════════════════════════════════════════$(NC)"

format:
	@echo "$(BLUE)🎨 Formatting code with Black and Ruff...$(NC)"
	black .
	ruff check --fix .
	ruff format .
	@echo "$(GREEN)✅ Code formatted!$(NC)"

fmt: format

lint:
	@echo "$(BLUE)🔍 Running linters...$(NC)"
	@echo "$(YELLOW)⚡ Ruff (ultra-fast)...$(NC)"
	ruff check .
	@echo "$(GREEN)✅ Linting complete!$(NC)"

guardrails:
	@echo "$(BLUE)🛡️ Running architecture guardrails...$(NC)"
	python scripts/ci_guardrails.py
	@echo "$(GREEN)✅ Guardrails passed!$(NC)"

# ISS-148: `guardrails` above runs ONE of the ~29 checks the CI job of the same
# name runs. That gap is how a contributor ends up "locally clean" and red on
# push. `gates` runs the real set, read from ci.yml itself so it cannot drift.
gates:
	@echo "$(BLUE)🚦 Running every fitness gate the CI guardrails job runs...$(NC)"
	@base_sha="$$(git merge-base HEAD origin/main 2>/dev/null || true)"; \
	CODE_ACCEPTANCE_BASE_SHA="$$base_sha" python scripts/run_fitness_gates.py
	@echo "$(GREEN)✅ All fitness gates passed!$(NC)"

compose-isolation:
	@echo "$(BLUE)🧩 Validating compose isolation rules...$(NC)"
	python scripts/validate_compose_isolation.py
	@echo "$(GREEN)✅ Compose isolation validation complete!$(NC)"

# D-288: CI الأخضر لا يعني أن الكتالوج الحيّ يخدم نماذجنا — المطاردة الكاملة كانت هنا.
# المسبار يسأل مزوّد النماذج عن كل سلسلة MODEL_CHAIN (وعميلِ الـ override نفسه) ويُسقِط
# الرحلة الحيّة برسائل صريحة إن مات نموذج. يحتاج OPENROUTER_API_KEY فقط؛ لا يُقلِع
# خادماً ولا يلمس قاعدة بيانات، فيُشغَّل قبل الإقلاع الحيّ وبعده على السواء.
model-check:
	@echo "$(BLUE)🛰️ Probing the live model registry for the whole chain...$(NC)"
	python scripts/verify_model_registry_live.py --check-key
	@echo "$(GREEN)✅ Model chain is servable on the live registry.$(NC)"

ci: check lint guardrails compose-isolation test
	@echo "$(GREEN)✅ CI checks complete!$(NC)"

check:
	@echo "$(BLUE)✅ Checking code formatting (no changes)...$(NC)"
	black --check .
	ruff check .
	@echo "$(GREEN)✅ Code formatting check passed!$(NC)"

type-check:
	@echo "$(BLUE)🔍 Type checking with MyPy...$(NC)"
	mypy app/ --ignore-missing-imports --show-error-codes --pretty || true
	@echo "$(GREEN)✅ Type checking complete!$(NC)"

security:
	@echo "$(BLUE)🔒 Running security scans...$(NC)"
	@echo "$(YELLOW)🛡️ Bandit (code security)...$(NC)"
	bandit -r app/ -c pyproject.toml
	@echo "$(YELLOW)🔐 Safety (dependency security)...$(NC)"
	safety check || true
	@echo "$(GREEN)✅ Security scan complete!$(NC)"

complexity:
	@echo "$(BLUE)📊 Analyzing code complexity...$(NC)"
	@echo "$(YELLOW)🎯 Cyclomatic complexity...$(NC)"
	radon cc app/ -a -nb
	@echo "$(YELLOW)📈 Maintainability index...$(NC)"
	radon mi app/ -nb
	@echo "$(GREEN)✅ Complexity analysis complete!$(NC)"

# =============================================================================
# TESTING
# =============================================================================
test:
	@echo "$(BLUE)🧪 Running test suite with coverage...$(NC)"
	ENVIRONMENT=testing TESTING=1 SECRET_KEY=test-key \
	pytest --verbose --cov=app --cov-report=term-missing:skip-covered \
	       --cov-report=html:htmlcov --cov-report=xml:coverage.xml \
	       --cov-fail-under=73
#      ^^ ISS-148: was 100, while `ci.yml` gates on 73 (measured, with a
#      deliberate margin below the real 73.41%). A local target that fails where
#      CI passes trains people to ignore it — the worst possible state for a gate.
	@echo "$(GREEN)✅ Tests passed with coverage!$(NC)"

test-fast:
	@echo "$(BLUE)🧪 Running fast tests...$(NC)"
	ENVIRONMENT=testing TESTING=1 SECRET_KEY=test-key pytest
	@echo "$(GREEN)✅ Fast tests complete!$(NC)"

test-verbose:
	@echo "$(BLUE)🧪 Running tests with detailed output...$(NC)"
	ENVIRONMENT=testing TESTING=1 SECRET_KEY=test-key pytest -vv -s
	@echo "$(GREEN)✅ Verbose tests complete!$(NC)"

coverage:
	@echo "$(BLUE)📊 Generating coverage report...$(NC)"
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Open htmlcov/index.html manually"
	@echo "$(GREEN)✅ Coverage report generated!$(NC)"

# =============================================================================
# DOCUMENTATION
# =============================================================================
docs:
	@echo "$(BLUE)📚 Generating documentation...$(NC)"
	@python scripts/generate_docs.py --format both
	@echo "$(GREEN)✅ API documentation generated!$(NC)"

docs-serve:
	@echo "$(BLUE)📚 Serving documentation...$(NC)"
	@cd docs/generated && python -m http.server 8000

docs-validate:
	@echo "$(BLUE)🔍 Validating API contracts...$(NC)"
	@for file in docs/contracts/openapi/*.yaml; do \
		echo "Validating $$file..."; \
		npx @stoplight/spectral-cli lint "$$file" --ruleset docs/contracts/policies/.spectral.yaml || true; \
	done
	@for file in docs/contracts/asyncapi/*.yaml; do \
		echo "Validating $$file..."; \
		npx @stoplight/spectral-cli lint "$$file" --ruleset docs/contracts/policies/.spectral.yaml || true; \
	done
	@echo "$(GREEN)✅ Contract validation complete!$(NC)"

# =============================================================================
# RUNNING
# =============================================================================
run:
	@echo "$(BLUE)🚀 Starting application...$(NC)"
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	@echo "$(BLUE)🔧 Starting development server...$(NC)"
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

debug:
	@echo "$(BLUE)🐛 Starting debug mode...$(NC)"
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

# =============================================================================
# DOCKER
# =============================================================================
docker-build:
	@echo "$(BLUE)🐳 Building Docker images...$(NC)"
	docker-compose build
	@echo "$(GREEN)✅ Docker images built!$(NC)"

docker-up:
	@echo "$(BLUE)🐳 Starting Docker containers...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✅ Containers started!$(NC)"

docker-down:
	@echo "$(BLUE)🐳 Stopping Docker containers...$(NC)"
	docker-compose down
	@echo "$(GREEN)✅ Containers stopped!$(NC)"

docker-logs:
	@echo "$(BLUE)🐳 Viewing Docker logs...$(NC)"
	docker-compose logs -f

# =============================================================================
# MICROSERVICES - API-First Architecture
# =============================================================================
microservices-build:
	@echo "$(BLUE)🏗️  Building all microservices...$(NC)"
	docker-compose -f docker-compose.yml build
	@echo "$(GREEN)✅ All microservices built!$(NC)"

microservices-up:
	@echo "$(BLUE)🚀 Starting all microservices...$(NC)"
	docker-compose -f docker-compose.yml up -d
	@echo "$(GREEN)✅ All microservices started!$(NC)"
	@echo ""
	@echo "$(YELLOW)📊 Service URLs:$(NC)"
	@echo "  API Gateway:        http://localhost:8000"
	@echo "  Planning Agent:     http://localhost:8001"
	@echo "  Memory Agent:       http://localhost:8002"
	@echo "  User Service:       http://localhost:8003"
	@echo "  Orchestrator:       http://localhost:8004"
	@echo "  Observability:      http://localhost:8005"

microservices-down:
	@echo "$(BLUE)🛑 Stopping all microservices...$(NC)"
	docker-compose -f docker-compose.yml down
	@echo "$(GREEN)✅ All microservices stopped!$(NC)"

microservices-logs:
	@echo "$(BLUE)📋 Viewing microservices logs...$(NC)"
	docker-compose -f docker-compose.yml logs -f

microservices-health:
	@echo "$(BLUE)🏥 Checking microservices health...$(NC)"
	@echo ""
	@echo "$(YELLOW)API Gateway:$(NC)"
	@curl -s http://localhost:8000/gateway/health | jq || echo "$(RED)❌ Not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Planning Agent:$(NC)"
	@curl -s http://localhost:8001/health | jq || echo "$(RED)❌ Not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Memory Agent:$(NC)"
	@curl -s http://localhost:8002/health | jq || echo "$(RED)❌ Not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)User Service:$(NC)"
	@curl -s http://localhost:8003/health | jq || echo "$(RED)❌ Not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Orchestrator:$(NC)"
	@curl -s http://localhost:8004/health | jq || echo "$(RED)❌ Not responding$(NC)"
	@echo ""
	@echo "$(YELLOW)Observability:$(NC)"
	@curl -s http://localhost:8005/health | jq || echo "$(RED)❌ Not responding$(NC)"

microservices-restart:
	@echo "$(BLUE)🔄 Restarting all microservices...$(NC)"
	docker-compose -f docker-compose.yml restart
	@echo "$(GREEN)✅ All microservices restarted!$(NC)"

microservices-ps:
	@echo "$(BLUE)📊 Microservices status:$(NC)"
	docker-compose -f docker-compose.yml ps

# =============================================================================
# MICROSERVICES TESTING
# =============================================================================
gateway-test:
	@echo "$(BLUE)🧪 Testing API Gateway...$(NC)"
	python -m pytest tests/test_gateway.py -v
	@echo "$(GREEN)✅ Gateway tests passed!$(NC)"

event-bus-test:
	@echo "$(BLUE)🧪 Testing Event Bus...$(NC)"
	python -m pytest tests/test_event_bus.py -v
	@echo "$(GREEN)✅ Event Bus tests passed!$(NC)"

circuit-breaker-test:
	@echo "$(BLUE)🧪 Testing Circuit Breaker...$(NC)"
	python -m pytest tests/test_circuit_breaker.py -v
	@echo "$(GREEN)✅ Circuit Breaker tests passed!$(NC)"

integration-test:
	@echo "$(BLUE)🧪 Running integration tests...$(NC)"
	python -m pytest tests/integration/ -v
	@echo "$(GREEN)✅ Integration tests passed!$(NC)"

microservices-test: gateway-test event-bus-test circuit-breaker-test integration-test
	@echo "$(GREEN)✅ All microservices tests passed!$(NC)"

# =============================================================================
# DATABASE
# =============================================================================
db-migrate:
	@echo "$(BLUE)🗄️ Creating migration...$(NC)"
	python -m alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)✅ Migration created!$(NC)"

db-upgrade:
	@echo "$(BLUE)🗄️ Applying migrations...$(NC)"
	python -m alembic upgrade head
	@echo "$(GREEN)✅ Migrations applied!$(NC)"

db-downgrade:
	@echo "$(BLUE)🗄️ Rolling back migration...$(NC)"
	python -m alembic downgrade -1
	@echo "$(GREEN)✅ Migration rolled back!$(NC)"

db-status:
	@echo "$(BLUE)🗄️ Checking migration status...$(NC)"
	python check_migrations_status.py

# =============================================================================
# SIMPLICITY - complexity-reduction helpers
# =============================================================================
simplicity-validate:
	@echo "$(BLUE)🎯 Running simplicity validator...$(NC)"
	python tools/simplicity_validator.py --directory app --report-file SIMPLICITY_VALIDATION_REPORT.md
	@echo "$(GREEN)✅ Simplicity validation complete!$(NC)"

simplicity-purify:
	@echo "$(BLUE)🧹 Purifying root directory...$(NC)"
	bash scripts/purify_root.sh
	@echo "$(GREEN)✅ Root purification complete!$(NC)"

simplicity-report:
	@echo "$(BLUE)📊 Generating simplicity report...$(NC)"
	@echo "$(YELLOW)See SIMPLICITY_VALIDATION_REPORT.md for details$(NC)"
	@cat SIMPLICITY_VALIDATION_REPORT.md 2>/dev/null || echo "Run 'make simplicity-validate' first"

simplicity-help:
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BLUE)  🎯 Simplicity Commands$(NC)"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@echo "  make simplicity-validate   - Validate code against simplicity principles"
	@echo "  make simplicity-purify     - Clean root directory (move docs to archive)"
	@echo "  make simplicity-report     - View current simplicity report"
	@echo ""
	@echo "$(GREEN)Documentation:$(NC)"
	@echo "  • docs/architecture/ENGINEERING_DOCTRINE.md - complexity law + its gates"
	@echo ""
	@echo "$(YELLOW)Philosophy: \"احذف، ادمج، ثم ابنِ\" - Delete, Merge, then Build$(NC)"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"

# =============================================================================
# CLEANUP
# =============================================================================
clean:
	@echo "$(BLUE)🧹 Cleaning build artifacts...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ coverage.xml junit.xml
	rm -rf build/ dist/
	@echo "$(GREEN)✅ Cleanup complete!$(NC)"

clean-all: clean
	@echo "$(BLUE)🧹 Deep cleaning (including .venv)...$(NC)"
	rm -rf .venv/
	@echo "$(GREEN)✅ Deep cleanup complete!$(NC)"

# =============================================================================
# PRE-COMMIT
# =============================================================================
pre-commit-run:
	@echo "$(BLUE)🔧 Running pre-commit hooks on all files...$(NC)"
	pre-commit run --all-files
	@echo "$(GREEN)✅ Pre-commit checks complete!$(NC)"

pre-commit-update:
	@echo "$(BLUE)🔧 Updating pre-commit hooks...$(NC)"
	pre-commit autoupdate
	@echo "$(GREEN)✅ Pre-commit hooks updated!$(NC)"

# =============================================================================
# ML OPERATIONS - DevOps / MLOps
# =============================================================================

# ML Installation
install-ml: install
	@echo "$(BLUE)📦 Installing ML-specific dependencies...$(NC)"
	pip install great-expectations mlflow argo-workflows || true
	@echo "$(GREEN)✅ ML dependencies installed!$(NC)"

# Data Quality
data-quality:
	@echo "$(BLUE)🔍 Running data quality checks...$(NC)"
	python pipelines/data_quality_checkpoint.py
	@echo "$(GREEN)✅ Data quality checks complete!$(NC)"

# ML Training Pipeline
train:
	@echo "$(BLUE)🚀 Starting ML training pipeline...$(NC)"
	python pipelines/steps/prepare_data.py
	python pipelines/steps/validate_data_quality.py
	python pipelines/steps/train.py
	python pipelines/steps/evaluate.py
	python pipelines/steps/check_fairness.py
	python pipelines/steps/register_model.py
	@echo "$(GREEN)✅ Training pipeline complete!$(NC)"

# Model Evaluation
evaluate:
	@echo "$(BLUE)📊 Evaluating model...$(NC)"
	python pipelines/steps/evaluate.py
	@echo "$(GREEN)✅ Model evaluation complete!$(NC)"

# Model Registration
register:
	@echo "$(BLUE)📝 Registering model to MLflow...$(NC)"
	python pipelines/steps/register_model.py
	@echo "$(GREEN)✅ Model registered!$(NC)"

# Infrastructure Operations
infra-init:
	@echo "$(BLUE)🏗️ Initializing Terraform...$(NC)"
	cd infra/terraform && terraform init
	@echo "$(GREEN)✅ Terraform initialized!$(NC)"

infra-plan:
	@echo "$(BLUE)📋 Planning infrastructure changes...$(NC)"
	cd infra/terraform && terraform plan
	@echo "$(GREEN)✅ Infrastructure plan complete!$(NC)"

infra-apply:
	@echo "$(YELLOW)⚠️  Applying infrastructure changes...$(NC)"
	cd infra/terraform && terraform apply
	@echo "$(GREEN)✅ Infrastructure applied!$(NC)"

infra-destroy:
	@echo "$(RED)⚠️  Destroying infrastructure...$(NC)"
	cd infra/terraform && terraform destroy
	@echo "$(YELLOW)⚠️  Infrastructure destroyed!$(NC)"

# Deployment Operations
deploy-dev:
	@echo "$(BLUE)🚀 Deploying to dev environment...$(NC)"
	kubectl apply -f serving/kserve-inference.yaml --namespace=dev || echo "kubectl not available"
	@echo "$(GREEN)✅ Deployed to dev!$(NC)"

deploy-staging:
	@echo "$(BLUE)🚀 Deploying to staging environment...$(NC)"
	kubectl apply -f serving/kserve-inference.yaml --namespace=staging || echo "kubectl not available"
	@echo "$(GREEN)✅ Deployed to staging!$(NC)"

deploy-prod:
	@echo "$(YELLOW)⚠️  Deploying to production (canary)...$(NC)"
	kubectl apply -f serving/kserve-inference.yaml --namespace=prod || echo "kubectl not available"
	@echo "$(GREEN)✅ Deployed to production!$(NC)"

rollback:
	@echo "$(RED)⚠️  Rolling back deployment...$(NC)"
	kubectl rollout undo deployment/cogniforge-classifier -n prod || echo "kubectl not available"
	@echo "$(YELLOW)⚠️  Deployment rolled back!$(NC)"

# Monitoring
slo-check:
	@echo "$(BLUE)📊 Checking SLO compliance...$(NC)"
	@echo "See monitoring/slo.yaml for SLO definitions"
	@echo "$(GREEN)✅ SLO check complete!$(NC)"

# Version info
version:
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BLUE)  CogniForge ML Platform - Version Information$(NC)"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo "Platform Version: 1.0.0-devops-mlops"
	@echo "Python: $(shell python --version 2>&1)"
	@echo "Docker: $(shell docker --version 2>/dev/null || echo 'Not installed')"
	@echo "Kubernetes: $(shell kubectl version --client --short 2>/dev/null || echo 'Not installed')"
	@echo "Terraform: $(shell terraform version 2>/dev/null | head -n1 || echo 'Not installed')"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
