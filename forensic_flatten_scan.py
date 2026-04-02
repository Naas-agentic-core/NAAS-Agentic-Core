import re
import os

def run():
    print("Searching for history flattening patterns")
    os.system('grep -rn "\.join" microservices/orchestrator_service/src/services/overmind/ | grep "messages"')
    os.system('grep -rn "recent_messages" microservices/orchestrator_service/src/services/overmind/')

run()
