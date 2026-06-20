from typing import cast

import networkx as nx


class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self._name_to_id: dict[str, str] = {}

    def add_node(self, id: str, name: str, **attrs):
        self.graph.add_node(id, name=name, **attrs)
        self._name_to_id[name] = id

    def add_edge(self, from_id: str, to_id: str, **attrs):
        if from_id in self.graph.nodes and to_id in self.graph.nodes:
            self.graph.add_edge(from_id, to_id, **attrs)

    def get_node_id(self, name: str) -> str | None:
        return self._name_to_id.get(name)

    def get_node_name(self, node_id: str) -> str | None:
        return cast("str | None", self.graph.nodes[node_id].get("name"))

    def get_dependencies(self, name: str) -> list[str]:
        node_id = self.get_node_id(name)
        if node_id is None:
            return []
        return [
            n
            for succ in self.graph.successors(node_id)
            if (n := self.get_node_name(succ)) is not None
        ]

    def get_dependents(self, name: str) -> list[str]:
        node_id = self.get_node_id(name)
        if node_id is None:
            return []
        return [
            n
            for pred in self.graph.predecessors(node_id)
            if (n := self.get_node_name(pred)) is not None
        ]

    def get_all_dependents_recursive(self, name: str) -> set[str]:
        node_id = self.get_node_id(name)
        if node_id is None:
            return set()

        descendants = nx.descendants(self.graph.reverse(copy=False), node_id)
        return {n for node in descendants if (n := self.get_node_name(node)) is not None}

    def get_all_dependencies_recursive(self, name: str) -> set[str]:
        node_id = self.get_node_id(name)
        if node_id is None:
            return set()

        ancestors = nx.descendants(self.graph, node_id)
        return {n for node in ancestors if (n := self.get_node_name(node)) is not None}

    def has_cycle(self) -> bool:
        try:
            nx.find_cycle(self.graph)
            return True
        except nx.NetworkXNoCycle:
            return False

    def get_cycles(self) -> list[list[str]]:
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return [
                [n for node in cycle if (n := self.get_node_name(node)) is not None]
                for cycle in cycles
                if cycle
            ]
        except Exception:
            return []

    def get_roots(self) -> list[str]:
        roots = [node for node in self.graph.nodes if self.graph.in_degree(node) == 0]
        return [n for node in roots if (n := self.get_node_name(node)) is not None]

    def get_leaves(self) -> list[str]:
        leaves = [node for node in self.graph.nodes if self.graph.out_degree(node) == 0]
        return [n for node in leaves if (n := self.get_node_name(node)) is not None]

    def to_tree_string(self, root: str | None = None, indent: str = "") -> str:
        if self.graph.number_of_nodes() == 0:
            return "(empty graph)"

        lines = []

        if root is None:
            roots = self.get_roots()
            for i, r in enumerate(roots):
                is_last = i == len(roots) - 1
                prefix = indent + ("└─ " if is_last else "├─ ")
                lines.append(prefix + r)
                child_lines = self._build_tree_lines(r, indent + ("    " if is_last else "│   "))
                lines.extend(child_lines)
        else:
            lines.append(root)
            child_lines = self._build_tree_lines(root, "    ")
            lines.extend(child_lines)

        return "\n".join(lines)

    def _build_tree_lines(self, name: str, indent: str) -> list[str]:
        deps = self.get_dependencies(name)
        lines = []
        for i, dep in enumerate(deps):
            is_last = i == len(deps) - 1
            prefix = indent + ("└─ " if is_last else "├─ ")
            lines.append(prefix + dep)
            child_lines = self._build_tree_lines(dep, indent + ("    " if is_last else "│   "))
            lines.extend(child_lines)
        return lines

    def to_dict(self) -> dict:
        nodes = []
        edges = []

        for node in self.graph.nodes:
            nodes.append({"id": node, "name": self.get_node_name(node), **self.graph.nodes[node]})

        for from_node, to_node in self.graph.edges:
            edges.append({"from": from_node, "to": to_node, **self.graph.edges[from_node, to_node]})

        return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyGraph":
        graph = cls()

        for node in data.get("nodes", []):
            node_id = node.get("id", node.get("name"))
            graph.add_node(node_id, **node)

        for edge in data.get("edges", []):
            graph.add_edge(edge.get("from"), edge.get("to"))

        return graph
