from device_infrastructure import DeviceManager

from transition_graph.utils.mock_strategy import MockStrategy


class AbstractEvent:
    counter = 0

    def __init__(self, state_node):
        self.type = "abstract"
        self.state_node = state_node # indicates the state node that the event belongs to
        self.event_id = AbstractEvent.counter
        AbstractEvent.counter += 1

        # semantic label
        self.semantic_label = ""
        self.has_data_side_effect = False

    def perform(self, device_mng: DeviceManager):
        raise NotImplementedError

    def equals(self, other) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError

    @staticmethod
    def from_dict(event_dict: dict):
        event = None
        if event_dict["event_type"] == "click":
            event = ClickEvent(None, event_dict["xpath"], (event_dict["position_x"], event_dict["position_y"]) if event_dict["position_x"] is not None else None)
        elif event_dict["event_type"] == "text_input":
            event = TextInputEvent(None, event_dict["xpath"], MockStrategy.from_dict(event_dict["mock_strategy"]) if event_dict["mock_strategy"] is not None else None, event_dict["text"] if event_dict["text"] is not None else None)
        elif event_dict["event_type"] == "back":
            event = BackEvent(None)
        elif event_dict["event_type"] == "text_clear":
            event = TextClearEvent(None, event_dict["xpath"])
        elif event_dict["event_type"] == "internal":
            event = InternalEvent(None)
        else:
            print(f"Unknown event type: {event_dict['event_type']}")
            return None
        event.event_id = event_dict["event_id"]
        event.semantic_label = event_dict["semantic_label"] if "semantic_label" in event_dict else ""
        event.has_data_side_effect = event_dict["has_data_side_effect"] if "has_data_side_effect" in event_dict else False
        return event

class ClickEvent(AbstractEvent):
    from transition_graph.nodes.state_node import StateNode

    def __init__(self, state_node, xpath, position=None):
        """
        Create a click event
        :param state_node: the state node that the event belongs to
        :param xpath: the xpath of the element to be clicked
        :param position: the position of the element to be clicked. If not provided, the xpath will be used to locate the element. Otherwise, the position will be used.
        """
        super(ClickEvent, self).__init__(state_node)
        self.type = "click"
        self.xpath = xpath
        if position is not None:
            self.position_x, self.position_y = position
        else:
            self.position_x = None
            self.position_y = None

    def __str__(self):
        return f"ClickEvent event_{self.event_id} on state_node_{self.state_node.id}: (Xpath: {self.xpath}, Position: ({self.position_x}, {self.position_y}))"

    def perform(self, device_mng: DeviceManager):
        if self.position_x is None or self.position_y is None:
            # locate the element by xpath
            device_mng.click_by_xpath(self.xpath)
        else:
            device_mng.click_by_coordinate(self.position_x, self.position_y)

    def equals(self, other) -> bool:
        if self.type != other.type:
            return False
        if self.xpath != other.xpath:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "state_node_id": self.state_node.id,
            "event_id": self.event_id,
            "event_type": self.type,
            "xpath": self.xpath,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "semantic_label": self.semantic_label,
            "has_data_side_effect": self.has_data_side_effect
        }

class TextInputEvent(AbstractEvent):
    from transition_graph.utils.mock_strategy import MockStrategy

    def __init__(self, state_node, xpath, mock_strategy: MockStrategy, text=None):
        """
        Create a text input event
        :param state_node: the state node that the event belongs to
        :param xpath: the xpath of the element to input text
        :param mock_strategy: the mock strategy to generate the input text
        :param text: the text to be input. If not provided, the mock strategy will be used to generate the text. Otherwise, the text will be used.
        """
        super(TextInputEvent, self).__init__(state_node)
        self.type = "text_input"
        self.xpath = xpath
        self.mock_strategy = mock_strategy
        self.text = text

    def __str__(self):
        return f"TextInputEvent event_{self.event_id} on state_node_{self.state_node.id}: {self.xpath} (Mock Strategy: {self.mock_strategy}, Text: {self.text})"

    def perform(self, device_mng: DeviceManager):
        if self.text is None:
            text = self.mock_strategy.generate_text()
        else:
            text = self.text
        device_mng.text_input(self.xpath, text)

    def get_text(self):
        if self.text is None:
            text = self.mock_strategy.generate_text()
        else:
            text = self.text
        return text
    
    def equals(self, other) -> bool:
        if self.type != other.type:
            return False
        if self.xpath != other.xpath:
            return False
        if self.text != other.text:
            return False
        if not (self.mock_strategy is not None and other.mock_strategy is not None):
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "state_node_id": self.state_node.id,
            "event_id": self.event_id,
            "event_type": self.type,
            "xpath": self.xpath,
            "mock_strategy": self.mock_strategy.to_dict(),
            "text": self.text,
            "semantic_label": self.semantic_label,
            "has_data_side_effect": self.has_data_side_effect
        }

class TextClearEvent(AbstractEvent):
    def __init__(self, state_node, xpath):
        """
        Create a text clear event
        :param state_node: the state node that the event belongs to
        :param xpath: the xpath of the element to be cleared
        """
        super(TextClearEvent, self).__init__(state_node)
        self.type = "text_clear"
        self.xpath = xpath

    def __str__(self):
        return f"TextClearEvent event_{self.event_id} on {self.state_node.id}"

    def perform(self, device_mng: DeviceManager):
        device_mng.text_clear(self.xpath)

    def equals(self, other) -> bool:
        if self.type != other.type:
            return False
        if self.xpath != other.xpath:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "state_node_id": self.state_node.id,
            "event_id": self.event_id,
            "event_type": self.type,
            "xpath": self.xpath,
            "semantic_label": self.semantic_label,
            "has_data_side_effect": self.has_data_side_effect
        }

class BackEvent(AbstractEvent):

    def __init__(self, state_node):
        """
        Create a back event
        :param state_node: the state node that the event belongs to
        """
        super(BackEvent, self).__init__(state_node)
        self.type = "back"

    def __str__(self):
        return f"BackEvent event_{self.event_id} on {self.state_node.id}"

    def perform(self, device_mng: DeviceManager):
        device_mng.back()

    def equals(self, other) -> bool:
        if self.type != other.type:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "state_node_id": self.state_node.id,
            "event_id": self.event_id,
            "event_type": self.type,
            "semantic_label": self.semantic_label,
            "has_data_side_effect": self.has_data_side_effect
        }

class InternalEvent(AbstractEvent):

    def __init__(self, state_node):
        """
        Create an internal event
        :param state_node: the state node that the event belongs to
        """
        super(InternalEvent, self).__init__(state_node)
        self.type = "internal"

    def __str__(self):
        return f"InternalEvent event_{self.event_id} on {self.state_node.id}"

    def perform(self, device_mng: DeviceManager):
        print(f"Event perform Error: Trying to perform an internal event {self.event_id}")
        raise NotImplementedError

    def to_dict(self) -> dict:
        return {
            "state_node_id": self.state_node.id,
            "event_id": self.event_id,
            "event_type": self.type
        }