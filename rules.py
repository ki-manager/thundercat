from config import FOLDER_MAP

def create_rule_preview(senders, classifications, folder_map=None):
    folder_map = folder_map or FOLDER_MAP
    rules = []

    for address, info in senders.items():
        result = classifications[address]
        category = result["category"]

        if category == "UNKLAR":
            continue

        folder = folder_map.get(category)
        if not folder:
            continue

        rules.append({
            "email": address,
            "domain": info["domain"],
            "category": category,
            "confidence": result["confidence"],
            "count": info["count"],
            "reason": result["reason"],
            "folder": folder,
        })

    rules.sort(key=lambda item: (item["category"], -item["count"]))
    return rules

def escape_value(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')

def generate_filter_text(rules):
    lines = ['version="9"\n', 'logging="no"\n']

    for rule in rules:
        name = f"{rule['category']} - {rule['email']}"
        condition = f"OR (from,contains,{rule['email']})"

        lines.append("\n")
        lines.append(f'name="{escape_value(name)}"\n')
        lines.append('enabled="yes"\n')
        lines.append('type="17"\n')
        lines.append('action="Move to folder"\n')
        lines.append(f'actionValue="{escape_value(rule["folder"])}"\n')
        lines.append(f'condition="{escape_value(condition)}"\n')

    return "".join(lines)
