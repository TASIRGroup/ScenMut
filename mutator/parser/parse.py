import re


def parse_script(script_content):
    steps = []
    oracles = []
    # Tuple(step_idx: int, dict)
    # step_idx: corresponding step index
    # dict: {
    #   "oracle_type": attr | text | display, 
    #   "locator": {"method": AppiumBy.*, "value": locator_value}, 
    #   "text": str | None,
    #   "attribute": str | None,
    #   "value": str | None,
    #   "display": bool | None
    # }
    lines = script_content.split('\n')

    current_element = None
    current_locator = None
    
    # Oracle parsing state
    oracle_vars = {}  # {var_name: {"type": oracle_type, "locator": locator, "attribute": attr_name}}

    for line in lines:
        if "driver.back()" in line:
            steps.append({
                "action": "back",
                "locator": None
            })
            continue
        # element locator
        if "find_element" in line and "=" in line:
            locator_parts = line.split("find_element")
            if len(locator_parts) > 1:
                locator_method = locator_parts[1].strip('(').strip(')').split(",")[0].strip().replace("by=", "")
                locator_value = locator_parts[1].strip('(').strip(')').split(",")[1].strip().replace("value=", "").strip('\'').strip('\"')

                var_name = line.split("=")[0].strip()

                current_element = var_name
                current_locator = {"method": locator_method, "value": locator_value}
                
                # Check for inline oracle patterns
                # Text oracle: var = driver.find_element(...).text
                if ".text" in line and ".text" in line.split("find_element")[1]:
                    oracle_vars[var_name] = {
                        "type": "text",
                        "locator": current_locator
                    }
                # Display oracle: var = driver.find_element(...).is_displayed()
                elif ".is_displayed()" in line:
                    oracle_vars[var_name] = {
                        "type": "display",
                        "locator": current_locator
                    }

        # element action
        elif current_element and current_element in line:
            if ".send_keys" in line:
                input_value = line.replace("\'", "\"").split('send_keys("')[1].split('")')[0]
                steps.append({
                    "action": "send_keys",
                    "locator": current_locator,
                    "value": input_value
                })
            elif ".click" in line:
                steps.append({
                    "action": "click",
                    "locator": current_locator
                })
            elif ".clear" in line:
                steps.append({
                    "action": "send_keys_clear",
                    "locator": current_locator
                })
            # Attribute oracle: var = element.get_attribute("attr_name")
            elif ".get_attribute" in line and "=" in line:
                attr_var = line.split("=")[0].strip()
                attr_match = line.split(".get_attribute(")[1].split(")")[0]
                attr_name = attr_match.strip('\'').strip('\"')
                oracle_vars[attr_var] = {
                    "type": "attr",
                    "locator": current_locator,
                    "attribute": attr_name
                }
        
        # Parse assert statements for oracles
        if "assert" in line:
            step_idx = len(steps) - 1 if steps else 0
            
            for var_name, oracle_info in oracle_vars.items():
                if var_name in line:
                    oracle = {
                        "oracle_type": oracle_info["type"],
                        "locator": oracle_info["locator"],
                        "text": None,
                        "attribute": None,
                        "value": None,
                        "display": None
                    }
                    
                    if oracle_info["type"] == "text":
                        # Extract expected text from assert: assert var == "expected"
                        if "==" in line:
                            expected = _extract_expected_value(line)
                            oracle["text"] = expected
                    
                    elif oracle_info["type"] == "attr":
                        oracle["attribute"] = oracle_info.get("attribute")
                        # Extract expected value from assert
                        if "==" in line:
                            expected = _extract_expected_value(line)
                            oracle["value"] = expected
                    
                    elif oracle_info["type"] == "display":
                        # Extract expected display status
                        if "True" in line or "is True" in line:
                            oracle["display"] = True
                        elif "False" in line or "is False" in line:
                            oracle["display"] = False
                    
                    oracles.append((step_idx, oracle))
                    break

    return steps, oracles


def _extract_expected_value(line):
    """Extract expected value from assert statement."""
    try:
        if "==" in line:
            right_part = line.split("==")[1].strip()
            # Handle quoted strings
            if right_part.startswith('"') or right_part.startswith("'"):
                quote_char = right_part[0]
                end_idx = right_part.find(quote_char, 1)
                if end_idx != -1:
                    return right_part[1:end_idx]
            # Handle unquoted values (like True, False, or simple strings)
            else:
                # Remove trailing comma and assertion message
                value = right_part.split(",")[0].strip()
                return value
    except (IndexError, ValueError):
        pass
    return None
