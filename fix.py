import re

with open("tests/microservices/test_agent_chat_contract.py", "r") as f:
    code = f.read()

code = code.replace(
    "async def ainvoke(self, inputs: dict[str, object]):",
    "async def ainvoke(self, inputs: dict[str, object], config: dict | None = None):"
)

with open("tests/microservices/test_agent_chat_contract.py", "w") as f:
    f.write(code)
