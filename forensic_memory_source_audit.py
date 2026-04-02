import re
import os

def run():
    print("[MEMORY_SOURCE] Checking API routes for history_messages")
    os.system('grep -rn "history_messages" microservices/orchestrator_service/src/api/')
    print("[MEMORY_SOURCE] Checking API routes for DB conversation fetching")
    os.system('grep -rn "_ensure_conversation" microservices/orchestrator_service/src/api/')
run()
