def build_imap_uri(server, username, folder):
    safe_user=username.replace('@','%40')
    return f"imap://{safe_user}@{server}/{folder.strip('/')}"

def create_rule_preview(senders, classifications, category_to_folder, server, username):
    rules=[]
    for address,info in senders.items():
        result=classifications[address]
        category=result['category']
        if category=='UNKLAR': continue
        folder=category_to_folder.get(category)
        if not folder: continue
        rules.append({
            'email':address,'domain':info['domain'],'category':category,
            'confidence':result['confidence'],'count':info['count'],'reason':result['reason'],
            'folder':folder,'folder_uri':build_imap_uri(server,username,folder)
        })
    rules.sort(key=lambda x:(x['category'],-x['count']))
    return rules

def escape_value(value):
    return value.replace('\\','\\\\').replace('"','\\"')

def generate_filter_text(rules):
    lines=['version="9"\n','logging="no"\n']
    for rule in rules:
        name=f"{rule['category']} - {rule['email']}"
        condition=f"OR (from,contains,{rule['email']})"
        lines += [
            '\n', f'name="{escape_value(name)}"\n', 'enabled="yes"\n', 'type="17"\n',
            'action="Move to folder"\n', f'actionValue="{escape_value(rule["folder_uri"])}"\n',
            f'condition="{escape_value(condition)}"\n'
        ]
    return ''.join(lines)
