import collections

def toposort(nodes, graph):
    in_degree = {u: 0 for u in nodes}
    for u in nodes:
        for v in graph.get(u, []):
            if v in in_degree:
                in_degree[v] += 1

    queue = collections.deque([u for u in nodes if in_degree[u] == 0])
    ordered = []

    while queue:
        u = queue.popleft()
        ordered.append(u)
        for v in graph.get(u, []):
            if v in in_degree:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

    # Handle cycles or isolated nodes implicitly
    # Nodes left with in_degree > 0 mean there are cycles.
    # For now, just append any remaining nodes.
    remaining = set(nodes) - set(ordered)
    ordered.extend(list(remaining))
    return ordered

print(toposort([1,2,3], {1: [2, 3], 2: [3]}))
