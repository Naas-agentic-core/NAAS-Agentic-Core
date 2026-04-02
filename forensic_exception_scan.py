import re
import os

def run():
    print("[EXCEPT] Searching for exceptions returning '؟'")
    os.system('grep -rn "؟" microservices/orchestrator_service/src/ | grep except')
run()
