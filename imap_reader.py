import imaplib, email, re
from collections import defaultdict
from email.utils import parseaddr
from mail_utils import decode_header_value, get_domain

def connect_imap(server, port, username, password):
    if not all([server, username, password]):
        raise ValueError('IMAP-Server, Benutzername oder Passwort fehlt.')
    imap = imaplib.IMAP4_SSL(server, int(port))
    imap.login(username, password)
    return imap

def get_folders(imap):
    status, data = imap.list()
    if status != 'OK':
        return ['INBOX']
    folders=[]
    for item in data:
        if not item: continue
        text=item.decode(errors='replace')
        m=re.search(r'"([^"]+)"$', text)
        folders.append(m.group(1) if m else text.split()[-1].strip('"'))
    return sorted(set(folders))

def scan_mail_headers(server, port, username, password, max_mails_per_folder=5000,
                      subjects_per_sender=5, progress_callback=None, status_callback=None):
    imap=connect_imap(server, port, username, password)
    folders=get_folders(imap)
    senders=defaultdict(lambda:{'name':'','domain':'','count':0,'subjects':[],'folders':set()})
    total=0
    try:
        for idx, folder in enumerate(folders, start=1):
            if status_callback: status_callback(f'Lese Ordner: {folder}')
            try:
                status,_=imap.select(f'"{folder}"', readonly=True)
                if status!='OK': continue
                status,data=imap.search(None,'ALL')
                if status!='OK': continue
                ids=data[0].split()[-int(max_mails_per_folder):]
                for num in ids:
                    status,msg_data=imap.fetch(num,'(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])')
                    if status!='OK': continue
                    raw=None
                    for part in msg_data:
                        if isinstance(part, tuple): raw=part[1]; break
                    if not raw: continue
                    msg=email.message_from_bytes(raw)
                    name,address=parseaddr(decode_header_value(msg.get('From','')))
                    address=address.lower().strip()
                    if not address: continue
                    subject=decode_header_value(msg.get('Subject',''))
                    info=senders[address]
                    info['name']=info['name'] or decode_header_value(name)
                    info['domain']=get_domain(address)
                    info['count']+=1
                    info['folders'].add(folder)
                    if subject and subject not in info['subjects'] and len(info['subjects'])<int(subjects_per_sender):
                        info['subjects'].append(subject)
                    total+=1
            finally:
                if progress_callback: progress_callback(idx, len(folders))
    finally:
        try: imap.logout()
        except Exception: pass
    return senders,total,folders
