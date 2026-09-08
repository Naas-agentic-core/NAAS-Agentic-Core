"""Tests for refactored architecture."""

import pytest

from app.application.use_cases.planning.refactored_planner import (
    ContextAnalyzer,
    Plan,
    PlanOptimizer,
    PlanValidator,
    RefactoredPlanner,
    Task,
    TaskGenerator,
)
from app.application.use_cases.routing.routing_strategies import (
    LatencyBasedStrategy,
    RoundRobinStrategy,
    RoutingRequest,
    ServiceEndpoint,
    StrategyFactory,
)
from app.infrastructure.patterns import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    DIContainer,
    Event,
    EventBus,
    RequestContext,
    build_request_pipeline,
)


class TestRoutingStrategies:
    """Test routing strategies."""

    def test_round_robin_strategy(self):
        """Test round-robin routing."""
        endpoints = [
            ServiceEndpoint(id="e1", url="http://service1"),
            ServiceEndpoint(id="e2", url="http://service2"),
            ServiceEndpoint(id="e3", url="http://service3"),
        ]

        strategy = RoundRobinStrategy(endpoints)
        request = RoutingRequest(request_id="r1", method="GET", path="/api/test", headers={})

        result1 = strategy.execute(request)
        result2 = strategy.execute(request)
        result3 = strategy.execute(request)
        result4 = strategy.execute(request)

        assert result1.id == "e1"
        assert result2.id == "e2"
        assert result3.id == "e3"
        assert result4.id == "e1"

    def test_latency_based_strategy(self):
        """Test latency-based routing."""
        endpoints = [
            ServiceEndpoint(id="e1", url="http://service1", avg_latency_ms=100),
            ServiceEndpoint(id="e2", url="http://service2", avg_latency_ms=50),
            ServiceEndpoint(id="e3", url="http://service3", avg_latency_ms=200),
        ]

        strategy = LatencyBasedStrategy(endpoints)
        request = RoutingRequest(request_id="r1", method="GET", path="/api/test", headers={})

        result = strategy.execute(request)
        assert result.id == "e2"

    def test_strategy_factory(self):
        """Test strategy factory."""
        endpoints = [ServiceEndpoint(id="e1", url="http://service1")]

        strategy = StrategyFactory.create("round_robin", endpoints)
        assert isinstance(strategy, RoundRobinStrategy)

        strategies = StrategyFactory.list_strategies()
        assert "round_robin" in strategies
        assert "latency_based" in strategies


class TestCircuitBreaker:
    """Test circuit breaker pattern."""

    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config)

        def successful_operation():
            return "success"

        result = breaker.call(successful_operation)
        assert result == "success"
        assert breaker.get_state() == CircuitState.CLOSED

    def test_circuit_breaker_opens_on_failures(self):
        """Test circuit breaker opens after failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config)

        def failing_operation():
            raise RuntimeError("Operation failed")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                breaker.call(failing_operation)

        assert breaker.get_state() == CircuitState.OPEN

    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker recovery."""
        config = CircuitBreakerConfig(failure_threshold=2, success_threshold=2, timeout_seconds=0.1)
        breaker = CircuitBreaker(config)

        def failing_operation():
            raise RuntimeError("Failed")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(failing_operation)

        assert breaker.get_state() == CircuitState.OPEN

        import time

        time.sleep(0.2)

        def successful_operation():
            return "success"

        breaker.call(successful_operation)
        assert breaker.get_state() == CircuitState.HALF_OPEN

        breaker.call(successful_operation)
        assert breaker.get_state() == CircuitState.CLOSED


class TestEventBus:
    """Test event bus pattern."""

    def test_event_subscription_and_publishing(self):
        """Test event subscription and publishing."""
        bus = EventBus()
        received_events = []

        def handler(event: Event):
            received_events.append(event)

        bus.subscribe("test_event", handler)

        event = Event(event_type="test_event", data={"message": "Hello"})
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].data["message"] == "Hello"

    def test_event_history(self):
        """Test event history tracking."""
        bus = EventBus()

        event1 = Event(event_type="event1", data={"id": 1})
        event2 = Event(event_type="event2", data={"id": 2})

        bus.publish(event1)
        bus.publish(event2)

        history = bus.get_history()
        assert len(history) == 2

        event1_history = bus.get_history(event_type="event1")
        assert len(event1_history) == 1


class TestDependencyInjection:
    """Test dependency injection container."""

    def test_register_and_resolve(self):
        """Test service registration and resolution."""
        container = DIContainer()

        class Service:
            def get_value(self):
                return "test"

        container.register(Service, Service)
        service = container.resolve(Service)

        assert isinstance(service, Service)
        assert service.get_value() == "test"

    def test_singleton_registration(self):
        """Test singleton registration."""
        container = DIContainer()

        class Service:
            pass

        instance = Service()
        container.register_singleton(Service, instance)

        resolved1 = container.resolve(Service)
        resolved2 = container.resolve(Service)

        assert resolved1 is instance
        assert resolved2 is instance


class TestChainOfResponsibility:
    """Test chain of responsibility pattern."""

    def test_authentication_handler(self):
        """Test authentication in chain."""
        pipeline = build_request_pipeline()

        context = RequestContext(data={"auth_token": "valid_token"})
        result = pipeline.handle(context)

        assert result is None or result.metadata.get("authenticated")

    def test_failed_authentication(self):
        """Test failed authentication."""
        pipeline = build_request_pipeline()

        context = RequestContext(data={})
        result = pipeline.handle(context)

        assert result is not None
        assert result.has_errors()
        assert "authentication" in result.errors[0].lower()


class TestRefactoredPlanner:
    """Test refactored planner."""

    def test_plan_generation(self):
        """Test plan generation."""
        planner = RefactoredPlanner()

        plan = planner.generate_plan("Create a simple task")

        assert "plan_id" in plan
        assert plan["objective"] == "Create a simple task"
        assert len(plan["tasks"]) > 0

    def test_plan_validation(self):
        """Test plan validation."""
        validator = PlanValidator()

        valid_plan = Plan(
            plan_id="p1",
            objective="Test",
            tasks=[
                Task(
                    task_id="t1",
                    description="Task",
                    tool_name="test",
                    tool_args={},
                    dependencies=[],
                )
            ],
            metadata={},
        )

        is_valid, errors = validator.validate(valid_plan)
        assert is_valid
        assert len(errors) == 0

    def test_plan_optimization(self):
        """Test plan optimization."""
        optimizer = PlanOptimizer()

        tasks = [
            Task(
                task_id="t3",
                description="Task 3",
                tool_name="test",
                tool_args={},
                dependencies=["t1", "t2"],
            ),
            Task(
                task_id="t1", description="Task 1", tool_name="test", tool_args={}, dependencies=[]
            ),
            Task(
                task_id="t2",
                description="Task 2",
                tool_name="test",
                tool_args={},
                dependencies=["t1"],
            ),
        ]

        plan = Plan(plan_id="p1", objective="Test", tasks=tasks, metadata={})

        optimized = optimizer.optimize(plan)

        task_ids = [t.task_id for t in optimized.tasks]
        assert task_ids.index("t1") < task_ids.index("t2")
        assert task_ids.index("t2") < task_ids.index("t3")

    def test_context_analyzer(self):
        """Test context analyzer."""
        analyzer = ContextAnalyzer()

        analysis = analyzer.analyze("This is a simple test", None)

        assert "complexity" in analysis
        assert "language" in analysis
        assert analysis["language"] == "english"

    def test_task_generator(self):
        """Test task generator."""
        generator = TaskGenerator()

        analysis = {"complexity": "medium"}
        tasks = generator.generate_tasks("Test objective", analysis)

        assert len(tasks) > 0
        assert all(isinstance(task, Task) for task in tasks)


class TestIntegration:
    """Integration tests."""

    def test_full_planning_flow(self):
        """Test complete planning flow."""
        planner = RefactoredPlanner()

        plan = planner.generate_plan("Build a complex system with multiple components", max_tasks=5)

        assert planner.validate_plan(plan)
        assert len(plan["tasks"]) <= 5

        capabilities = planner.get_capabilities()
        assert "semantic" in capabilities
        assert "optimization" in capabilities
