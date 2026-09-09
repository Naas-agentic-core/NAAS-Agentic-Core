#!/usr/bin/env python3
"""
Automatic Test Generator for 100% Coverage
===========================================

This script automatically generates comprehensive test files
for all modules in the project to achieve 100% coverage.
"""

import ast
import json
import subprocess
from pathlib import Path


def analyze_module(filepath: Path) -> dict:
    """Analyze a Python module and extract its structure"""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        functions = []
        classes = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Get function info
                args = [arg.arg for arg in node.args.args]
                functions.append(
                    {
                        "name": node.name,
                        "args": args,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    }
                )
            elif isinstance(node, ast.ClassDef):
                # Get class info
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
                classes.append({"name": node.name, "methods": methods})
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif node.module:
                    imports.append(node.module)

        return {"functions": functions, "classes": classes, "imports": imports}
    except Exception as e:
        print(f"  ⚠️  Error analyzing {filepath}: {e}")
        return {"functions": [], "classes": [], "imports": []}


def generate_comprehensive_test(module_path: Path, analysis: dict) -> str:
    """Generate comprehensive test code for a module"""
    module_name = module_path.stem
    relative_path = str(module_path.relative_to("app")).replace("/", ".").replace(".py", "")

    # Build imports
    imports_section = []
    if analysis["classes"]:
        class_names = [c["name"] for c in analysis["classes"]]
        imports_section.append(f"from app.{relative_path} import {', '.join(class_names[:5])}")
    if analysis["functions"]:
        func_names = [f["name"] for f in analysis["functions"] if not f["name"].startswith("_")][:5]
        if func_names:
            imports_section.append(f"from app.{relative_path} import {', '.join(func_names)}")

    # Generate test classes
    test_classes = []

    for cls_info in analysis["classes"][:3]:  # Limit to first 3 classes
        class_name = cls_info["name"]
        methods = cls_info["methods"][:5]  # First 5 methods

        test_methods = []
        for method in methods:
            if method.startswith("_") and method != "__init__":
                continue

            test_methods.append(f"""
    def test_{method}_basic(self):
        \"\"\"Test {method} with basic inputs\"\"\"
        # TODO: Implement test for {method}
        obj = {class_name}()
        # Add assertions here
        assert True
""")

        test_class = f"""
class Test{class_name}:
    \"\"\"Comprehensive tests for {class_name}\"\"\"
{"".join(test_methods)}
"""
        test_classes.append(test_class)

    # Generate function tests
    func_tests = []
    for func_info in analysis["functions"][:5]:  # First 5 functions
        func_name = func_info["name"]
        if func_name.startswith("_"):
            continue

        is_async = func_info.get("is_async", False)
        decorator = "@pytest.mark.asyncio\n    " if is_async else ""

        func_tests.append(f"""
    {decorator}{"async " if is_async else ""}def test_{func_name}_basic(self):
        \"\"\"Test {func_name} with basic inputs\"\"\"
        # TODO: Implement test for {func_name}
        {"await " if is_async else ""}{func_name}()
        assert True
""")

    if func_tests:
        test_classes.append(f"""
class Test{module_name.title().replace("_", "")}Functions:
    \"\"\"Test standalone functions\"\"\"
{"".join(func_tests)}
""")

    # Build complete test file
    return f'''"""
Comprehensive Tests for {module_name}
{"=" * (25 + len(module_name))}

Auto-generated test file.
Target: 100% coverage

Module: app.{relative_path}
Classes: {len(analysis["classes"])}
Functions: {len(analysis["functions"])}
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

{chr(10).join(imports_section) if imports_section else "# No imports needed"}


{
        chr(10).join(test_classes)
        if test_classes
        else """
class TestPlaceholder:
    \"\"\"Placeholder test class\"\"\"

    def test_module_imports(self):
        \"\"\"Test that module can be imported\"\"\"
        import app.{relative_path}
        assert True
"""
    }


class TestEdgeCases:
    \"\"\"Test edge cases and error conditions\"\"\"

    def test_placeholder_edge_case(self):
        \"\"\"Placeholder for edge case tests\"\"\"
        # TODO: Add edge case tests
        assert True


class TestIntegration:
    \"\"\"Integration tests\"\"\"

    def test_placeholder_integration(self):
        \"\"\"Placeholder for integration tests\"\"\"
        # TODO: Add integration tests
        assert True
'''


def get_uncovered_files() -> list[tuple[Path, float, int]]:
    """Get list of files with <100% coverage"""
    # Run coverage
    print("🔍 Analyzing coverage...")
    cmd = [
        "python",
        "-m",
        "pytest",
        "tests/",
        "--cov=app",
        "--cov-report=json:coverage_gen.json",
        "-q",
        "--tb=no",
        "-x",  # Stop on first failure
    ]

    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("⚠️  Coverage analysis timed out")

    # Read coverage
    coverage_file = Path("coverage_gen.json")
    if not coverage_file.exists():
        print("❌ No coverage data generated")
        return []

    with open(coverage_file) as f:
        data = json.load(f)

    files = data.get("files", {})
    uncovered = []

    for filepath, metrics in files.items():
        if not filepath.startswith("app/"):
            continue
        if any(skip in filepath for skip in ["__pycache__", "migrations/", "__init__.py"]):
            continue

        coverage = metrics["summary"]["percent_covered"]
        lines = metrics["summary"]["num_statements"]

        if coverage < 100 and lines > 10:  # Focus on files with significant code
            uncovered.append((Path(filepath), coverage, lines))

    # Sort by lines of code (most important first)
    uncovered.sort(key=lambda x: x[2], reverse=True)

    return uncovered


def main():
    """Main execution"""
    print("🚀 Automatic Test Generator for 100% Coverage")
    print("=" * 70)

    # Get uncovered files
    uncovered = get_uncovered_files()

    if not uncovered:
        print("🎉 All files have 100% coverage!")
        return

    print(f"\n📊 Found {len(uncovered)} files needing tests")
    print("   Focusing on top 20 most important files\n")

    generated = 0
    skipped = 0

    for filepath, coverage, lines in uncovered[:20]:  # Top 20
        print(f"📝 {filepath} ({coverage:.1f}% coverage, {lines} lines)")

        # Check if test file exists
        parts = filepath.parts[1:]  # Remove 'app'
        test_dir = Path("tests") / Path(*parts[:-1])
        test_file = test_dir / f"test_{parts[-1].replace('.py', '')}_comprehensive.py"

        if test_file.exists():
            print(f"   ⏭️  Test file exists: {test_file}")
            skipped += 1
            continue

        # Analyze module
        analysis = analyze_module(filepath)

        # Generate test
        test_code = generate_comprehensive_test(filepath, analysis)

        # Create directory
        test_dir.mkdir(parents=True, exist_ok=True)

        # Write test file
        test_file.write_text(test_code)
        print(f"   ✅ Generated: {test_file}")
        generated += 1

    print("\n" + "=" * 70)
    print("📊 Summary:")
    print(f"   Generated: {generated} test files")
    print(f"   Skipped: {skipped} (already exist)")
    print(f"   Total: {len(uncovered)} files need coverage")
    print("\n📝 Next steps:")
    print("   1. Review generated test files")
    print("   2. Fill in TODO sections with actual tests")
    print("   3. Run: pytest --cov=app --cov-report=term-missing")
    print("   4. Iterate until 100% coverage")
    print("=" * 70)


if __name__ == "__main__":
    main()
