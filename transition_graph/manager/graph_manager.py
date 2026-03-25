import os
import shutil

import yaml
import json

from transition_graph.nodes.page_node import PageNode
from transition_graph.utils.belonging_strategy import ComponentTreeSimilarityBelongingStrategy
from transition_graph.utils.mock_strategy import MockStrategy
from transition_graph.utils.samestate_strategy import ComponentTreeHashSameStateStrategy
from transition_graph.utils.semantic_labels import generate_semantic_understanding_result_for_state_node


class GraphManager:
    from transition_graph.nodes.state_node import StateNode
    from transition_graph.nodes.page_node import PageNode
    from transition_graph.events.event import AbstractEvent
    from transition_graph.nodes.state_node import AbstractStateNode

    currentGraph = None
    same_state_strategy = None
    belonging_strategy = None

    def __init__(self, yaml_file_path):
        from transition_graph.nodes.transition_graph_node import TransitionGraphNode

        self.currentGraph = TransitionGraphNode()
        yaml_file = open(yaml_file_path, "r")
        config = yaml.safe_load(yaml_file)
        yaml_file.close()

        # Load the strategies
        if config["sameStateStrategy"]["type"] == "hash":
            self.same_state_strategy = ComponentTreeHashSameStateStrategy()

        if config["belongingStrategy"]["type"] == "tree_similarity":
            threshold = config["belongingStrategy"]["threshold"]
            self.belonging_strategy = ComponentTreeSimilarityBelongingStrategy(float(threshold))

        # Load save path
        self.save_path = config["graphDir"]
        self.app_name = (config.get("appium") or {}).get("appPackage")

        # Semantic model and cache (stored per graph instance; thread-safe).
        self._semantic_model = None
        self._semantic_target_embedding = None
        self._semantic_label_to_weight = {}

        print("GraphManager initialized")

    def set_start_state(self, start_state: StateNode):
        self.currentGraph.set_start_state(start_state)

    def get_start_state(self):
        return self.currentGraph.start_state

    def get_start_page(self):
        return self.currentGraph.start_page

    def add_page_node(self, page_node: PageNode):
        self.currentGraph.add_page_node(page_node)

    @staticmethod
    def add_state_to_page(state_node: AbstractStateNode, page_node: PageNode):
        page_node.add_state_node(state_node)

    def belongs_to_which_page(self, state_node: StateNode, current_activity):
        target_page_node = self.belonging_strategy.belongs_to_which_page(state_node, self.currentGraph.page_nodes)
        if target_page_node is None:
            # If the state node does not belong to any page, create a new page node
            target_page_node = PageNode("page", current_activity)
            self.add_page_node(target_page_node)

        return target_page_node

    def add_transition(self, event: AbstractEvent, source_state_node: StateNode, target_state_node: StateNode):
        from transition_graph.events.event import InternalEvent

        if isinstance(event, InternalEvent):
            print("Internal event Error: it should not be added manually.")
            raise ValueError
        new_internal_state_node = source_state_node.add_transition(event, target_state_node)
        if new_internal_state_node is not None:
            self.currentGraph.add_internal_state_node(new_internal_state_node)

    def add_new_state(self, new_state_node: StateNode, source_state_node: StateNode, event: AbstractEvent, current_activity):
        """
        Add a new state to the graph. An important method to maintain the graph.
        If the new state is not in the graph, it will be added to the graph.

        :param new_state_node: The new state node to be added.
        :param source_state_node: The source state node.
        :param event: The event that triggers the transition.
        :param current_activity: The current activity of the new state node.
        :return: The new state node, or the existing one.
        """
        # If the new state is the first state in the graph, set it as the start state
        if self.currentGraph.start_state is None:
            target_page_node = self.belongs_to_which_page(new_state_node, current_activity)
            self.add_state_to_page(new_state_node, target_page_node)
            self.set_start_state(new_state_node)
            return new_state_node

        # The new state node is the end state
        if new_state_node == self.currentGraph.get_end_state():
            self.add_transition(event, source_state_node, new_state_node)
            return new_state_node

        # Check if the new state node is already in the graph
        state_node = self.find_state(new_state_node)
        if state_node is not None:
            # If the new state node is already in the graph, add the transition
            self.add_transition(event, source_state_node, state_node)
            # If the new state node has script_loc, add it to the old one
            if len(new_state_node.script_loc) > 0:
                state_node.add_script_loc(new_state_node.script_loc[0]) # new state node has only one script_loc
            # Compare events and add new ones if the events are different
            for new_event in new_state_node.available_events:
                is_matched = False
                for old_event in state_node.available_events:
                    if new_event.equals(old_event):
                        is_matched = True
                        break
                if not is_matched:
                    new_event.state_node = state_node
                    state_node.available_events.append(new_event)
                    if new_event in new_state_node.visited_events:
                        state_node.visited_events.append(new_event)
            return state_node

        # If the new state node is not in the graph, add it to the graph
        target_page_node = self.belongs_to_which_page(new_state_node, current_activity)
        self.add_state_to_page(new_state_node, target_page_node)
        self.add_transition(event, source_state_node, new_state_node)

        return new_state_node

    def find_state(self, new_state_node: StateNode):
        for page_node in self.currentGraph.page_nodes:
            for state_node in page_node.state_nodes:
                if self.same_state_strategy.is_same_state(new_state_node, state_node):
                    return state_node
        return None

    def get_state_by_id(self, state_id):
        for page_node in self.currentGraph.page_nodes:
            for state_node in page_node.state_nodes:
                if state_node.id == state_id:
                    return state_node
        for internal_state_node in self.currentGraph.internal_state_nodes:
            if internal_state_node.id == state_id:
                return internal_state_node

    @staticmethod
    def add_event(event: AbstractEvent, state_node: StateNode):
        from transition_graph.events.event import InternalEvent

        if isinstance(event, InternalEvent):
            print("Internal event Error: it should not be added manually.")
            return
        state_node.add_event(event)

    @staticmethod
    def visit_event(event: AbstractEvent, state_node: StateNode):
        state_node.add_visited_event(event)

    def get_end_state(self):
        return self.currentGraph.get_end_state()

    def get_script_name_list(self) -> list:
        script_name_set = set()
        for page_node in self.currentGraph.page_nodes:
            for state_node in page_node.state_nodes:
                for script_loc_item in state_node.script_loc:
                    script_name_set.add(script_loc_item[0])
        return list(script_name_set)

    def get_states_by_script_name(self, script_name):
        states_with_positions = []
        for page_node in self.currentGraph.page_nodes:
            for state_node in page_node.state_nodes:
                for script_loc_item in state_node.script_loc:
                    if script_name == script_loc_item[0]:
                        states_with_positions.append((state_node, script_loc_item[1]))
        # Sort states by script_loc_item[1] where script_loc_item[0] == script_name
        states_with_positions.sort(key=lambda x: x[1])
        states = []
        for state, position in states_with_positions:
            states.append(state)

        return states

    def get_state_by_script_loc(self, script_loc):
        for page_node in self.currentGraph.page_nodes:
            for state_node in page_node.state_nodes:
                if script_loc in state_node.script_loc:
                    return state_node

    def save_graph_to_file(self):
        """
        Save the current graph to a file.
        :return: Boolean, whether the graph is saved successfully.

        Note: If you call this method, old saved graph will be deleted.
        """
        # Delete the old files
        if os.path.exists(self.save_path):
            shutil.rmtree(self.save_path)
        os.makedirs(self.save_path, exist_ok=True)

        # Use json to save the graph
        graph_dict = self.currentGraph.to_dict()
        try:
            path = os.path.join(self.save_path, "graph.json")
            with open(path, "w") as f:
                json.dump(graph_dict, f, indent=4)

            state_path = os.path.join(self.save_path, "states.json")
            state_dict = {
                "states": [],
                "internal_states": []
            }
            for page in self.currentGraph.page_nodes:
                for state in page.state_nodes:
                    state_dict["states"].append(state.to_dict())
            for internal_state in self.currentGraph.internal_state_nodes:
                state_dict["internal_states"].append(internal_state.to_dict())
            with open(state_path, "w") as f:
                json.dump(state_dict, f, indent=4)

            event_path = os.path.join(self.save_path, "events.json")
            event_dict = {
                "all_events": [],
                "mock_strategy_hash_map": MockStrategy.hash_map_to_dict()
            }
            for page in self.currentGraph.page_nodes:
                for state in page.state_nodes:
                    for event, target_node in state.transitions.items():
                        event_dict["all_events"].append(event.to_dict())
                    for event in state.available_events:
                        event_dict["all_events"].append(event.to_dict())

            for internal_state in self.currentGraph.internal_state_nodes:
                for event, target_node in internal_state.transitions.items():
                    event_dict["all_events"].append(event.to_dict())

            # Remove duplicate events by event.id, not the whole event object
            event_dict["all_events"] = list({event["event_id"]: event for event in event_dict["all_events"]}.values())
            # Sort the events by event_id
            event_dict["all_events"] = sorted(event_dict["all_events"], key=lambda x: x["event_id"])

            with open(event_path, "w") as f:
                json.dump(event_dict, f, indent=4)

            return True
        except Exception as e:
            print(f"Save Graph Error: {e}")
            return False

    def load_graph_from_file(self):
        """
        Load the graph from a file.
        :return: Boolean, whether the graph is loaded successfully.
        """
        from transition_graph.nodes.state_node import InternalStateNode, AbstractStateNode

        def _load_events(events_dict):
            from transition_graph.events.event import ClickEvent, TextInputEvent, BackEvent, InternalEvent, TextClearEvent, AbstractEvent
            # Load the events
            events = []
            max_id = 0
            MockStrategy.hash_map_from_dict(events_dict["mock_strategy_hash_map"])

            for event_dict in events_dict["all_events"]:
                event = AbstractEvent.from_dict(event_dict)
                if event is None:
                    raise ValueError(f"Failed to load event with id {event_dict['event_id']}")
                max_id = max(max_id, event.event_id + 1)
                events.append(event)

            AbstractEvent.counter = max_id
            return events

        def _load_states(states_dict):
            from transition_graph.nodes.state_node import StateNode, InternalStateNode
            from device_infrastructure.actions import Screenshot
            # Load the states
            states = []
            max_id = 0
            max_screenshot_id = 0
            for state_dict in states_dict["states"]:
                state = StateNode(state_dict["name"], state_dict["component_tree"], state_dict["screenshot_path"])
                state.id = state_dict["id"]
                state.available_events = []
                state.visited_events = []
                state.transitions = {}
                state.script_loc = state_dict["script_loc"]
                state.oracles_from_dict(state_dict["oracles"])
                from transition_graph.data.data_entity import DataEntity
                state.data_entities = [DataEntity.from_dict(data_entity_dict) for data_entity_dict in state_dict["data_entities"]] if "data_entities" in state_dict else []

                max_id = max(max_id, state.id + 1)
                # /Users/xingjunyang/Documents/GitHub/PathMuTeG/screenshots/3.png -> 3
                if state.screenshot_path is not None:
                    # in order to support multi-platform, we need to consider two types of path separator
                    max_screenshot_id = max(max_screenshot_id, int(state.screenshot_path.split("/")[-1].split("\\")[-1].split(".")[0]) + 1)
                states.append(state)

            for internal_state_dict in states_dict["internal_states"]:
                internal_state = InternalStateNode(internal_state_dict["name"])
                internal_state.id = internal_state_dict["id"]
                internal_state.transitions = {}

                max_id = max(max_id, internal_state.id + 1)
                states.append(internal_state)

            AbstractStateNode.counter = max_id
            Screenshot.count = max_screenshot_id
            return states

        def _bind_states_and_events(states, events, events_dict, states_dict):
            # bind state to event
            for event in events:
                event_id = event.event_id
                state_id = next(filter(lambda x: x["event_id"] == event_id, events_dict["all_events"]))["state_node_id"]
                state = next(filter(lambda x: x.id == state_id, states))
                event.state_node = state

            # bind event to state
            for state_dict in states_dict["states"]:
                state_id = state_dict["id"]
                state = next(filter(lambda x: x.id == state_id, states))
                for transition_dict in state_dict["transitions"]:
                    event_id = transition_dict["event"]["event_id"]
                    event = next(filter(lambda x: x.event_id == event_id, events))
                    target_state_id = transition_dict["target_state_node_id"]
                    target_state = next(filter(lambda x: x.id == target_state_id, states))
                    state.add_transition(event, target_state)

                for available_event_dict in state_dict["available_events"]:
                    event_id = available_event_dict["event_id"]
                    event = next(filter(lambda x: x.event_id == event_id, events))
                    state.available_events.append(event)

                for visited_event_dict in state_dict["visited_events"]:
                    event_id = visited_event_dict["event_id"]
                    event = next(filter(lambda x: x.event_id == event_id, events))
                    state.visited_events.append(event)

            for internal_state_dict in states_dict["internal_states"]:
                state_id = internal_state_dict["id"]
                state = next(filter(lambda x: x.id == state_id, states))
                for transition_dict in internal_state_dict["transitions"]:
                    event_id = transition_dict["event"]["event_id"]
                    event = next(filter(lambda x: x.event_id == event_id, events))
                    target_state_id = transition_dict["target_state_node_id"]
                    target_state = next(filter(lambda x: x.id == target_state_id, states))
                    state.add_transition(event, target_state)

        def _load_page(pages_dict, states):
            pages = []
            max_id = 0
            for page_dict in pages_dict:
                page = PageNode(page_dict["name"], page_dict["current_activity"])
                page.id = page_dict["id"]
                page.state_nodes = []
                page.semantic_label = page_dict.get("semantic_label", "")
                for state_node_dict in page_dict["state_nodes"]:
                    state_node_id = state_node_dict["id"]
                    state_node = next(filter(lambda x: x.id == state_node_id, states))
                    page.state_nodes.append(state_node)
                    state_node.parent_page_node = page
                max_id = max(max_id, page.id + 1)
                pages.append(page)

            PageNode.counter = max_id
            return pages


        # Use json to load the graph
        try:
            path = os.path.join(self.save_path, "graph.json")
            with open(path, "r") as f:
                graph_dict = json.load(f)

            state_path = os.path.join(self.save_path, "states.json")
            with open(state_path, "r") as f:
                states_dict = json.load(f)

            event_path = os.path.join(self.save_path, "events.json")
            with open(event_path, "r") as f:
                events_dict = json.load(f)

            # Load the states
            states = _load_states(states_dict)
            # Load the events
            events = _load_events(events_dict)
            # Bind states and events
            _bind_states_and_events(states, events, events_dict, states_dict)
            # Load the pages
            pages = _load_page(graph_dict["page_nodes"], states)

            # Build the graph
            self.currentGraph.start_page = next(filter(lambda x: x.id == graph_dict["start_page"]["id"], pages))
            self.currentGraph.start_state = next(filter(lambda x: x.id == graph_dict["start_state"]["id"], states))
            self.currentGraph.end_page = next(filter(lambda x: x.id == graph_dict["end_page"]["id"], pages))
            self.currentGraph.end_state = next(filter(lambda x: x.id == graph_dict["end_state"]["id"], states))
            self.currentGraph.page_nodes = pages
            self.currentGraph.internal_state_nodes = list(filter(lambda x: isinstance(x, InternalStateNode), states))
            self.currentGraph.finished_semantic_labeling = graph_dict["finished_semantic_labeling"] if "finished_semantic_labeling" in graph_dict else False

            return True

        except Exception as e:
            print(f"Load Graph Error: {e}")
            return False

    def get_all_available_semantic_labels(self):
        all_available_semantic_labels = []
        for page_node in self.currentGraph.page_nodes:
            if page_node.has_semantic_label():
                all_available_semantic_labels.append(page_node.semantic_label)
        return all_available_semantic_labels
    
    def clear_all_semantic_labels(self):
        for page_node in self.currentGraph.page_nodes:
            if page_node.has_semantic_label():
                page_node.semantic_label = ""
            for state_node in page_node.state_nodes:
                state_node.data_entities = []
                for event in state_node.available_events:
                    event.semantic_label = ""
                    event.has_data_side_effect = False
        self.currentGraph.finished_semantic_labeling = False
    
    def merge_page_node(self, src_page_node, dst_page_node):
        # Merge the src_page_node into the dst_page_node, and update the graph accordingly
        for state_node in src_page_node.state_nodes:
            dst_page_node.add_state_node(state_node)
            state_node.parent_page_node = dst_page_node

        # Remove the src_page_node from the graph
        self.currentGraph.page_nodes.remove(src_page_node)

    def get_all_similar_state_nodes(self, state_node: StateNode, threshold: float = 0.95):
        similar_state_nodes = []
        for page_node in self.currentGraph.page_nodes:
            if page_node == self.currentGraph.end_page:
                continue
            for target_state_node in page_node.state_nodes:
                if target_state_node == state_node:
                    continue
                if ComponentTreeSimilarityBelongingStrategy.is_similar_state_node(state_node, target_state_node, threshold):
                    similar_state_nodes.append(target_state_node)
        return similar_state_nodes

    def refine_pagination_by_semantic_labels_quick(self):
        import tqdm

        for page_node in tqdm.tqdm(self.currentGraph.page_nodes, desc="Refining pagination by semantic labels"):
            if self.currentGraph.end_page == page_node:
                continue
            if not page_node.has_semantic_label():
                # random choose one state node in the page node to generate semantic label for all state nodes in the page node
                state_node = page_node.state_nodes[0]
                available_semantic_labels = self.get_all_available_semantic_labels()
                semantic_understanding_result = generate_semantic_understanding_result_for_state_node(
                    state_node, available_semantic_labels, app_name=self.app_name
                )
                intent = semantic_understanding_result.model_dump()["intent"]
                page_node.add_semantic_label(intent)
                print(f"Generated intent '{intent}' for page '{page_node.name}'")
        
        # find pages with the same semantic label and merge them
        semantic_label_to_page_nodes = {}
        for page_node in self.currentGraph.page_nodes:
            if page_node.semantic_label not in semantic_label_to_page_nodes:
                semantic_label_to_page_nodes[page_node.semantic_label] = []
            semantic_label_to_page_nodes[page_node.semantic_label].append(page_node)
        for semantic_label, page_nodes in semantic_label_to_page_nodes.items():
            if len(page_nodes) > 1:
                dst_page_node = page_nodes[0]
                for src_page_node in page_nodes[1:]:
                    self.merge_page_node(src_page_node, dst_page_node)
                    print(f"Merged page '{src_page_node.name}' into page '{dst_page_node.name}' with semantic label '{semantic_label}'")
        pass

    def refine_pagination_by_semantic_labels_full(self):
        import tqdm
        from transition_graph.data.data_entity import DataEntity

        if self.currentGraph.finished_semantic_labeling:
            return # reuse the existing semantic labels

        self.clear_all_semantic_labels()

        state_nodes = []
        for page_node in self.currentGraph.page_nodes:
            if page_node == self.currentGraph.end_page:
                continue
            state_nodes.extend(page_node.state_nodes)

        semantic_label_to_state_nodes = {} # key: semantic label, value: list of state nodes with the semantic label
        for state_node in tqdm.tqdm(state_nodes, desc="Grouping state nodes by semantic labels"):
            # get available semantic labels from semantic_label_to_state_nodes dict, which is generated by the state nodes that have been processed
            available_semantic_labels = list(semantic_label_to_state_nodes.keys())
            
            # collect existing data field keys and event semantic labels from similar processed state nodes
            already_processed = set()
            for nodes in semantic_label_to_state_nodes.values():
                already_processed.update(nodes)
            similar_state_nodes = self.get_all_similar_state_nodes(state_node)
            existing_data_field_keys = []
            existing_event_semantic_labels = []
            for s in similar_state_nodes:
                if s != state_node and s in already_processed:
                    for de in s.data_entities:
                        if de.key:
                            existing_data_field_keys.append(de.key)
                    for ev in s.available_events:
                        if getattr(ev, "semantic_label", None):
                            existing_event_semantic_labels.append(ev.semantic_label)
            semantic_understanding_result = generate_semantic_understanding_result_for_state_node(
                state_node,
                available_semantic_labels,
                existing_data_field_keys=existing_data_field_keys if existing_data_field_keys else None,
                existing_event_semantic_labels=existing_event_semantic_labels if existing_event_semantic_labels else None,
                app_name=self.app_name,
            )
            intent = semantic_understanding_result.model_dump()["intent"]
            if intent not in semantic_label_to_state_nodes:
                semantic_label_to_state_nodes[intent] = []
            semantic_label_to_state_nodes[intent].append(state_node)

            # parse data entities and data changing events
            data_entities = semantic_understanding_result.model_dump()["data_fields"]
            for data_entity in data_entities:
                state_node.data_entities.append(DataEntity.from_dict(data_entity))
            data_changing_events = semantic_understanding_result.model_dump()["data_changing_events"]
            for event_dict in data_changing_events:
                event_id = event_dict["event_id"]
                event = next(filter(lambda x: x.event_id == event_id, state_node.available_events))
                event.semantic_label = event_dict["semantic_label"]
                event.has_data_side_effect = True

        # generate new page nodes based on the semantic labels, and assign state nodes to the new page nodes
        new_page_nodes = []
        start_page_node = None
        for semantic_label, state_nodes in semantic_label_to_state_nodes.items():
            new_page_node = PageNode(f"page_{semantic_label}", state_nodes[0].parent_page_node.current_activity)
            new_page_node.add_semantic_label(semantic_label)
            new_page_nodes.append(new_page_node)
            for state_node in state_nodes:
                new_page_node.add_state_node(state_node)
                state_node.parent_page_node = new_page_node
                if state_node == self.currentGraph.start_state:
                    start_page_node = new_page_node

        old_end_page = self.currentGraph.end_page

        self.currentGraph.page_nodes = new_page_nodes
        self.currentGraph.page_nodes.append(old_end_page)
        self.currentGraph.start_page = start_page_node
        self.currentGraph.finished_semantic_labeling = True
        self.save_graph_to_file()

    def calculate_exploration_coverage(self):
        """
        Calculate the exploration coverage of the graph.
        :return: The coverage percentage.
        """
        total_events = 0
        visited_events = 0

        for page in self.currentGraph.page_nodes:
            for state in page.state_nodes:
                total_events += len(state.available_events)
                visited_events += len(state.visited_events)

        if total_events == 0:
            return 0.0

        return (visited_events / total_events) * 100

    def calculate_states_count(self):
        states = []
        for page in self.currentGraph.page_nodes:
            for state in page.state_nodes:
                states.append(state)
        for internal_state in self.currentGraph.internal_state_nodes:
            states.append(internal_state)

        return len(states)

    def calculate_events_count(self):
        events = []
        for page in self.currentGraph.page_nodes:
            for state in page.state_nodes:
                for event, target_node in state.transitions.items():
                    events.append(event.to_dict())
                for event in state.available_events:
                    events.append(event.to_dict())
        for internal_state in self.currentGraph.internal_state_nodes:
            for event, target_node in internal_state.transitions.items():
                events.append(event.to_dict())
        events = list({event["event_id"]: event for event in events}.values())

        return len(events)

    def calculate_transitions_count(self):
        transition_count = 0
        for page in self.currentGraph.page_nodes:
            for state_node in page.state_nodes:
                transition_count += len(state_node.transitions)

        return transition_count