class PageNode:
    """
    A page node represents a page in the transition graph. It contains a list of state nodes that are present on the page, and a list of transitions that can be taken from the page. The transitions are represented as tuples of the event that triggers the transition, the source state node, and the target page node.
    Attributes:
        - name: the name of the page node
        - current_activity: the current activity of the page node.
            - It is represented as a JSON object containing:
                - component_hash: the hash of the component tree of the current activity
                - u0: the user ID of the current activity
                - package_name: the package name of the current activity
                - activity_name: the name of the current activity
        - id: the unique identifier of the page node
        - state_nodes: a list of state nodes that are present on the page
        - transitions: a list of transitions that can be taken from the page
            - each transition is a tuple of the form (event, source_state_node, target_page_node)
            - source_state_node is the state node that the transition starts from
            - target_page_node is the page node that the transition leads to
    """

    counter = 0

    def __init__(self, name, current_activity):
        self.name = name
        self.current_activity = current_activity
        self.id = PageNode.counter
        self.state_nodes = []
        self.semantic_label = ""
        PageNode.counter += 1

    def add_semantic_label(self, label):
        self.semantic_label = label

    def has_semantic_label(self):
        return self.semantic_label != ""

    def add_state_node(self, state_node):
        self.state_nodes.append(state_node)
        state_node.parent_page_node = self

    def get_all_adjacent_pages(self):
        """
        Get all the adjacent pages of the current page node.
        :return: a list of page nodes that are adjacent to the current page node. The list elements are tuples of the form (event, source_state_node, target_page_node)
        """
        from transition_graph import InternalStateNode

        adjacent_pages = set()
        for state_node in self.state_nodes:
            for transition in state_node.transitions.items():
                event, target_node = transition
                if isinstance(target_node, InternalStateNode):
                    for internal_node_transition in target_node.transitions.items():
                        internal_event, internal_target_node = internal_node_transition
                        if internal_target_node.parent_page_node is not self:
                            adjacent_pages.add(internal_target_node.parent_page_node)
                else:
                    if target_node.parent_page_node is not self:
                        adjacent_pages.add(target_node.parent_page_node)
        return adjacent_pages

    def get_outgoing_events(self):
        """
        Get all the outgoing events of the current page node.
        :return: a list of events that are outgoing from the current page node, in the form of (event, target_node_out_of_current_page_node)
        """
        from transition_graph import InternalStateNode

        outgoing_events = []
        for state_node in self.state_nodes:
            for transition in state_node.transitions.items():
                event, target_node = transition
                if isinstance(target_node, InternalStateNode):
                    for internal_node_transition in target_node.transitions.items():
                        internal_event, internal_target_node = internal_node_transition
                        if internal_target_node.parent_page_node is not self:
                            outgoing_events.append((event, internal_target_node))
                else:
                    if target_node.parent_page_node is not self:
                        outgoing_events.append((event, target_node))
        return outgoing_events

    def get_outgoing_events_to_page(self, page_node):
        """
        Get the outgoing events from the current page node to the given page node.
        :param page_node: the page node to get the outgoing events to
        :return: a list of events that are outgoing from the current page node to the given page node, in the form of (event, target_node_in_that_page_node)

        NOTE: You can use this method to get events that don't go out of the current page node. Just pass the current page node as the argument.
        """
        from transition_graph import InternalStateNode
        
        outgoing_events = []
        for state_node in self.state_nodes:
            for transition in state_node.transitions.items():
                event, target_node = transition
                if isinstance(target_node, InternalStateNode):
                    for internal_node_transition in target_node.transitions.items():
                        internal_event, internal_target_node = internal_node_transition
                        if internal_target_node.parent_page_node is page_node:
                            outgoing_events.append((event, internal_target_node))
                else:
                    if target_node.parent_page_node is page_node:
                        outgoing_events.append((event, target_node))
        return outgoing_events

    def to_dict(self):
        return {
            "name": self.name,
            "current_activity": self.current_activity,
            "id": self.id,
            "semantic_label": self.semantic_label,
            "state_nodes": [state_node.to_dict() for state_node in self.state_nodes]
        }