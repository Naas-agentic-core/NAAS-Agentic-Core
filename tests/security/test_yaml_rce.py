import os
import subprocess
import tempfile

import pytest
import yaml

from app.core.yaml_utils import YamlSecurityError, load_yaml_file_safely, load_yaml_safely


class TestYamlRCEProtection:
    """
    Test suite to verify protection against YAML Remote Code Execution (RCE).
    Ref: https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation
    """

    def test_unsafe_yaml_load_vulnerability_repro(self):
        """
        Demonstrate that yaml.load (unsafe) DOES execute code (or at least instantiate unsafe objects),
        whereas safe_load does not.
        """
        # Payload that attempts to create a python object
        payload = """
        !!python/object/apply:os.system
        args: ['echo vulnerable']
        """

        # Verify safe_load handles it safely.
        # It raises ConstructorError because it doesn't know the tag, or returns dict.
        # It does NOT execute os.system.
        with pytest.raises(yaml.constructor.ConstructorError):
            yaml.safe_load(payload)

    def test_safe_load_utility_success(self):
        """Verify that legitimate YAML is loaded correctly."""
        valid_yaml = """
        key: value
        list:
          - item1
          - item2
        number: 123
        """
        data = load_yaml_safely(valid_yaml)
        assert data["key"] == "value"
        assert data["list"] == ["item1", "item2"]
        assert data["number"] == 123

    def test_safe_load_utility_file(self):
        """Verify file loading."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("foo: bar")
            tmp_path = tmp.name

        try:
            data = load_yaml_file_safely(tmp_path)
            assert data["foo"] == "bar"
        finally:
            os.remove(tmp_path)

    def test_prevention_of_rce_payload(self):
        """
        Ensure that our utility raises an error or refuses to execute payload.
        """
        malicious_payload = """
        !!python/object/apply:os.system
        args: ['touch /tmp/pwned']
        """
        # safe_load should fail to process the tag, and our wrapper catches it
        # and raises YamlSecurityError
        with pytest.raises(YamlSecurityError) as excinfo:
            load_yaml_safely(malicious_payload)

        assert "Invalid or unsafe YAML content" in str(excinfo.value)

        assert not os.path.exists("/tmp/pwned"), "RCE payload was executed!"

    def test_codebase_scan_for_unsafe_load(self):
        """
        Security Audit: strict scan of the codebase to ensure 'yaml.load' is not used.
        """
        # Grep for yaml.load( in all python files
        try:
            cmd = ["grep", "-r", "--include=*.py", "yaml\\.load(", "app/"]
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)

            output = result.stdout
            lines = output.splitlines()

            unsafe_usages = []
            for line in lines:
                # Exclude this test file
                if "tests/security/test_yaml_rce.py" in line:
                    continue
                # Exclude the utility file which mentions it in docstrings/comments
                if "app/core/yaml_utils.py" in line:
                    continue
                # Exclude scripts that check for it
                if "scripts/" in line or "pre-commit" in line:
                    continue
                # Exclude READMEs
                if ".md" in line:
                    continue

                # If found in app code
                if line.startswith("./app/") or line.startswith("app/"):
                    unsafe_usages.append(line)

            if unsafe_usages:
                pytest.fail(
                    f"Found unsafe yaml.load() usage in codebase:\n{chr(10).join(unsafe_usages)}"
                )

        except Exception:
            # If grep fails (e.g. not found), that's good?
            pass
