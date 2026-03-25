class AbstractPathNode:
    def __init__(self, state, event, next_path_node=None):
        self.state = state
        self.event = event
        self.next_path_node = next_path_node

    def to_dict(self) -> dict:
        raise NotImplementedError

class PathNode(AbstractPathNode):
    """
    PathNode is a concrete implementation of AbstractPathNode.
    It represents a node in the path graph, containing a state and an event.
    """

    def __init__(self, state, event, oracles=None, next_path_node=None):
        from transition_graph.nodes.state_node import StateNode
        from transition_graph.events.event import InternalEvent
        if not isinstance(state, StateNode) or isinstance(event, InternalEvent):
            raise ValueError("PathNode can only be created with an AbstractStateNode.")
        self.oracles = oracles or []
        super(PathNode, self).__init__(state, event, next_path_node)

    def to_dict(self) -> dict:
        if self.event is not None and self.event.state_node is None:
            self.event.state_node = self.state
        d = {
            "node_type": "normal",
            "state_id": self.state.id,
            "raw_state_dict": self.state.to_dict(),
            "event_id": self.event.event_id if self.event is not None else None,
            "raw_event_dict": self.event.to_dict() if self.event is not None else None
        }
        if getattr(self, "oracles", None):
            d["oracles"] = [o.to_dict() for o in self.oracles]
        else:
            d["oracles"] = []
        return d

class InternalPathNode(AbstractPathNode):
    """
    InternalPathNode is a concrete implementation of AbstractPathNode.
    It represents a node in the path graph that is not reachable from the UI.
    """

    def __init__(self, state, event, next_path_node=None):
        from transition_graph.nodes.state_node import InternalStateNode
        from transition_graph.events.event import InternalEvent
        if not isinstance(state, InternalStateNode) or (not isinstance(event, InternalEvent) and event is not None):
            raise ValueError("InternalPathNode can only be created with an InternalStateNode.")
        super(InternalPathNode, self).__init__(state, event, next_path_node)

    def to_dict(self) -> dict:
        if self.event is not None and self.event.state_node is None:
            self.event.state_node = self.state
        return {
            "node_type": "internal",
            "state_id": self.state.id,
            "raw_state_dict": self.state.to_dict(),
            "event_id": self.event.event_id if self.event is not None else None,
            "raw_event_dict": self.event.to_dict() if self.event is not None else None
        }