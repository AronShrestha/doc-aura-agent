from __future__ import annotations

from collections import defaultdict

import networkx as nx

from .types import ExtractedArtifact, ExtractedEdge, RepoSnapshot
from .utils import stable_artifact_id


def add_service_flow_artifacts(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
) -> tuple[list[ExtractedArtifact], list[ExtractedEdge]]:
    module_artifacts = [a for a in artifacts if a.category == "module"]
    if not module_artifacts:
        return artifacts, edges

    graph = nx.Graph()
    modules_by_id = {a.artifact_id: a for a in module_artifacts}
    for module in module_artifacts:
        graph.add_node(module.artifact_id)
    for edge in edges:
        if edge.kind in {"imports", "calls"} and edge.src_artifact_id in modules_by_id and edge.dst_artifact_id in modules_by_id:
            graph.add_edge(edge.src_artifact_id, edge.dst_artifact_id)

    flow_artifacts: list[ExtractedArtifact] = []
    flow_edges: list[ExtractedEdge] = []
    components = [sorted(component) for component in nx.connected_components(graph)]
    for idx, component in enumerate(sorted(components, key=lambda c: (-len(c), c[0])), start=1):
        modules = [modules_by_id[mid] for mid in component]
        if len(modules) < 2:
            continue
        name = _cluster_name(idx, modules)
        locator = f"service_cluster:{name}"
        flow_id = stable_artifact_id(snapshot.repo_id, "flow", locator)
        flow_artifacts.append(
            ExtractedArtifact(
                artifact_id=flow_id,
                category="flow",
                name=name,
                canonical_locator=locator,
                source_file=None,
                source_line_start=None,
                source_line_end=None,
                payload={"modules": [m.name for m in modules], "module_count": len(modules), "cluster_strategy": "module_graph_connected_component"},
            )
        )
        for module in modules:
            flow_edges.append(ExtractedEdge(module.artifact_id, flow_id, "part_of_flow"))
    return artifacts + flow_artifacts, edges + flow_edges


def _cluster_name(index: int, modules: list[ExtractedArtifact]) -> str:
    prefixes: defaultdict[str, int] = defaultdict(int)
    for module in modules:
        parts = module.name.split(".")
        if len(parts) > 1:
            prefixes[parts[0]] += 1
    if prefixes:
        prefix = max(prefixes.items(), key=lambda item: item[1])[0]
        return f"{prefix} service cluster {index}"
    return f"service cluster {index}"
