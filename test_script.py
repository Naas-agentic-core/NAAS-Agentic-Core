import asyncio
from app.infrastructure.clients.memory_client import MemoryClient
from app.services.knowledge.prerequisite_checker import PrerequisiteChecker

async def main():
    print("Testing client connectivity")
