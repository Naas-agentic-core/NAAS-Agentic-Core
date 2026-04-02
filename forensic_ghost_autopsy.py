import re
import os

def run():
    print("Searching for '؟'")
    os.system('grep -rn "؟" microservices/orchestrator_service/src/')
    os.system('grep -rn "?" microservices/orchestrator_service/src/services/overmind/')
run()
