import logging

from microservices.orchestrator_service.src.services.overmind.planning.deep_indexer import build_index

# Configure logging to print to console
logging.basicConfig(level=logging.INFO)

print("Building index...")
analysis = build_index(".")
print(f"Total Files: {analysis.total_files}")
print(f"Total Lines: {analysis.total_lines}")

js_files = [
    f for f in analysis.files if f.file_path.endswith(".js") or f.file_path.endswith(".jsx")
]
print(f"JS/JSX Files: {len(js_files)}")
for f in js_files:
    print(f" - {f.relative_path}")
