from lxml import etree

def get_element_by_xpath(component_tree, xpath):
    try:
        xml_bytes = component_tree.encode('utf-8')  # Convert to bytes
        root = etree.fromstring(xml_bytes)

        element = root.xpath(xpath)

        if len(element) == 1:
            return element[0]
        else:
            return None

    except etree.XMLSyntaxError:
        return None
    except etree.XPathEvalError:
        return None