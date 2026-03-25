class DataEntity:
    def __init__(self, key: str, entity_type: str, locator: dict, current_value: str):
        self.key = key               # e.g., "total_price"
        self.type = entity_type      # "input", "output", "input_output"
        self.locator = locator       # locator {"method": locator_method, "value": locator_value} (now using xpath only)
        self.value = current_value   # Actual text value on the current screen

    def to_dict(self):
        return {
            "key": self.key,
            "type": self.type,
            "locator": {
                "method": self.locator.get("method", ""),
                "value": self.locator.get("value", "")
            },
            "value": self.value,
        }

    @staticmethod
    def from_dict(data_entity_dict):
        data_entity = DataEntity(
            data_entity_dict["key"], 
            data_entity_dict["type"], 
            {
                "method": data_entity_dict["locator"].get("method", ""),
                "value": data_entity_dict["locator"].get("value", "")
            },
            data_entity_dict["value"]
        )
        return data_entity