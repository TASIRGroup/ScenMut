from typing import Dict
from ..utils.element_finder import get_element_by_xpath

def _clean_locator(locator: Dict[str, str]) -> Dict[str, str]:
    if "value" in locator:
        value = locator["value"]
        if value.endswith("').text") or value.endswith('").text'):
            locator["value"] = value[:-len("').text")]
    return locator

def _migrate_locator_by_text(locator: Dict[str, str], text: str) -> Dict[str, str]:
    import re

    if locator["method"] == "AppiumBy.XPATH":
        xpath = locator["value"]

        # Match @text='...' or @text="..."
        # re.DOTALL so '.' also matches real newlines inside the attribute value
        def replacer(m: re.Match) -> str:
            quote = m.group(1)  # captured quote char: ' or "
            return f"@text={quote}{text}{quote}"

        new_xpath = re.sub(r'@text=([\'"])(.*?)\1', replacer, xpath, flags=re.DOTALL)

        return {**locator, "value": new_xpath}
    else:
        return locator

class AbstractOracle:
    counter = 0

    def __init__(self, state_node, locator: Dict[str, str]):
        """
        Docstring for __init__
        
        :param state_node: indicates the state node that the oracle belongs to
        :param locator: the locator of the element. Format: {"method": AppiumBy.*, "value": locator_value}
        :type locator: Dict[str, str]
        """
        self.state_node = state_node # indicates the state node that the oracle belongs to
        self.locator = _clean_locator(locator)
        self.event_id = AbstractOracle.counter
        AbstractOracle.counter += 1

    def migrate(self, state_node):
        raise NotImplementedError
    
    def verify(self, state_node):
        raise NotImplementedError

    def _get_element(self, state_node):
        if self.locator["method"] == "AppiumBy.XPATH":
            element = get_element_by_xpath(state_node.component_tree, self.locator["value"])
        # more methods can be added here
        else:
            return None
        
        return element

    def to_dict(self) -> dict:
        raise NotImplementedError
    
class TextOracle(AbstractOracle):
    from transition_graph.nodes.state_node import StateNode

    def __init__(self, state_node: StateNode, locator: Dict[str, str], text: str, validation_type: str = "exact"):
        if validation_type == 'exact':
            locator = _migrate_locator_by_text(locator, text)
        super().__init__(state_node, locator)
        self.text = text
        if validation_type not in ["exact", "contains", "startswith", "endswith"]:
            raise ValueError(f"Invalid validation type: {validation_type}")
        self.validation_type = validation_type

    def migrate(self, state_node: StateNode) -> AbstractOracle:
        element = self._get_element(state_node)
        if element is None:
            return DisplayOracle(state_node, self.locator, False)
        return TextOracle(state_node, self.locator, element.text, self.validation_type)
    def verify(self, state_node: StateNode) -> bool:
        element = self._get_element(state_node)
        if element is None:
            return False
        if self.validation_type == "exact":
            return element.text == self.text
        elif self.validation_type == "contains":
            return self.text in element.text
        elif self.validation_type == "startswith":
            return element.text.startswith(self.text)
        elif self.validation_type == "endswith":
            return element.text.endswith(self.text)
    
    def to_dict(self) -> dict:
        return {
            "type": "text",
            "text": self.text,
            "locator": self.locator,
            "validation_type": self.validation_type
        }


class AttributeOracle(AbstractOracle):
    from transition_graph.nodes.state_node import StateNode

    def __init__(self, state_node: StateNode, locator: Dict[str, str], attribute: str, value: str):
        super().__init__(state_node, locator)
        self.attribute = attribute
        self.value = value

    def migrate(self, state_node: StateNode) -> AbstractOracle:
        element = self._get_element(state_node)
        if element is None:
            return DisplayOracle(state_node, self.locator, False)
        return AttributeOracle(state_node, self.locator, self.attribute, element.get_attribute(self.attribute))
    
    def verify(self, state_node: StateNode) -> bool:
        element = self._get_element(state_node)
        if element is None:
            return False
        return element.get_attribute(self.attribute) == self.value
    
    def to_dict(self) -> dict:
        return {
            "type": "attribute",
            "attribute": self.attribute,
            "value": self.value,
            "locator": self.locator
        }

class DisplayOracle(AbstractOracle):
    from transition_graph.nodes.state_node import StateNode

    def __init__(self, state_node: StateNode, locator: Dict[str, str], display: bool):
        super().__init__(state_node, locator)
        self.display = display

    def migrate(self, state_node: StateNode) -> AbstractOracle:
        element = self._get_element(state_node)
        if element is None:
            return DisplayOracle(state_node, self.locator, False)
        return DisplayOracle(state_node, self.locator, element.is_displayed())
    
    def verify(self, state_node):
        element = self._get_element(state_node)
        if element is None:
            return False
        return element.is_displayed() == self.display
    
    def to_dict(self) -> dict:
        return {
            "type": "display",
            "display": self.display,
            "locator": self.locator
        }
