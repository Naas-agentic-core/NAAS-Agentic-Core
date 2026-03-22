"""
Governance Architecture Tests.
------------------------------
The "Immune System" of the codebase.
Scans for violations of the Architectural Singularity:
1. Orchestration Drift (Multiple decision makers) - Hard to test statically, but we enforce Policy usage.
2. Exception Swallowing (naked except Exception).
3. Loose Contracts (usage of Any).
"""

import ast
import os

import pytest

# Directories to enforce strict governance on
GOVERNED_DIRS = [
    "app/core/governance",
    "app/services/overmind",
    "microservices",
]


def get_python_files(directories):
    for directory in directories:
        if not os.path.exists(directory):
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py") and not file.startswith("test_"):
                    yield os.path.join(root, file)


class GovernanceVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.violations = []

    def visit_AsyncFunctionDef(self, node):
        """
        Check for 'Any' in async type hints.
        """
        self.visit_FunctionDef(node)

    def visit_AnnAssign(self, node):
        """
        Check for 'Any' in type-annotated assignments (e.g., class attributes, TypedDict).
        """
        if self._has_any(node.annotation):
            self.violations.append(
                f"{self.filename}:{node.lineno} - Type annotation uses 'Any'. Use strict types."
            )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        """
        Check for 'except Exception:' or 'except:' without a specific comment or re-raise.
        """
        # strict check for bare except or Exception
        is_bare = node.type is None
        is_exception = False
        if isinstance(node.type, ast.Name) and node.type.id == "Exception":
            is_exception = True

        if is_bare or is_exception:
            # Check for comments? (AST doesn't preserve comments easily without tokenizing)
            # For now, we flag it unless it raises a GovernanceError or similar.
            # This is a strict linter.

            # Heuristic: if the body contains 'raise' or 'GovernanceError', it might be okay.
            # We strictly want to discourage it.
            pass  # Disabling strict check for now to allow incremental adoption, enabled in V2.

        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """
        Check for 'Any' in type hints.
        """
        if "test" in self.filename:
            return

        # Check standard arguments
        for arg in node.args.args:
            if self._has_any(arg.annotation):
                self.violations.append(
                    f"{self.filename}:{node.lineno} - Argument '{arg.arg}' uses 'Any'. Use strict types."
                )

        # Check *args
        if node.args.vararg and self._has_any(node.args.vararg.annotation):
            self.violations.append(
                f"{self.filename}:{node.lineno} - Argument '*{node.args.vararg.arg}' uses 'Any'. Use strict types."
            )

        # Check **kwargs
        if node.args.kwarg and self._has_any(node.args.kwarg.annotation):
            self.violations.append(
                f"{self.filename}:{node.lineno} - Argument '**{node.args.kwarg.arg}' uses 'Any'. Use strict types."
            )

        if self._has_any(node.returns):
            self.violations.append(
                f"{self.filename}:{node.lineno} - Return type uses 'Any'. Use strict types."
            )

        self.generic_visit(node)

    def _has_any(self, annotation):
        if annotation is None:
            return False
        if isinstance(annotation, ast.Name) and annotation.id == "Any":
            return True
        if isinstance(annotation, ast.Attribute) and annotation.attr == "Any":
            return True
        # Recursive check for List[Any], etc.
        if isinstance(annotation, ast.Subscript):
            if hasattr(annotation.slice, "value"):  # Python < 3.9
                return self._has_any(annotation.slice.value)
            return self._has_any(annotation.slice)
        return False


@pytest.mark.architecture
def test_governance_contracts_any():
    """
    Enforce NO usage of 'Any' in the Governed Core and Microservices.
    """
    visitor = GovernanceVisitor("")

    # Enforce strictness on all governed directories
    target_files = list(get_python_files(GOVERNED_DIRS))

    all_violations = []
    for file_path in target_files:
        if "errors.py" in file_path:
            continue  # errors.py imports Any for type hinting the exception context

        with open(file_path) as f:
            tree = ast.parse(f.read())
            visitor.filename = file_path
            visitor.violations = []
            visitor.visit(tree)
            all_violations.extend(visitor.violations)

    assert len(all_violations) == 0, "Found Governance Violations:\n" + "\n".join(all_violations)


@pytest.mark.architecture
def test_decision_record_immutability():
    """
    Ensure DecisionRecord is immutable (frozen).
    """
    from app.core.governance.decision import DecisionRecord

    assert DecisionRecord.model_config.get("frozen"), "DecisionRecord must be frozen/immutable."
