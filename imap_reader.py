import base64
import email
import imaplib
import re

from collections import defaultdict
from email.utils import parseaddr

from mail_utils import (
    decode_header_value,
    get_domain,
)


# ---------------------------------------------------------
# IMAP Modified UTF-7
# ---------------------------------------------------------

def encode_imap_utf7(text):
    """
    Kodiert einen Unicode-Ordnernamen in IMAP Modified UTF-7.

    Beispiel:
        INBOX/Behörden
    """

    result = []
    buffer = []

    def flush_buffer():

        nonlocal buffer

        if not buffer:
            return

        raw = (
            "".join(buffer)
            .encode("utf-16-be")
        )

        encoded = (
            base64.b64encode(raw)
            .decode("ascii")
            .rstrip("=")
            .replace("/", ",")
        )

        result.append(
            f"&{encoded}-"
        )

        buffer = []

    for char in text:

        code = ord(char)

        # normale druckbare ASCII-Zeichen
        if 0x20 <= code <= 0x7E:

            flush_buffer()

            if char == "&":
                result.append("&-")
            else:
                result.append(char)

        else:

            buffer.append(char)

    flush_buffer()

    return "".join(result)


def decode_imap_utf7(text):
    """
    Dekodiert IMAP Modified UTF-7 nach Unicode.
    """

    if not text:
        return ""

    result = []
    index = 0

    while index < len(text):

        if text[index] != "&":

            result.append(
                text[index]
            )

            index += 1

            continue

        end = text.find(
            "-",
            index,
        )

        if end == -1:

            result.append(
                text[index:]
            )

            break

        encoded = text[
            index + 1:
            end
        ]

        # "&-" bedeutet ein echtes &
        if encoded == "":

            result.append("&")

        else:

            encoded = encoded.replace(
                ",",
                "/",
            )

            padding = "=" * (
                (-len(encoded)) % 4
            )

            try:

                raw = base64.b64decode(
                    encoded + padding
                )

                decoded = raw.decode(
                    "utf-16-be"
                )

                result.append(
                    decoded
                )

            except Exception:

                # Im Fehlerfall Original beibehalten
                result.append(
                    "&"
                    + encoded
                    + "-"
                )

        index = end + 1

    return "".join(result)


# ---------------------------------------------------------
# IMAP Verbindung
# ---------------------------------------------------------

def connect_imap(
    server,
    port,
    username,
    password,
):

    if not server:
        raise ValueError(
            "IMAP-Server fehlt."
        )

    if not username:
        raise ValueError(
            "Benutzername fehlt."
        )

    if not password:
        raise ValueError(
            "Passwort fehlt."
        )

    imap = imaplib.IMAP4_SSL(
        server,
        int(port),
    )

    imap.login(
        username,
        password,
    )

    return imap


# ---------------------------------------------------------
# IMAP LIST Parsing
# ---------------------------------------------------------

def parse_list_response(item):
    """
    Liest eine einzelne IMAP-LIST-Antwort.

    Beispiel:

        (\\HasNoChildren) "/" "INBOX/Rechnungen"

    Rückgabe:

        separator, folder
    """

    if isinstance(
        item,
        bytes,
    ):

        text = item.decode(
            "ascii",
            errors="replace",
        )

    else:

        text = str(item)

    # Standardfall:
    # (\HasNoChildren) "/" "INBOX"
    match = re.match(
        r'^\((.*?)\)\s+"([^"]*)"\s+"(.*)"$',
        text,
    )

    if match:

        separator = (
            match.group(2)
            or "/"
        )

        folder = match.group(3)

        return (
            separator,
            decode_imap_utf7(
                folder
            ),
        )

    # Alternative ohne Anführungszeichen
    match = re.match(
        r'^\((.*?)\)\s+"([^"]*)"\s+(.+)$',
        text,
    )

    if match:

        separator = (
            match.group(2)
            or "/"
        )

        folder = (
            match.group(3)
            .strip()
            .strip('"')
        )

        return (
            separator,
            decode_imap_utf7(
                folder
            ),
        )

    # Fallback
    parts = text.split()

    if not parts:
        return (
            "/",
            "",
        )

    folder = (
        parts[-1]
        .strip()
        .strip('"')
    )

    return (
        "/",
        decode_imap_utf7(
            folder
        ),
    )


# ---------------------------------------------------------
# Ordner lesen
# ---------------------------------------------------------

def get_folders(
    imap,
):

    status, data = imap.list()

    if status != "OK":

        return [
            "INBOX"
        ]

    folders = []

    for item in data:

        if not item:
            continue

        _, folder = (
            parse_list_response(
                item
            )
        )

        if folder:

            folders.append(
                folder
            )

    return sorted(
        set(folders),
        key=str.casefold,
    )


# ---------------------------------------------------------
# IMAP Separator erkennen
# ---------------------------------------------------------

def detect_imap_separator(
    imap,
):

    status, data = imap.list()

    if (
        status != "OK"
        or not data
    ):

        return "/"

    for item in data:

        if not item:
            continue

        separator, _ = (
            parse_list_response(
                item
            )
        )

        if separator:

            return separator

    return "/"


# ---------------------------------------------------------
# Ordnerstruktur neu lesen
# ---------------------------------------------------------

def refresh_folder_structure(
    server,
    port,
    username,
    password,
):

    imap = connect_imap(
        server,
        port,
        username,
        password,
    )

    try:

        return get_folders(
            imap
        )

    finally:

        try:

            imap.logout()

        except Exception:

            pass


# ---------------------------------------------------------
# Fehlende Ordner unter INBOX anlegen
# ---------------------------------------------------------

def create_missing_folders_under_inbox(
    server,
    port,
    username,
    password,
    folder_names,
    parent="INBOX",
):

    imap = connect_imap(
        server,
        port,
        username,
        password,
    )

    results = {}

    try:

        separator = (
            detect_imap_separator(
                imap
            )
        )

        existing_folders = (
            get_folders(
                imap
            )
        )

        existing_lookup = {
            folder.casefold():
            folder

            for folder
            in existing_folders
        }

        for folder_name in folder_names:

            folder_name = (
                str(folder_name)
                .strip()
            )

            if not folder_name:
                continue

            full_folder = (
                f"{parent}"
                f"{separator}"
                f"{folder_name}"
            )

            # Bereits vorhanden?
            if (
                full_folder.casefold()
                in existing_lookup
            ):

                results[
                    folder_name
                ] = {

                    "folder":
                        full_folder,

                    "success":
                        True,

                    "created":
                        False,

                    "message":
                        "Bereits vorhanden",
                }

                continue

            # -------------------------------------------------
            # Unicode -> IMAP Modified UTF-7
            # -------------------------------------------------

            encoded_folder = (
                encode_imap_utf7(
                    full_folder
                )
            )

            try:

                status, response = (
                    imap.create(
                        encoded_folder
                    )
                )

                success = (
                    status == "OK"
                )

            except Exception as exc:

                status = "NO"

                response = [
                    str(exc)
                ]

                success = False

            results[
                folder_name
            ] = {

                "folder":
                    full_folder,

                "success":
                    success,

                "created":
                    success,

                "message":
                    (
                        "Angelegt"
                        if success
                        else str(
                            response
                        )
                    ),
            }

            if success:

                existing_lookup[
                    full_folder.casefold()
                ] = full_folder

        return (
            results,
            separator,
        )

    finally:

        try:

            imap.logout()

        except Exception:

            pass


# ---------------------------------------------------------
# Mailheader auslesen
# ---------------------------------------------------------

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

    folders = get_folders(
        imap
    )

    senders = defaultdict(
        lambda: {

            "name":
                "",

            "domain":
                "",

            "count":
                0,

            "subjects":
                [],

            "folders":
                set(),
        }
    )

    total = 0

    done = 0

    try:

        for folder in folders:

            if status_callback:

                status_callback(
                    f"Lese Ordner: "
                    f"{folder}"
                )

            try:

                # IMAP erwartet auch beim SELECT
                # Modified UTF-7
                encoded_folder = (
                    encode_imap_utf7(
                        folder
                    )
                )

                status, _ = (
                    imap.select(
                        f'"{encoded_folder}"',
                        readonly=True,
                    )
                )

                if status != "OK":
                    continue

                status, data = (
                    imap.search(
                        None,
                        "ALL",
                    )
                )

                if status != "OK":
                    continue

                ids = (
                    data[0]
                    .split()
                )

                ids = ids[
                    -int(
                        max_mails_per_folder
                    ):
                ]

                for num in ids:

                    status, msg_data = (
                        imap.fetch(
                            num,
                            (
                                "BODY.PEEK["
                                "HEADER.FIELDS "
                                "(FROM SUBJECT)"
                                "]"
                            ),
                        )
                    )

                    if status != "OK":
                        continue

                    raw = None

                    for part in msg_data:

                        if isinstance(
                            part,
                            tuple,
                        ):

                            raw = (
                                part[1]
                            )

                            break

                    if not raw:
                        continue

                    msg = (
                        email
                        .message_from_bytes(
                            raw
                        )
                    )

                    raw_from = (
                        decode_header_value(
                            msg.get(
                                "From",
                                "",
                            )
                        )
                    )

                    name, address = (
                        parseaddr(
                            raw_from
                        )
                    )

                    address = (
                        address
                        .lower()
                        .strip()
                    )

                    if not address:
                        continue

                    name = (
                        decode_header_value(
                            name
                        )
                    )

                    subject = (
                        decode_header_value(
                            msg.get(
                                "Subject",
                                "",
                            )
                        )
                    )

                    info = (
                        senders[
                            address
                        ]
                    )

                    if (
                        not info[
                            "name"
                        ]
                    ):

                        info[
                            "name"
                        ] = name

                    info[
                        "domain"
                    ] = get_domain(
                        address
                    )

                    info[
                        "count"
                    ] += 1

                    info[
                        "folders"
                    ].add(
                        folder
                    )

                    if (
                        subject
                        and subject
                        not in info[
                            "subjects"
                        ]
                        and len(
                            info[
                                "subjects"
                            ]
                        )
                        <
                        int(
                            subjects_per_sender
                        )
                    ):

                        info[
                            "subjects"
                        ].append(
                            subject
                        )

                    total += 1

            except Exception as exc:

                if status_callback:

                    status_callback(
                        f"Ordner konnte "
                        f"nicht gelesen werden: "
                        f"{folder} – {exc}"
                    )

            finally:

                done += 1

                if progress_callback:

                    progress_callback(
                        done,
                        len(
                            folders
                        ),
                    )

    finally:

        try:

            imap.logout()

        except Exception:

            pass

    return (
        senders,
        total,
        folders,
    )