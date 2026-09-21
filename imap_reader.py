import imaplib
import email
import re
from collections import defaultdict
from email.utils import parseaddr

from mail_utils import decode_header_value, get_domain


def connect_imap(server, port, username, password):
    if not server:
        raise ValueError("IMAP-Server fehlt.")

    if not username:
        raise ValueError("Benutzername fehlt.")

    if not password:
        raise ValueError("Passwort fehlt.")

    imap = imaplib.IMAP4_SSL(
        server,
        int(port),
    )

    imap.login(
        username,
        password,
    )

    return imap


def get_folders(imap):
    status, data = imap.list()

    if status != "OK":
        return ["INBOX"]

    folders = []

    for item in data:
        if not item:
            continue

        text = item.decode(errors="replace")
        match = re.search(r'"([^"]+)"$', text)

        if match:
            folder = match.group(1)
        else:
            folder = text.split()[-1].strip('"')

        folders.append(folder)

    return sorted(set(folders))


def scan_mail_headers(
    server,
    port,
    username,
    password,
    max_mails_per_folder=5000,
    subjects_per_sender=5,
    progress_callback=None,
    status_callback=None,
):
    imap = connect_imap(
        server,
        port,
        username,
        password,
    )

    folders = get_folders(imap)

    senders = defaultdict(
        lambda: {
            "name": "",
            "domain": "",
            "count": 0,
            "subjects": [],
            "folders": set(),
        }
    )

    total = 0
    done = 0

    try:
        for folder in folders:
            if status_callback:
                status_callback(f"Lese Ordner: {folder}")

            try:
                status, _ = imap.select(
                    f'"{folder}"',
                    readonly=True,
                )

                if status != "OK":
                    continue

                status, data = imap.search(
                    None,
                    "ALL",
                )

                if status != "OK":
                    continue

                ids = data[0].split()
                ids = ids[-int(max_mails_per_folder):]

                for num in ids:
                    status, msg_data = imap.fetch(
                        num,
                        "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])",
                    )

                    if status != "OK":
                        continue

                    raw = None

                    for part in msg_data:
                        if isinstance(part, tuple):
                            raw = part[1]
                            break

                    if not raw:
                        continue

                    msg = email.message_from_bytes(raw)

                    raw_from = decode_header_value(
                        msg.get("From", "")
                    )

                    name, address = parseaddr(raw_from)
                    address = address.lower().strip()

                    if not address:
                        continue

                    name = decode_header_value(name)
                    subject = decode_header_value(
                        msg.get("Subject", "")
                    )

                    info = senders[address]

                    info["name"] = info["name"] or name
                    info["domain"] = get_domain(address)
                    info["count"] += 1
                    info["folders"].add(folder)

                    if (
                        subject
                        and subject not in info["subjects"]
                        and len(info["subjects"]) < int(subjects_per_sender)
                    ):
                        info["subjects"].append(subject)

                    total += 1

            finally:
                done += 1

                if progress_callback:
                    progress_callback(
                        done,
                        len(folders),
                    )

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return senders, total, folders



def refresh_folder_structure(server, port, username, password):
    """Liest die aktuelle IMAP-Ordnerstruktur erneut vom Server."""
    imap = connect_imap(
        server,
        port,
        username,
        password,
    )

    try:
        return get_folders(imap)
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def detect_imap_separator(imap):
    """Ermittelt den IMAP-Hierarchie-Trenner, z. B. '/' oder '.'."""
    status, data = imap.list()

    if status != "OK" or not data:
        return "/"

    for item in data:
        if not item:
            continue

        text = item.decode(errors="replace")

        # Typisches LIST-Format:
        # (\HasNoChildren) "/" "INBOX"
        match = re.search(
            r'\([^\)]*\)\s+"([^"]*)"\s+"[^"]+"',
            text,
        )

        if match:
            separator = match.group(1)

            if separator:
                return separator

    return "/"


def create_missing_folders_under_inbox(
    server,
    port,
    username,
    password,
    folder_names,
    parent="INBOX",
):
    """Legt fehlende Ordner direkt unterhalb von INBOX an."""
    imap = connect_imap(
        server,
        port,
        username,
        password,
    )

    results = {}

    try:
        separator = detect_imap_separator(imap)
        existing = set(get_folders(imap))

        for folder_name in folder_names:
            if not folder_name:
                continue

            full_folder = f"{parent}{separator}{folder_name}"

            if full_folder in existing:
                results[folder_name] = {
                    "folder": full_folder,
                    "success": True,
                    "created": False,
                    "message": "Bereits vorhanden",
                }
                continue

            status, response = imap.create(full_folder)
            success = status == "OK"

            results[folder_name] = {
                "folder": full_folder,
                "success": success,
                "created": success,
                "message": (
                    "Angelegt"
                    if success
                    else str(response)
                ),
            }

            if success:
                existing.add(full_folder)

        return results, separator

    finally:
        try:
            imap.logout()
        except Exception:
            pass
