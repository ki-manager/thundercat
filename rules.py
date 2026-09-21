from urllib.parse import quote


def build_imap_uri(
    server,
    username,
    folder,
):
    safe_user = quote(
        username,
        safe="",
    )

    safe_folder = "/".join(
        quote(
            part,
            safe="",
        )
        for part in folder.strip("/").split("/")
    )

    return (
        f"imap://"
        f"{safe_user}"
        f"@{server}/"
        f"{safe_folder}"
    )


def create_rule_preview(
    senders,
    classifications,
    category_to_folder,
    server,
    username,
):
    rules = []

    for address, info in senders.items():
        result = classifications[address]
        category = result["category"]

        if category == "Unklar":
            continue

        folder = category_to_folder.get(
            category
        )

        if not folder:
            continue

        folder_uri = build_imap_uri(
            server=server,
            username=username,
            folder=folder,
        )

        rules.append({
            "email": address,
            "domain": info["domain"],
            "category": category,
            "confidence": result["confidence"],
            "count": info["count"],
            "reason": result["reason"],
            "folder": folder,
            "folder_uri": folder_uri,
        })

    rules.sort(
        key=lambda item: (
            item["category"],
            -item["count"],
        )
    )

    return rules


def escape_value(value):
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )


def generate_filter_text(rules):
    lines = [
        'version="9"\n',
        'logging="no"\n',
    ]

    for rule in rules:
        name = (
            f"{rule['category']} - "
            f"{rule['email']}"
        )

        condition = (
            "OR "
            f"(from,contains,"
            f"{rule['email']})"
        )

        lines.append("\n")
        lines.append(
            f'name="{escape_value(name)}"\n'
        )
        lines.append(
            'enabled="yes"\n'
        )
        lines.append(
            'type="17"\n'
        )
        lines.append(
            'action="Move to folder"\n'
        )
        lines.append(
            f'actionValue="'
            f'{escape_value(rule["folder_uri"])}"\n'
        )
        lines.append(
            f'condition="'
            f'{escape_value(condition)}"\n'
        )

    return "".join(lines)
