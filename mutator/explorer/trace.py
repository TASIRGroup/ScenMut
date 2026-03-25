import yaml
from time import sleep
from pathlib import Path

from device_infrastructure import DeviceManager
from transition_graph import GraphManager, StateManager, AbstractOracle, TextOracle, AttributeOracle, DisplayOracle

class TraceException(Exception):
    """Base class for trace exceptions."""
    def __init__(self, message):
        super(Exception, self).__init__(message)
        self.message = message

class Tracer:
    from transition_graph.events.event import AbstractEvent

    def __init__(self, yaml_file_path, reset=None):
        self.yaml_file_path = yaml_file_path

        yaml_file = open(yaml_file_path, "r")
        config = yaml.safe_load(yaml_file)
        yaml_file.close()

        self.reset = config["reset"] if "reset" in config else False
        self.reset = reset if reset is not None else self.reset
        self.device_mgr_reset = self.reset
        self.delay = config["delay"] if "delay" in config else 0.5
        self.device_mgr = None
        self.script_dir = Path(config["scriptDir"])
        self.graph_mgr = GraphManager(self.yaml_file_path)

        print("Tracer initialized with yaml file path:", self.yaml_file_path)

    def execute_and_trace(self, steps, oracles, script_name):
        if not self.reset:
            print("Reset is not True, skipping execution.")
            return

        transformed_script_name = script_name.replace(".py", "")
        self.device_mgr = DeviceManager(self.yaml_file_path, reset=self.device_mgr_reset, seperate_screenshot_folder=f"trace_{transformed_script_name}", seperate_coverage_folder=f"trace_{transformed_script_name}")
        self.state_mgr = StateManager(self.device_mgr)
        self.device_mgr_reset = False # reset device mgr only once

        # startup delay to avoid capturing the startup screen
        sleep(4)

        if self.graph_mgr.get_start_state() is None:
            print("Tracer: No start state found. Creating a new start state.")
            self.current_state = self.state_mgr.capture_new_state([script_name, 0], step=steps[0])
            self.graph_mgr.add_new_state(self.current_state, None, None, self.state_mgr.capture_current_activity())
            self.graph_mgr.save_graph_to_file()
        else:
            print("Tracer: Found a start state in the graph. Resuming the exploration.")
            self.current_state = self.graph_mgr.get_start_state()
            self.current_state.add_script_loc([script_name, 0])

        for i, step in enumerate(steps):
            print(f"Executing step {i + 1}/{len(steps)} in '{script_name}': {step}")
            events = self.current_state.available_events
            current_oracles = []
            for oracle in oracles:
                if oracle[0] == i:
                    current_oracles.append(oracle[1])

            # first find in parsed events
            matched_event = self.match_step_and_event(step, self.current_state.component_tree, events)
            
            # # then find by bounds (well, this is not a good idea)
            # if matched_event is None:
            #     if step["locator"]["method"] == 'AppiumBy.XPATH':
            #         bounds = self.device_mgr.get_bounds_by_xpath(step["locator"]["value"])
            #         if bounds is not None:
            #             matched_event = self.match_bounds_and_event(step, bounds, self.current_state.component_tree, events)
            #             print("fall back to bounds matching")

            # if still None, we manually add this event and try to perform it
            if matched_event is None:
                matched_event = self.generate_event_by_step(step, self.current_state)
                self.graph_mgr.add_event(matched_event, self.current_state)
                print("Tracer: Manually added event for step.", matched_event)
            
            matched_event.perform(self.device_mgr)
            self.graph_mgr.visit_event(matched_event, self.current_state)

            # Check app state
            state = self.device_mgr.get_state()

            if state == "background":
                next_state = self.graph_mgr.get_end_state()
                self.device_mgr.quit() # clean up before raising exception
                raise TraceException("Error: App is in background. Marking the state as end state. Test may be incomplete.")
            elif state == "halted":
                next_state = self.graph_mgr.get_end_state()
                self.device_mgr.quit() # clean up before raising exception
                raise TraceException("Error: App is halted. Marking the state as end state. Test may be incomplete.")
            else: # state == "running"
                print("Tracer: App is in foreground. Capturing new state.")
                next_state = self.state_mgr.capture_new_state([script_name, i + 1], step=(steps[i + 1] if i + 1 < len(steps) else None))
                for oracle in current_oracles:
                    Tracer.add_oracle_to_state_node(oracle, next_state, [script_name, i + 1])

            # Add the new state to the graph
            next_state = self.graph_mgr.add_new_state(next_state, self.current_state, matched_event, self.state_mgr.capture_current_activity())
            self.graph_mgr.save_graph_to_file()

            self.current_state = next_state

            sleep(2)

        print("Tracer: Test execution completed.")
        self.device_mgr.quit()

    @staticmethod
    def match_step_and_event(step, component_tree, events: list[AbstractEvent]) -> AbstractEvent | None:
        """
        Match the step with the events in the transition graph.
        :param step: The step to be matched.
        :param events: The list of events in the transition graph.
        :return: The matched event. If no event is found, return None.
        """
        from transition_graph.events.event import ClickEvent, TextInputEvent, TextClearEvent, BackEvent

        matched_events = [] # collect all matched events

        for event in events:
            if step["action"] == "click" and isinstance(event, ClickEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath(component_tree, event.xpath, step["locator"]["value"]):
                    matched_events.append(event)
            elif step["action"] == "send_keys" and isinstance(event, TextInputEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath(component_tree, event.xpath, step["locator"]["value"]) and event.text == step["value"]:
                    matched_events.append(event)
            elif step["action"] == "send_keys_clear" and isinstance(event, TextClearEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath(component_tree, event.xpath, step["locator"]["value"]):
                    matched_events.append(event)
            elif step["action"] == "back" and isinstance(event, BackEvent):
                return event

        if len(matched_events) == 1:
            return matched_events[0]

        def _bounds_distance(bounds_1, bounds_2):
            """
            Calculate the distance between two bounding boxes based on IoU of the two bounding boxes.
            param bounds_1: The first bounding box. In (x1, y1, x2, y2) format tuple
            param bounds_2: The second bounding box. In (x1, y1, x2, y2) format tuple
            """
            if bounds_1 is None or bounds_2 is None:
                return 1.0

            x1_inter = max(bounds_1[0], bounds_2[0])
            y1_inter = max(bounds_1[1], bounds_2[1])
            x2_inter = min(bounds_1[2], bounds_2[2])
            y2_inter = min(bounds_1[3], bounds_2[3])
            
            if x2_inter <= x1_inter or y2_inter <= y1_inter:
                return 1.0
            
            inter_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)
            
            area1 = (bounds_1[2] - bounds_1[0]) * (bounds_1[3] - bounds_1[1])
            area2 = (bounds_2[2] - bounds_2[0]) * (bounds_2[3] - bounds_2[1])
            
            union_area = area1 + area2 - inter_area
            
            iou = inter_area / union_area
            
            return 1.0 - iou

        def _get_bounds_by_xpath(xpath):
            xpath = xpath.replace("'", "\"")
            xpath = xpath.replace('"', "\"")
            xpath = xpath.strip()

            from lxml import etree

            try:
                xml_bytes = component_tree.encode('utf-8')  # Convert to bytes
                root = etree.fromstring(xml_bytes)

                elements = root.xpath(xpath)
                if len(elements) == 1:
                    x1, y1, x2, y2 = map(int, elements[0].get('bounds').replace('][', ',').replace('[', '').replace(']', '').split(','))
                    return (x1, y1, x2, y2)
                else:
                    return None
            except Exception as e:
                print(f"Error: {e}")
                return None

        if len(matched_events) > 1:
            # strategy: choose the event that has closest bounding box
            matched_events.sort(key=lambda event: _bounds_distance(_get_bounds_by_xpath(step["locator"]["value"]), _get_bounds_by_xpath(event.xpath)))
            return matched_events[0]

        return None

    @staticmethod
    def match_bounds_and_event(step, bounds, component_tree, events: list[AbstractEvent]) -> AbstractEvent | None:
        """
        Match the bounds with the events in the transition graph.
        :param bounds: The bounds to be matched. In (x1, y1, x2, y2) format tuple
        :param events: The list of events in the transition graph.
        :return: The matched event. If no event is found, return None.
        """
        from transition_graph.events.event import ClickEvent, TextInputEvent, TextClearEvent
        for event in events:
            if step["action"] == "click" and isinstance(event, ClickEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath_and_bounds(component_tree, event.xpath, bounds):
                    return event
            elif step["action"] == "send_keys" and isinstance(event, TextInputEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath_and_bounds(component_tree, event.xpath, bounds) and event.text == step["value"]:
                    return event
            elif step["action"] == "send_keys_clear" and isinstance(event, TextClearEvent):
                if step["locator"]["method"] == 'AppiumBy.XPATH' and Tracer.compare_xpath_and_bounds(component_tree, event.xpath, bounds):
                    return event

        return None

    def generate_event_by_step(self, step, current_state):
        from transition_graph.events.event import ClickEvent, TextInputEvent, TextClearEvent
        if step["locator"]["method"] == 'AppiumBy.XPATH':
            if step["action"] == "click":
                return ClickEvent(current_state, step["locator"]["value"])
            elif step["action"] == "send_keys":
                return TextInputEvent(current_state, step["locator"]["value"], text=step["value"])
            elif step["action"] == "send_keys_clear":
                return TextClearEvent(current_state, step["locator"]["value"])
    
    @staticmethod
    def add_oracle_to_state_node(oracle, state_node, script_loc):
        if oracle["oracle_type"] == "text":
            new_oracle = TextOracle(state_node, oracle["locator"],oracle["text"])
        elif oracle["oracle_type"] == "attr":
            new_oracle = AttributeOracle(state_node, oracle["locator"], oracle["attribute"], oracle["value"])
        elif oracle["oracle_type"] == "display":
            new_oracle = DisplayOracle(state_node, oracle["locator"], oracle["display"])
        else:
            raise Exception(f"Error: Unknown oracle type: {oracle['type']}")
        state_node.add_oracle(script_loc, new_oracle)

    @staticmethod
    def compare_xpath(component_tree, xpath1, xpath2):
        xpath1 = xpath1.replace("'", "\"")
        xpath2 = xpath2.replace("'", "\"")
        xpath1 = xpath1.replace('"', "\"")
        xpath2 = xpath2.replace('"', "\"")
        xpath1 = xpath1.strip()
        xpath2 = xpath2.strip()

        from lxml import etree

        try:
            xml_bytes = component_tree.encode('utf-8')  # Convert to bytes
            root = etree.fromstring(xml_bytes)

            elements1 = root.xpath(xpath1)
            elements2 = root.xpath(xpath2)

            if len(elements1) == 1 and len(elements2) == 1:
                # if the two elements are the same, return True
                if elements1[0] == elements2[0]:
                    return True
                # if one element is a child of the other, return True
                if elements1[0].getparent() == elements2[0] or elements2[0].getparent() == elements1[0]:
                    return True
                # if the boundary of one element is contained in the other, return True
                bounds1 = elements1[0].get('bounds')
                bounds2 = elements2[0].get('bounds')
                #  bounds: [x1,y1][x2,y2]
                if bounds1 and bounds2:
                    x1, y1, x2, y2 = map(int, bounds1.replace('][', ',').replace('[', '').replace(']', '').split(','))
                    x3, y3, x4, y4 = map(int, bounds2.replace('][', ',').replace('[', '').replace(']', '').split(','))
                    if (x1 <= x3 <= x2 and y1 <= y3 <= y2 and x1 <= x4 <= x2 and y1 <= y4 <= y2) or \
                            (x3 <= x1 <= x4 and y3 <= y1 <= y4 and x3 <= x2 <= x4 and y3 <= y2 <= y4):
                        return True

                return False
            elif len(elements1) == 0 and len(elements2) == 0:
                # If both expressions find no nodes, treat them as not equal (maybe not).
                return False
            else:
                return set(elements1) == set(elements2)

        except etree.XMLSyntaxError:
            return False
        except etree.XPathEvalError:
            return False

    @staticmethod
    def compare_xpath_and_bounds(component_tree, xpath1, bounds2):
        xpath1 = xpath1.replace("'", "\"")
        xpath1 = xpath1.replace('"', "\"")
        xpath1 = xpath1.strip()
        x1, y1, x2, y2 = bounds2

        from lxml import etree
        try:
            xml_bytes = component_tree.encode('utf-8')  # Convert to bytes
            root = etree.fromstring(xml_bytes)

            elements1 = root.xpath(xpath1)

            if len(elements1) == 1:
                bounds1 = elements1[0].get('bounds')
                if bounds1:
                    x3, y3, x4, y4 = map(int, bounds1.replace('][', ',').replace('[', '').replace(']', '').split(','))
                    if (x3 <= x1 <= x4 and y3 <= y1 <= y4 and x3 <= x2 <= x4 and y3 <= y2 <= y4):
                        return True

            return False

        except etree.XMLSyntaxError:
            return False
        except etree.XPathEvalError:
            return False
    def execute_and_trace_all_scripts(self):
        from mutator.parser.parse import parse_script

        total_scripts = 0
        successful_scripts = 0

        for script_file in self.script_dir.iterdir():
            if script_file.is_file() and script_file.suffix == ".py":
                total_scripts += 1
                try:
                    script_content = script_file.read_text(encoding='utf-8')
                    steps, oracles = parse_script(script_content)
                    self.execute_and_trace(steps, oracles, script_file.name)
                    successful_scripts += 1
                except TraceException as e:
                    print('TraceException:', e.message)
                except Exception as e: # trace exception will not abort the execution
                    print('Exception:', e)
                finally:
                    # clean device manager
                    if self.device_mgr is not None:
                        self.device_mgr.quit()
                    sleep(2)

        for i in range(10):
            self.graph_mgr.save_graph_to_file()
            print("Saved graph to file.")
            self.graph_mgr.load_graph_from_file()
            print("Loaded graph from file.")
            self.graph_mgr.save_graph_to_file()
            print("Saved graph to file.")
        
        print("Tracing scripts completed.")

        return {
            "successful_rate": successful_scripts / total_scripts if total_scripts > 0 else 0
        }

    
if __name__ == "__main__":
    yaml_file_path = "D:\code\github\ScenMut-private\mutator\explorer\input\config.yaml"
    tracer = Tracer(yaml_file_path)
    tracer.execute_and_trace_all_scripts()
