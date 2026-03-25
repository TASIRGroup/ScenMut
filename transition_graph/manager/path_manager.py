import yaml
import json
import os

from ..paths.path import ScriptPath
from ..manager.graph_manager import GraphManager

class PathManager:
    def __init__(self, yaml_file_path, graph_mgr: GraphManager):
        self.original_paths: list[ScriptPath] = []
        self.mutated_paths: list[ScriptPath] = []
        self.executable_paths: list[ScriptPath] = []
        self.graph_mgr = graph_mgr

        yaml_file = open(yaml_file_path, "r")
        config = yaml.safe_load(yaml_file)
        yaml_file.close()
        self.save_path = config["graphDir"]

    def get_paths(self) -> dict:
        return {"original": self.original_paths, "mutated": self.mutated_paths}

    def add_path(self, path: ScriptPath, path_type: str):
        if path_type == "original":
            self.original_paths.append(path)
        elif path_type == "mutated":
            self.mutated_paths.append(path)
        elif path_type == "executable":
            self.executable_paths.append(path)

    def extend_paths(self, paths: list[ScriptPath], path_type: str):
        if path_type == "original":
            self.original_paths.extend(paths)
        elif path_type == "mutated":
            self.mutated_paths.extend(paths)
        elif path_type == "executable":
            self.executable_paths.extend(paths)

    def save_paths_to_file(self):
        """
        NOTE: update graph after saving paths MAY cause unsync between paths and graph
        """
        try:
            paths_dict = {
                "original_paths": [],
                "mutated_paths": [],
                "executable_paths": []
            }
            
            for path in self.original_paths:
                path_dict = path.to_dict()
                paths_dict["original_paths"].append(path_dict)
            
            for path in self.mutated_paths:
                path_dict = path.to_dict()
                paths_dict["mutated_paths"].append(path_dict)
            
            for path in self.executable_paths:
                path_dict = path.to_dict()
                paths_dict["executable_paths"].append(path_dict)

            path_file = os.path.join(self.save_path, "paths.json")
            with open(path_file, "w") as f:
                json.dump(paths_dict, f, indent=4)
            
            return True
        except Exception as e:
            print(f"Save Paths Error: {e}")
            return False

    def load_paths_from_file(self):
        from ..paths.path_node import PathNode, InternalPathNode
        from ..events.event import AbstractEvent
        
        def _load_path_from_dict(path_dict, graph_mgr):
            """Load a single path from dictionary representation"""
            path_nodes_array = []
            
            for path_node_dict in path_dict["path_nodes"]:
                state = graph_mgr.get_state_by_id(path_node_dict["state_id"])
                if state is None:
                    
                    raise ValueError(f"State with id {path_node_dict['state_id']} not found in graph")
                
                event = None
                if path_node_dict["event_id"] is not None:
                    for ev, target_node in state.transitions.items():
                        if ev.event_id == path_node_dict["event_id"]:
                            event = ev
                            break
                    if event is None:
                        event = AbstractEvent.from_dict(path_node_dict["raw_event_dict"])
                    if event is None:
                        raise ValueError(f"Event with id {path_node_dict['event_id']} not found in graph")
                
                if path_node_dict["node_type"] == "normal":
                    oracles = []
                    for od in path_node_dict.get("oracles") or []:
                        from ..oracles.oracle import TextOracle, AttributeOracle, DisplayOracle
                        locator = od.get("locator") or {}
                        t = (od.get("type") or "text").strip().lower()
                        try:
                            if t == "text":
                                oracles.append(TextOracle(state, locator, od.get("text") or "", od.get("validation_type") or "exact"))
                            elif t == "attribute":
                                oracles.append(AttributeOracle(state, locator, od.get("attribute") or "", od.get("value") or ""))
                            elif t == "display":
                                oracles.append(DisplayOracle(state, locator, bool(od.get("display", False))))
                        except Exception:
                            pass
                    path_node = PathNode(state, event, oracles)
                elif path_node_dict["node_type"] == "internal":
                    path_node = InternalPathNode(state, event)
                else:
                    raise ValueError(f"Unknown path node type: {path_node_dict['node_type']}")
                
                path_nodes_array.append(path_node)
            
            script_path = ScriptPath(path_array=path_nodes_array)
            script_path.set_path_name(path_dict["path_name"] if "path_name" in path_dict else "")
            script_path.set_path_type(path_dict["path_type"])
            script_path.set_mutation_description(path_dict["mutation_description"])
            return script_path
        
        try:
            path_file = os.path.join(self.save_path, "paths.json")
            with open(path_file, "r") as f:
                paths_dict = json.load(f)
            
            # Clear existing paths
            self.original_paths = []
            self.mutated_paths = []
            self.executable_paths = []
            
            for path_dict in paths_dict["original_paths"]:
                script_path = _load_path_from_dict(path_dict, self.graph_mgr)
                self.original_paths.append(script_path)
            
            for path_dict in paths_dict["mutated_paths"]:
                script_path = _load_path_from_dict(path_dict, self.graph_mgr)
                self.mutated_paths.append(script_path)
            
            for path_dict in paths_dict["executable_paths"]:
                script_path = _load_path_from_dict(path_dict, self.graph_mgr)
                self.executable_paths.append(script_path)

            return True
        except Exception as e:
            print(f"Load Paths Error: {e}")
            return False
        
    @staticmethod
    def unique_states_count(paths: list[ScriptPath]) -> int:
        unique_states = {}
        for path in paths:
            for path_node in path.to_array():
                unique_states[path_node.state.id] = path_node.state
        return len(unique_states)

    @staticmethod
    def diversity(paths: list[ScriptPath]) -> float:
        if len(paths) == 0 or len(paths) == 1:
            return 0.0
        
        def _diversity_between_paths(path1: ScriptPath, path2: ScriptPath) -> float:
            len_diff = abs(len(path1.to_array()) - len(path2.to_array())) / max(len(path1.to_array()), len(path2.to_array()))
            state_set_1 = set(map(lambda path_node: path_node.state.id, path1.to_array()))
            state_set_2 = set(map(lambda path_node: path_node.state.id, path2.to_array()))
            state_intersection = state_set_1 & state_set_2
            state_union = state_set_1 | state_set_2
            if len(state_union) == 0:
                state_diversity = 0.0
            else:
                state_diversity = 1.0 - len(state_intersection) / len(state_union)
            return 0.5 * len_diff + 0.5 * state_diversity

        diversity = 0.0

        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                diversity += _diversity_between_paths(paths[i], paths[j])

        diversity /= (len(paths) * (len(paths) - 1)) / 2
        return diversity

    @staticmethod
    def unique(paths: list[ScriptPath]) -> list[ScriptPath]:
        # use path.equals(other_path) to compare
        unique_paths = []
        for path in paths:
            is_unique = True
            for unique_path in unique_paths:
                if path.equals(unique_path):
                    is_unique = False
                    break
            if is_unique:
                unique_paths.append(path)
        return unique_paths
