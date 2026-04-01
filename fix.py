from pathlib import Path

TEST_FILE_PATH = Path("tests/microservices/test_agent_chat_contract.py")
OLD_SIGNATURE = "async def ainvoke(self, inputs: dict[str, object]):"
NEW_SIGNATURE = "async def ainvoke(self, inputs: dict[str, object], config: dict | None = None):"

code = TEST_FILE_PATH.read_text()
updated_code = code.replace(OLD_SIGNATURE, NEW_SIGNATURE)
TEST_FILE_PATH.write_text(updated_code)
