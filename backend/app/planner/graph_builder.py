"""
Graph Builder: Constructs a NetworkX DAG from the topic prerequisites table.

Provides utilities for querying ancestors, descendants, root/leaf nodes,
topological ordering, and cycle validation.
"""

import networkx as nx
from supabase import Client
from dataclasses import dataclass


@dataclass
class TopicNode:
    """Represents a topic in the knowledge graph."""
    id: str
    name: str
    slug: str
    description: str | None = None


class KnowledgeGraph:
    """
    A DAG (Directed Acyclic Graph) representing topic prerequisite relationships.
    
    Edges are directed: prerequisite → dependent.
    An edge (A → B) means "A must be learned before B".
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._topics: dict[str, TopicNode] = {}

    @classmethod
    def from_database(cls, supabase: Client) -> "KnowledgeGraph":
        """
        Build the knowledge graph from the database.
        Fetches all topics and prerequisite edges, constructs the DAG,
        and validates it is acyclic.
        """
        kg = cls()

        # Fetch all topics
        topics_res = supabase.table("topics").select("id, name, slug, description").execute()
        if topics_res.data:
            for t in topics_res.data:
                node = TopicNode(
                    id=t["id"],
                    name=t["name"],
                    slug=t["slug"],
                    description=t.get("description"),
                )
                kg._topics[t["id"]] = node
                kg.graph.add_node(t["id"], name=t["name"], slug=t["slug"])

        # Fetch all prerequisite edges
        prereqs_res = supabase.table("topic_prerequisites").select("topic_id, prerequisite_topic_id").execute()
        if prereqs_res.data:
            for edge in prereqs_res.data:
                # Edge direction: prerequisite → topic (must learn prereq first)
                kg.graph.add_edge(edge["prerequisite_topic_id"], edge["topic_id"])

        # Validate DAG
        if not nx.is_directed_acyclic_graph(kg.graph):
            cycles = list(nx.simple_cycles(kg.graph))
            raise ValueError(
                f"Knowledge graph contains cycles and is not a valid DAG. "
                f"Cycles detected: {cycles[:5]}"  # show up to 5 cycles
            )

        return kg

    def get_topic(self, topic_id: str) -> TopicNode | None:
        """Get topic metadata by ID."""
        return self._topics.get(topic_id)

    def get_prerequisites(self, topic_id: str) -> set[str]:
        """Get all prerequisite ancestors (transitive) for a topic."""
        if topic_id not in self.graph:
            return set()
        return nx.ancestors(self.graph, topic_id)

    def get_direct_prerequisites(self, topic_id: str) -> set[str]:
        """Get only the immediate prerequisites for a topic."""
        if topic_id not in self.graph:
            return set()
        return set(self.graph.predecessors(topic_id))

    def get_dependents(self, topic_id: str) -> set[str]:
        """Get all dependent descendants (transitive) for a topic."""
        if topic_id not in self.graph:
            return set()
        return nx.descendants(self.graph, topic_id)

    def get_root_topics(self) -> list[str]:
        """Get topics with no prerequisites (entry points)."""
        return [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0]

    def get_leaf_topics(self) -> list[str]:
        """Get topics with no dependents (terminal goals)."""
        return [n for n in self.graph.nodes() if self.graph.out_degree(n) == 0]

    def get_topological_order(self) -> list[str]:
        """Get all topics in valid topological order."""
        return list(nx.topological_sort(self.graph))

    def get_subgraph_topological_order(self, node_ids: set[str]) -> list[str]:
        """Get topological order for a subgraph of specific nodes."""
        subgraph = self.graph.subgraph(node_ids)
        return list(nx.topological_sort(subgraph))

    def would_create_cycle(self, prerequisite_id: str, topic_id: str) -> bool:
        """
        Check if adding an edge (prerequisite_id → topic_id) would create a cycle.
        Returns True if it would create a cycle (invalid), False if safe.
        """
        if prerequisite_id == topic_id:
            return True

        # Temporarily add the edge and check
        test_graph = self.graph.copy()
        test_graph.add_edge(prerequisite_id, topic_id)
        return not nx.is_directed_acyclic_graph(test_graph)

    def to_adjacency_dict(self) -> dict:
        """
        Export the graph as an adjacency list for JSON serialization.
        
        Returns:
            {
                "nodes": [{"id": ..., "name": ..., "slug": ..., "in_degree": ..., "out_degree": ...}],
                "edges": [{"from": prerequisite_id, "to": topic_id}],
            }
        """
        nodes = []
        for node_id in self.graph.nodes():
            topic = self._topics.get(node_id)
            nodes.append({
                "id": node_id,
                "name": topic.name if topic else node_id,
                "slug": topic.slug if topic else "",
                "in_degree": self.graph.in_degree(node_id),
                "out_degree": self.graph.out_degree(node_id),
            })

        edges = []
        for u, v in self.graph.edges():
            edges.append({"from": u, "to": v})

        return {"nodes": nodes, "edges": edges}

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()
