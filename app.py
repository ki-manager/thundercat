import time
import pandas as pd
import streamlit as st
from config import *
from imap_reader import scan_mail_headers
from ollama_client import test_ollama, classify_all
from rules import create_rule_preview, generate_filter_text

st.set_page_config(page_title='Thunderbird Ollama Mail Sorter', page_icon='📧', layout='wide')
st.title('📧 Thunderbird Ollama Mail Sorter v3')
st.caption('Batch-Klassifizierung, lokaler Cache und Thunderbird-Filterdatei.')

def init_state():
    defaults={'step':1,'senders':None,'classifications':None,'rules':None,'filter_text':None,
              'total_mails':0,'folders':[],'category_to_folder':{},'imap_server':'','imap_port':993,
              'imap_username':'','stats':None}
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k]=v
init_state()

with st.sidebar:
    st.header('Einstellungen')
    st.subheader('IMAP')
    imap_server=st.text_input('IMAP-Server', value=st.session_state.imap_server, placeholder='imap.example.de')
    imap_port=st.number_input('IMAP-Port', min_value=1, max_value=65535, value=int(st.session_state.imap_port))
    imap_username=st.text_input('Benutzername / E-Mail', value=st.session_state.imap_username)
    imap_password=st.text_input('Passwort', type='password')
    st.divider(); st.subheader('Ollama')
    ollama_url=st.text_input('Ollama-URL', value=OLLAMA_URL)
    ollama_model=st.text_input('Ollama-Modell', value=OLLAMA_MODEL)
    batch_size=st.number_input('Batch-Größe', min_value=1, max_value=100, value=BATCH_SIZE)
    st.divider(); st.subheader('Analyse')
    max_mails=st.number_input('Max. Mails pro Ordner', min_value=1, value=MAX_MAILS_PER_FOLDER, step=100)
    subjects_per_sender=st.number_input('Beispiel-Betreffzeilen pro Absender', min_value=1, max_value=20, value=SUBJECTS_PER_SENDER)
    min_confidence=st.slider('Mindest-Sicherheit',0.0,1.0,float(MIN_CONFIDENCE),0.05)
    force_reclassify=st.checkbox('Cache ignorieren und alles neu klassifizieren', value=False)

st.info(f'Aktueller Schritt: {st.session_state.step} von 5')

if st.session_state.step==1:
    st.header('1. IMAP-Zugang und Header auslesen')
    st.write('Es werden nur Absender, Domain und einige Betreffzeilen gelesen. Der Nachrichtentext wird nicht ausgewertet.')
    if st.button('IMAP testen und Header auslesen', type='primary', use_container_width=True):
        if not imap_server or not imap_username or not imap_password:
            st.error('Bitte IMAP-Server, Benutzername und Passwort eintragen.')
        else:
            progress=st.progress(0.0); status_box=st.empty()
            try:
                senders,total,folders=scan_mail_headers(
                    imap_server,imap_port,imap_username,imap_password,max_mails,subjects_per_sender,
                    progress_callback=lambda d,t: progress.progress(d/max(t,1)),
                    status_callback=lambda txt: status_box.info(txt))
                st.session_state.senders=senders; st.session_state.total_mails=total; st.session_state.folders=folders
                st.session_state.imap_server=imap_server; st.session_state.imap_port=int(imap_port); st.session_state.imap_username=imap_username
                progress.progress(1.0); status_box.success('IMAP-Auslesen abgeschlossen.')
                st.success(f'{total} Mails analysiert, {len(senders)} eindeutige Absender gefunden.')
            except Exception as exc:
                st.error(f'IMAP-Fehler: {exc}')
    if st.session_state.senders and st.button('Weiter zu den Absendern', type='primary'):
        st.session_state.step=2; st.rerun()

elif st.session_state.step==2:
    st.header('2. Gefundene Absender')
    rows=[{'Name':i['name'],'E-Mail':a,'Domain':i['domain'],'Anzahl':i['count'],'Betreff-Beispiele':' | '.join(i['subjects'])}
          for a,i in sorted(st.session_state.senders.items(), key=lambda x:-x[1]['count'])]
    df=pd.DataFrame(rows); st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button('Absenderliste als CSV herunterladen', df.to_csv(index=False,sep=';').encode('utf-8-sig'),'senders.csv','text/csv')
    c1,c2=st.columns(2)
    with c1:
        if st.button('Zurück'): st.session_state.step=1; st.rerun()
    with c2:
        if st.button('Weiter zur Ollama-Analyse',type='primary',use_container_width=True): st.session_state.step=3; st.rerun()

elif st.session_state.step==3:
    st.header('3. Ollama-Klassifizierung')
    st.caption('v3 verarbeitet mehrere Absender pro Anfrage und verwendet einen lokalen Cache.')
    if st.session_state.classifications is None:
        if st.button('Ollama prüfen und Analyse starten',type='primary'):
            try:
                status=test_ollama(ollama_url,ollama_model)
                if not status['ok']:
                    st.error(f"Modell '{ollama_model}' wurde nicht gefunden.")
                    if status['models']: st.write('Installierte Modelle:', status['models'])
                else:
                    progress=st.progress(0.0); status_box=st.empty(); stats_box=st.empty(); started=time.time()
                    def prog(done,total,cached,total_new):
                        progress.progress(done/max(total,1))
                        stats_box.info(f'{done}/{total} Absender | Cache: {cached} | Neu: {total_new} | Laufzeit: {time.time()-started:.1f}s')
                    classifications,stats=classify_all(
                        ollama_url,ollama_model,st.session_state.senders,min_confidence,int(batch_size),
                        progress_callback=prog,status_callback=lambda txt: status_box.info(txt),force_reclassify=force_reclassify)
                    st.session_state.classifications=classifications; st.session_state.stats=stats
                    progress.progress(1.0); status_box.success('Ollama-Analyse abgeschlossen.'); st.rerun()
            except Exception as exc:
                st.error(f'Ollama-Fehler: {exc}')
    else:
        stats=st.session_state.stats or {'total':0,'cached':0,'new':0}
        st.success(f"{stats['total']} Absender ausgewertet: {stats['cached']} aus Cache, {stats['new']} neu mit Ollama.")
        rows=[]
        for a,i in st.session_state.senders.items():
            r=st.session_state.classifications[a]
            rows.append({'E-Mail':a,'Domain':i['domain'],'Anzahl':i['count'],'Kategorie':r['category'],'Sicherheit':r['confidence'],'Begründung':r['reason']})
        df=pd.DataFrame(rows); st.dataframe(df.sort_values(['Kategorie','Anzahl'],ascending=[True,False]),use_container_width=True,hide_index=True)
        st.download_button('Klassifizierung als CSV herunterladen',df.to_csv(index=False,sep=';').encode('utf-8-sig'),'classifications.csv','text/csv')
        c1,c2=st.columns(2)
        with c1:
            if st.button('Zurück zu den Absendern'): st.session_state.step=2; st.rerun()
        with c2:
            if st.button('Weiter zu den Zielordnern',type='primary',use_container_width=True): st.session_state.step=4; st.rerun()

elif st.session_state.step==4:
    st.header('4. Thunderbird-Zielordner auswählen')
    folders=st.session_state.folders
    if not folders: st.error('Es wurden keine IMAP-Ordner gefunden.')
    else:
        selected={}
        for category in CATEGORIES:
            if category=='UNKLAR': continue
            current=st.session_state.category_to_folder.get(category, folders[0])
            idx=folders.index(current) if current in folders else 0
            selected[category]=st.selectbox(CATEGORY_LABELS.get(category,category),folders,index=idx,key=f'folder_{category}')
        st.session_state.category_to_folder=selected
        st.dataframe(pd.DataFrame([{'Kategorie':CATEGORY_LABELS.get(k,k),'IMAP-Ordner':v} for k,v in selected.items()]),use_container_width=True,hide_index=True)
        c1,c2=st.columns(2)
        with c1:
            if st.button('Zurück zur Klassifizierung'): st.session_state.step=3; st.rerun()
        with c2:
            if st.button('Weiter zur Regelvorschau',type='primary',use_container_width=True):
                st.session_state.rules=create_rule_preview(st.session_state.senders,st.session_state.classifications,selected,
                                                          st.session_state.imap_server,st.session_state.imap_username)
                st.session_state.step=5; st.rerun()

elif st.session_state.step==5:
    st.header('5. Regeln prüfen und Filterdatei erzeugen')
    rules_df=pd.DataFrame(st.session_state.rules)
    if rules_df.empty: st.warning('Es wurden keine Regeln erzeugt.')
    else:
        st.dataframe(rules_df[['email','category','confidence','count','folder','reason']],use_container_width=True,hide_index=True)
        st.download_button('Regelvorschau als CSV herunterladen',rules_df.to_csv(index=False,sep=';').encode('utf-8-sig'),'filter_preview.csv','text/csv')
        if st.session_state.filter_text is None:
            if st.button('Jetzt msgFilterRules.dat erzeugen',type='primary',use_container_width=True):
                st.session_state.filter_text=generate_filter_text(st.session_state.rules); st.rerun()
        else:
            st.success('Filterdatei wurde erzeugt.')
            st.text_area('Vorschau',st.session_state.filter_text,height=350)
            st.download_button('msgFilterRules.dat herunterladen',st.session_state.filter_text.encode('utf-8'),'msgFilterRules.dat','text/plain',type='primary',use_container_width=True)
            if st.button('Neue Analyse starten'): st.session_state.clear(); st.rerun()
