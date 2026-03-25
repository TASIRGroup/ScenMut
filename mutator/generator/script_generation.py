"""
Generate an Appium Python script (parseable by `parse_script`) from a
`ScriptPath` (sequence of path nodes: `PathNode` / `InternalPathNode` plus
events and oracles).

Includes a preamble (imports/options/driver) and path steps
(`find_element` + operation + assertions).
"""

from typing import Optional

from transition_graph import ScriptPath
from transition_graph.paths.path_node import PathNode, InternalPathNode
from transition_graph.events.event import ClickEvent, TextInputEvent, TextClearEvent, BackEvent


def generate_script_of_mutated_path(
    mutated_path: ScriptPath,
    config: Optional[dict] = None,
) -> str:
    """
    Generate a complete Appium Python script string from a mutated path.

    :param mutated_path: The mutated script path (`ScriptPath`).
    :param config: Optional config used to fill `appPackage`, `appActivity`,
        `serverUrl`, etc. If `None`, placeholders are used.
    :return: Full script content string, consistent with
        `mutator/parser/example_script/test_script.py`, and parseable by
        `mutator/parser/parse.parse_script`.
    """
    lines = [_preamble(config)]
    el_counter = 1

    for path_node in mutated_path.to_array():
        if isinstance(path_node, InternalPathNode):
            continue

        if not isinstance(path_node, PathNode):
            continue

        # 1) Generate oracle assertion(s) for the current node.
        oracles = getattr(path_node, "oracles", None) or []
        if len(oracles) > 0:
            lines.append(f"    sleep(2)")
        for oracle in oracles:
            od = oracle.to_dict()
            locator = od.get("locator") or {}
            method = locator.get("method", "AppiumBy.XPATH")
            value = locator.get("value", "")
            otype = (od.get("type") or "text").strip().lower()
            if otype == "text":
                lines.append(
                    f"    el{el_counter} = (safe_find_element(driver, {method}, {_repr_xpath(value)})).text"
                )
                expected = od.get("text") or ""
                validation_type = od.get("validation_type") or "exact"
                # text has multiple lines
                if "\n" in expected:
                    # use triple quotes to represent multiple lines
                    expected = f'"""{expected}"""'
                    if validation_type == "exact":
                        lines.append(f'    assert el{el_counter} == {expected}')
                    elif validation_type == "contains":
                        lines.append(f'    assert {expected} in el{el_counter}')
                    elif validation_type == "startswith":
                        lines.append(f'    assert el{el_counter}.startswith({expected})')
                    elif validation_type == "endswith":
                        lines.append(f'    assert el{el_counter}.endswith({expected})')
                else:
                    if validation_type == "exact":
                        lines.append(f'    assert el{el_counter} == "{_escape_quotes(expected)}"')
                    elif validation_type == "contains":
                        lines.append(f'    assert "{_escape_quotes(expected)}" in el{el_counter}')
                    elif validation_type == "startswith":
                        lines.append(f'    assert el{el_counter}.startswith("{_escape_quotes(expected)}")')
                    elif validation_type == "endswith":
                        lines.append(f'    assert el{el_counter}.endswith("{_escape_quotes(expected)}")')
            elif otype == "attribute":
                attr = od.get("attribute") or ""
                lines.append(
                    f"    el{el_counter} = (safe_find_element(driver, {method}, {_repr_xpath(value)})).get_attribute(\"{_escape_quotes(attr)}\")"
                )
                expected = od.get("value") or ""
                lines.append(f'    assert el{el_counter} == "{_escape_quotes(expected)}"')
            elif otype == "display":
                lines.append(
                    f"    el{el_counter} = (safe_find_element(driver, {method}, {_repr_xpath(value)})).is_displayed()"
                )
                display_val = bool(od.get("display", False))
                lines.append(f"    assert el{el_counter} is {display_val}")
            else:
                continue
            el_counter += 1

        # 2) Generate operation code for the current node (`event`).
        lines.append(f"    sleep(2)")
        if path_node.event is not None:
            event = path_node.event
            method, value = _locator_from_event(event)
            xpath_value = value

            if isinstance(event, BackEvent):
                lines.append("    driver.back()")
            else:
                lines.append(
                    f"    el{el_counter} = safe_find_element(driver, AppiumBy.XPATH, {_repr_xpath(xpath_value)})"
                )
                if isinstance(event, ClickEvent):
                    lines.append(f"    el{el_counter}.click()")
                elif isinstance(event, TextInputEvent):
                    text = event.text if event.text is not None else ""
                    lines.append(f'    el{el_counter}.send_keys("{_escape_quotes(text)}")')
                elif isinstance(event, TextClearEvent):
                    lines.append(f"    el{el_counter}.clear()")
                else:
                    # Unknown event type; use a click placeholder.
                    lines.append(f"    el{el_counter}.click()")
                el_counter += 1

    # Add `finally: driver.quit()`.
    lines.append("finally:")
    lines.append("    driver.quit()")
    return "\n".join(lines)

SAFE_FIND_ELEMENT_FUNC = f"""
def safe_find_element(driver, by, value, timeout=10, check_interval=0.5):
    import time
    from selenium.common.exceptions import (
        NoSuchElementException, 
        StaleElementReferenceException,
        TimeoutException
    )
    
    start_time = time.time()
    last_exception = None
    
    while time.time() - start_time < timeout:
        try:
            element = driver.find_element(by, value)
            element.is_displayed()
            return element
            
        except (NoSuchElementException, StaleElementReferenceException) as e:
            last_exception = e
            time.sleep(check_interval)
            continue
    
    # debug information
    try:
        from appium.webdriver.common.appiumby import AppiumBy
        items = driver.find_elements(
            AppiumBy.XPATH, 
            '//androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout'
        )
        print(f"[safe_find_element] timeout, target: {{value}}")
        print(f"[safe_find_element] current RecyclerView item count: {{len(items)}}")
        for i, item in enumerate(items[:10]):
            print(f"  Item {{i+1}}: {{item.text or 'no text'}}")
    except Exception as debug_ex:
        print(f"[safe_find_element] debug information failed: {{debug_ex}}")
    
    raise TimeoutException(f"Element not found in {{timeout}}s: {{value}}") from last_exception
"""

def _preamble(config: Optional[dict]) -> str:
    """Generate the script preamble: imports, `AppiumOptions`, capabilities, and driver."""
    appium = (config or {}).get("appium", {})
    app_package = appium.get("appPackage", "com.example.myapplication")
    app_activity = appium.get("appActivity", "com.example.myapplication.MainActivity")
    server_url = appium.get("serverUrl", "http://localhost:4723")

    return f'''# This sample code supports Appium Python client >=2.3.0
# pip install Appium-Python-Client
# Then you can paste this into a file and simply run with Python
from time import sleep

from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy

# For W3C actions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

options = AppiumOptions()
options.load_capabilities({{
\t"platformName": "Android",
\t"appium:automationName": "uiautomator2",
\t"appium:deviceName": "android",
\t"appium:appPackage": "{_escape_quotes(app_package)}",
\t"appium:appActivity": "{_escape_quotes(app_activity)}",
\t"appium:language": "en",
\t"appium:locale": "US",
\t"appium:serverUrl": "{_escape_quotes(server_url)}",
\t"udid": "device_id", # Device id will be injected by the evaluator. If you don't want to use device id, you can remove this line.
\t"systemPort": "system_port", # System port will be injected by the evaluator. If you don't want to use system port, you can remove this line.
\t"appium:ensureWebviewsHavePages": True,
\t"appium:nativeWebScreenshot": True,
\t"appium:newCommandTimeout": 3600,
\t"appium:connectHardwareKeyboard": True
}})

driver = webdriver.Remote("{_escape_quotes(server_url)}", options=options)

{SAFE_FIND_ELEMENT_FUNC}

sleep(3)

try:'''

def _locator_from_event(event) -> tuple:
    """Get `(method, value)` from an event, used for `find_element(by=..., value=...)`."""
    if isinstance(event, (ClickEvent, TextInputEvent, TextClearEvent)):
        return "AppiumBy.XPATH", (event.xpath or "")
    return "AppiumBy.XPATH", ""


def _repr_xpath(xpath: str) -> str:
    """
    Convert an xpath string into a Python literal to avoid syntax errors caused
    by "real newlines" in the generated script source code.

    For example, if a locator contains newlines and you concatenate it
    directly with single quotes, the generated result may span multiple lines.
    Using `repr` instead emits the escaped form (e.g., `\\n`) so the source
    code does not break lines, while the runtime string value remains the same.
    """
    # Note: handle not only backslashes/single quotes, but also control characters
    # (especially newlines).
    if any(ch in xpath for ch in ["\\", "'", "\n", "\r", "\t"]):
        return repr(xpath)
    return "'" + xpath + "'"


def _escape_quotes(s: str) -> str:
    """Escape backslashes and double quotes inside a double-quoted Python string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
