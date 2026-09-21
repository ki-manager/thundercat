from email.header import decode_header


def decode_header_value(value):
    if not value:
        return ""

    result = []

    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            try:
                result.append(
                    part.decode(
                        encoding or "utf-8",
                        errors="replace",
                    )
                )
            except Exception:
                result.append(
                    part.decode(
                        "utf-8",
                        errors="replace",
                    )
                )
        else:
            result.append(part)

    return "".join(result)


def get_domain(address):
    if "@" not in address:
        return ""

    return address.split("@")[-1].lower().strip()
