from typing import List, Dict, Set, Optional
from collections import defaultdict, deque
from src.knowledge.core.models import Relationship

class RelationshipGraph:
    """
    Graph representation of database relationships for path discovery.
    """
    def __init__(self, relationships: List[Relationship]):
        self.relationships = relationships
        self.adj_list = defaultdict(list)
        self._build_graph()

    def _build_graph(self):
        for r in self.relationships:
            # Undirected graph for path finding (can traverse both ways)
            self.adj_list[r.source_table].append((r.target_table, r))
            self.adj_list[r.target_table].append((r.source_table, r))

    def get_neighbors(self, table: str) -> List[str]:
        return [target for target, _ in self.adj_list.get(table, [])]

    def find_join_paths(self, start_table: str, end_table: str, max_depth: int = 3) -> List[List[Relationship]]:
        """
        Find all paths between two tables using BFS.
        Returns a list of paths, where each path is a list of Relationships.
        """
        if start_table == end_table:
            return []
            
        paths = []
        queue = deque([(start_table, [])])
        visited = {start_table: 0} # keep track of depth

        while queue:
            current_table, current_path = queue.popleft()
            
            if len(current_path) >= max_depth:
                continue

            for neighbor, rel in self.adj_list.get(current_table, []):
                # Avoid cycles
                if any(r == rel for r in current_path):
                    continue
                    
                new_path = current_path + [rel]
                
                if neighbor == end_table:
                    paths.append(new_path)
                elif neighbor not in visited or visited[neighbor] > len(new_path):
                    visited[neighbor] = len(new_path)
                    queue.append((neighbor, new_path))
                    
        return paths
