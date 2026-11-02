"""Candidate AX naming only; mirrors legacy ax_name and name_equals."""
def ax_name(element):
    if not isinstance(element, dict):
        raise ValueError("malformed element")
    label = element.get("label")
    if isinstance(label, str) and label.strip():
        return label
    value = element.get("value")
    return value if isinstance(value, str) else ""

def candidate_name(element):
    # Existing normalized synthetic inputs remain supported. Raw fields always
    # take precedence; a forged normalized name cannot override raw AX values.
    if "label" in element or "value" in element:
        return ax_name(element)
    name = element.get("name")
    return name if isinstance(name, str) else ""

def name_equals(element, expected):
    return candidate_name(element).strip() == expected.strip()
