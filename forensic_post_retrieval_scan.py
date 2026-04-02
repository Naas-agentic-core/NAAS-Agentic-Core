import re
import os

def run():
    print("[POST_RETRIEVAL] Scanning SynthesizerNode")
    os.system('cat microservices/orchestrator_service/src/services/overmind/graph/search.py | grep -n -B 5 -A 20 "class SynthesizerNode"')
run()
