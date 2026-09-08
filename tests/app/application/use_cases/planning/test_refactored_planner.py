import pytest
from app.application.use_cases.planning.refactored_planner import (
    ContextAnalyzer,
    Plan,
    PlanOptimizer,
    PlanValidator,
    RefactoredPlanner,
    Task,
    TaskGenerator,
    PlannerConfig
)

class TestRefactoredPlanner:
    """Test refactored planner."""

    def test_plan_generation(self):
        """Test plan generation."""
        planner = RefactoredPlanner()

        plan = planner.generate_plan("Create a simple task")

        assert "plan_id" in plan
        assert plan["objective"] == "Create a simple task"
        assert len(plan["tasks"]) > 0

    def test_generate_plan_invalid_raises_error(self, monkeypatch):
        """Test generate plan raises ValueError when plan validation fails."""
        planner = RefactoredPlanner()

        # Mock validator to fail
        class MockValidator:
            def validate(self, plan: Plan):
                return False, ["Mock validation error"]

        planner.config = PlannerConfig(
            event_bus=planner.config.event_bus,
            validator=MockValidator(),
            optimizer=planner.config.optimizer,
            context_analyzer=planner.config.context_analyzer,
            task_generator=planner.config.task_generator
        )

        with pytest.raises(ValueError, match=r"Invalid plan:.*Mock validation error"):
            planner.generate_plan("Test objective")

    def test_validate_plan_dict_invalid_format(self):
        """Test validate_plan method handles malformed dictionary and returns False."""
        planner = RefactoredPlanner()
        # Invalid format (missing tasks) will cause _from_dict to raise KeyError
        invalid_plan_dict = {
            "plan_id": "123",
            "objective": "Test",
        }

        is_valid = planner.validate_plan(invalid_plan_dict)
        assert not is_valid

    def test_plan_validation_success(self):
        """Test plan validation with a valid plan."""
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

    def test_plan_validation_missing_objective(self):
        """Test plan validation with missing objective."""
        validator = PlanValidator()

        invalid_plan = Plan(
            plan_id="p1",
            objective="",
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

        is_valid, errors = validator.validate(invalid_plan)
        assert not is_valid
        assert "Objective is required" in errors

    def test_plan_validation_missing_tasks(self):
        """Test plan validation with empty tasks."""
        validator = PlanValidator()

        invalid_plan = Plan(
            plan_id="p1",
            objective="Test",
            tasks=[],
            metadata={},
        )

        is_valid, errors = validator.validate(invalid_plan)
        assert not is_valid
        assert "Plan must have at least one task" in errors

    def test_plan_validation_invalid_dependency(self):
        """Test plan validation with invalid dependency."""
        validator = PlanValidator()

        invalid_plan = Plan(
            plan_id="p1",
            objective="Test",
            tasks=[
                Task(
                    task_id="t1",
                    description="Task",
                    tool_name="test",
                    tool_args={},
                    dependencies=["non_existent_task"],
                )
            ],
            metadata={},
        )

        is_valid, errors = validator.validate(invalid_plan)
        assert not is_valid
        assert any("invalid dependency" in error for error in errors)
        assert any("non_existent_task" in error for error in errors)

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

    def test_context_analyzer_english(self):
        """Test context analyzer for english."""
        analyzer = ContextAnalyzer()
        analysis = analyzer.analyze("Test", None)
        assert analysis["language"] == "english"
        assert analysis["complexity"] == "simple"
        assert analysis["objective_length"] == len("Test")
        assert not analysis["requires_multi_step"]
        assert "has_context" not in analysis

    def test_context_analyzer_arabic(self):
        """Test context analyzer detects arabic."""
        analyzer = ContextAnalyzer()
        analysis = analyzer.analyze("اختبار", None)
        assert analysis["language"] == "arabic"
        assert analysis["complexity"] == "simple"

    def test_context_analyzer_complexity_medium(self):
        """Test context analyzer estimates medium complexity."""
        analyzer = ContextAnalyzer()
        objective = "This objective has exactly eight words in it"
        analysis = analyzer.analyze(objective, None)
        assert analysis["complexity"] == "medium"
        assert not analysis["requires_multi_step"]

    def test_context_analyzer_complexity_complex(self):
        """Test context analyzer estimates complex complexity and multi step."""
        analyzer = ContextAnalyzer()
        objective = "This is a very long objective that has more than fifteen words in it to trigger the complex complexity estimation."
        analysis = analyzer.analyze(objective, None)
        assert analysis["complexity"] == "complex"
        assert analysis["requires_multi_step"]

    def test_context_analyzer_with_context(self):
        """Test context analyzer with provided context."""
        analyzer = ContextAnalyzer()
        context = {"user_id": 123, "preferences": "strict"}
        analysis = analyzer.analyze("Test", context)
        assert analysis.get("has_context") is True
        assert analysis.get("context_keys") == ["user_id", "preferences"]

    def test_task_generator_simple(self):
        """Test task generator generates tasks for simple objective."""
        generator = TaskGenerator()
        analysis = {"complexity": "simple"}
        tasks = generator.generate_tasks("Simple objective", analysis)

        assert len(tasks) == 1
        assert tasks[0].tool_name == "execute"

    def test_task_generator_medium(self):
        """Test task generator generates tasks for medium objective."""
        generator = TaskGenerator()
        analysis = {"complexity": "medium"}
        tasks = generator.generate_tasks("Medium objective", analysis)

        assert len(tasks) == 3
        assert tasks[0].tool_name == "analyze"
        assert tasks[1].tool_name == "execute"
        assert tasks[2].tool_name == "verify"
        assert tasks[1].dependencies == ["task_1"]
        assert tasks[2].dependencies == ["task_2"]

    def test_task_generator_complex(self):
        """Test task generator generates tasks for complex objective."""
        generator = TaskGenerator()
        analysis = {"complexity": "complex"}
        tasks = generator.generate_tasks("Complex objective", analysis)

        assert len(tasks) == 5
        assert tasks[0].tool_name == "deep_analyze"
        assert tasks[1].tool_name == "decompose"
        assert tasks[2].tool_name == "execute_parallel"
        assert tasks[3].tool_name == "integrate"
        assert tasks[4].tool_name == "verify"

    def test_task_generator_max_tasks(self):
        """Test task generator respects max_tasks limit."""
        generator = TaskGenerator()
        analysis = {"complexity": "complex"}
        tasks = generator.generate_tasks("Complex objective", analysis, max_tasks=2)

        assert len(tasks) == 2
        assert tasks[0].tool_name == "deep_analyze"
        assert tasks[1].tool_name == "decompose"


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
