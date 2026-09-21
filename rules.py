from urllib.parse import quote

from imap_reader import encode_imap_utf7


def build_imap_uri(
    server,
    username,
    folder,
):
    """
    Baut die Thunderbird-Ziel-URI für msgFilterRules.dat.

    Wichtig:
    - Benutzername: URL-Encoding, z. B. @ -> %40
    - Ordnerpfad: IMAP Modified UTF-7, wie Thunderbird ihn selbst speichert

    Beispiel:
        INBOX/Behörden
    wird zu:
        INBOX/Beh&APY-rden
    """

    safe_user = quote(
        username,
        safe="",
    )

    thunderbird_folder = (
        encode_imap_utf7(
            folder.strip("/")
        )
    )

    return (
        f"imap://"
        f"{safe_user}"
        f"@{server}/"
        f"{thunderbird_folder}"
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
