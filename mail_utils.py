from email.header import decode_header

def decode_header_value(value):
    if not value:
        return ""
    out=[]
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            out.append(part.decode(enc or 'utf-8', errors='replace'))
        else:
            out.append(part)
    return ''.join(out)

def get_domain(address):
    return address.split('@')[-1].lower().strip() if '@' in address else ''
