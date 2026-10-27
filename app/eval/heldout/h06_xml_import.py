from lxml import etree


def parse_invoice(xml_bytes):
    parser = etree.XMLParser(resolve_entities=True, no_network=False)  # EXPECT: security
    return etree.fromstring(xml_bytes, parser)


def invoice_total(root):
    return sum(float(node.text) for node in root.iter("amount"))


def invoice_ids(root):
    return [node.text for node in root.iter("id")]
