class ScriptPath:
    def __init__(self, start_path_node = None, path_array = None):
        self.path_type = None
        self.path_name = None
        self.mutation_description = None
        if path_array is not None:
            self.from_array(path_array)
            return

        if start_path_node is None:
            self.start_path_node = None
            self.end_path_node = None
        else:
            self.start_path_node = start_path_node
            self.end_path_node = start_path_node

    def set_path_type(self, path_type):
        self.path_type = path_type

    def add_path_node(self, path_node):
        if self.start_path_node is None:
            self.start_path_node = path_node
            self.end_path_node = path_node
        else:
            self.end_path_node.next_path_node = path_node
            self.end_path_node = path_node

    def set_path_name(self, path_name):
        self.path_name = path_name

    def set_mutation_description(self, mutation_description):
        self.mutation_description = mutation_description

    def to_array(self):
        from .path_node import InternalPathNode, PathNode

        path_array = []
        current_node = self.start_path_node
        while current_node is not None:
            if isinstance(current_node, InternalPathNode):
                new_path_node = InternalPathNode(current_node.state, current_node.event)
            else:
                new_path_node = PathNode(current_node.state, current_node.event, current_node.oracles if len(current_node.oracles) > 0 else None)
            path_array.append(new_path_node)
            current_node = current_node.next_path_node
        return path_array

    def from_array(self, path_array):
        if len(path_array) == 0:
            return
        from .path_node import PathNode, InternalPathNode

        if isinstance(path_array[0], PathNode):
            self.start_path_node = PathNode(path_array[0].state, path_array[0].event, path_array[0].oracles if len(path_array[0].oracles) > 0 else None)
        else:
            self.start_path_node = InternalPathNode(path_array[0].state, path_array[0].event)
        self.end_path_node = self.start_path_node

        for i in range(1, len(path_array)):
            if isinstance(path_array[i], PathNode):
                new_path_node = PathNode(path_array[i].state, path_array[i].event, path_array[i].oracles if len(path_array[i].oracles) > 0 else None)
            else:
                new_path_node = InternalPathNode(path_array[i].state, path_array[i].event)
            self.end_path_node.next_path_node = new_path_node
            self.end_path_node = new_path_node

    def equals(self, other) -> bool:
        if not isinstance(other, ScriptPath):
            return False
        self_array = self.to_array()
        other_array = other.to_array()
        if len(self_array) != len(other_array):
            return False
        for i in range(len(self_array)):
            if not self_array[i].state.id == other_array[i].state.id:
                return False
            if i == len(self_array) - 1:
                continue
            if self_array[i].event is None and other_array[i].event is None:
                continue
            if self_array[i].event is None or other_array[i].event is None:
                return False
            if not self_array[i].event.event_id == other_array[i].event.event_id:
                return False
        return True

    def to_dict(self) -> dict:
        path_array = self.to_array()
        path_nodes_dict = []
        for path_node in path_array:
            path_nodes_dict.append(path_node.to_dict())
        
        return {
            "path_type": self.path_type,
            "path_name": self.path_name,
            "path_nodes_count": len(path_nodes_dict),
            "path_nodes": path_nodes_dict,
            "mutation_description": self.mutation_description
        }