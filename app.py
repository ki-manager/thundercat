import pandas as pd
import streamlit as st

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    MAX_MAILS_PER_FOLDER,
    SUBJECTS_PER_SENDER,
    MIN_CONFIDENCE,
    FOLDER_MAP,
)
from imap_reader import scan_mail_headers
from ollama_client import test_ollama, classify_all
from rules import create_rule_preview, generate_filter_text

st.set_page_config(
    page_title="Thunderbird Ollama Mail Sorter",
    page_icon="📧",
    layout="wide",
)

st.title("📧 Thunderbird Ollama Mail Sorter")
st.caption(
    "IMAP-Header auslesen, lokal mit Ollama klassifizieren "
    "und Thunderbird-Filterregeln erzeugen."
)

defaults = {
    "step": 1,
    "senders": None,
    "classifications": None,
    "rules": None,
    "filter_text": None,
    "total_mails": 0,
    "folders": [],
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.header("Einstellungen")

    st.subheader("IMAP")
    imap_server = st.text_input("IMAP-Server", placeholder="imap.example.de")
    imap_port = st.number_input("IMAP-Port", min_value=1, max_value=65535, value=993)
    imap_username = st.text_input("Benutzername / E-Mail", placeholder="name@example.de")
    imap_password = st.text_input("Passwort", type="password")

    st.divider()
    st.subheader("Ollama")

    ollama_url = st.text_input("Ollama-URL", value=OLLAMA_URL)
    ollama_model = st.text_input("Ollama-Modell", value=OLLAMA_MODEL)

    st.divider()
    st.subheader("Analyse")

    max_mails = st.number_input(
        "Max. Mails pro Ordner",
        min_value=1,
        value=MAX_MAILS_PER_FOLDER,
        step=100,
    )
    subjects_per_sender = st.number_input(
        "Beispiel-Betreffzeilen pro Absender",
        min_value=1,
        max_value=20,
        value=SUBJECTS_PER_SENDER,
    )
    min_confidence = st.slider(
        "Mindest-Sicherheit",
        0.0,
        1.0,
        float(MIN_CONFIDENCE),
        0.05,
    )

st.info(f"Aktueller Schritt: {st.session_state.step} von 4")

if st.session_state.step == 1:
    st.header("1. IMAP-Zugang und Header auslesen")
    st.write(
        "Gelesen werden nur Absender, Domain und einige Betreffzeilen. "
        "Der Nachrichtentext wird nicht ausgewertet."
    )

    if st.button("IMAP testen und Header auslesen", type="primary", use_container_width=True):
        if not imap_server or not imap_username or not imap_password:
            st.error("Bitte IMAP-Server, Benutzername und Passwort eintragen.")
        else:
            progress = st.progress(0.0)
            status_box = st.empty()

            def update_progress(done, total):
                progress.progress(done / max(total, 1))

            def update_status(text):
                status_box.info(text)

            try:
                senders, total, folders = scan_mail_headers(
                    server=imap_server,
                    port=imap_port,
                    username=imap_username,
                    password=imap_password,
                    max_mails_per_folder=max_mails,
                    subjects_per_sender=subjects_per_sender,
                    progress_callback=update_progress,
                    status_callback=update_status,
                )
                st.session_state.senders = senders
                st.session_state.total_mails = total
                st.session_state.folders = folders
                progress.progress(1.0)
                status_box.success("IMAP-Auslesen abgeschlossen.")
                st.success(
                    f"{total} Mails analysiert, "
                    f"{len(senders)} eindeutige Absender gefunden."
                )
            except Exception as exc:
                st.error(f"IMAP-Fehler: {exc}")

    if st.session_state.senders:
        if st.button("Weiter zu den Absendern", type="primary"):
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    st.header("2. Gefundene Absender")

    rows = []
    for address, info in sorted(
        st.session_state.senders.items(),
        key=lambda item: -item[1]["count"],
    ):
        rows.append({
            "Name": info["name"],
            "E-Mail": address,
            "Domain": info["domain"],
            "Anzahl": info["count"],
            "Betreff-Beispiele": " | ".join(info["subjects"]),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "Absenderliste als CSV herunterladen",
        data=df.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="senders.csv",
        mime="text/csv",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Zurück"):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Weiter zur Ollama-Analyse", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

elif st.session_state.step == 3:
    st.header("3. Ollama-Klassifizierung und Regelvorschau")

    if st.session_state.classifications is None:
        if st.button("Ollama prüfen und Analyse starten", type="primary"):
            try:
                ollama_status = test_ollama(ollama_url, ollama_model)

                if not ollama_status["ok"]:
                    st.error(f"Modell '{ollama_model}' wurde nicht gefunden.")
                    if ollama_status["models"]:
                        st.write("Installierte Modelle:")
                        for model_name in ollama_status["models"]:
                            st.code(model_name)
                else:
                    progress = st.progress(0.0)
                    status_box = st.empty()

                    def update_progress(done, total):
                        progress.progress(done / max(total, 1))

                    def update_status(text):
                        status_box.info(text)

                    classifications = classify_all(
                        base_url=ollama_url,
                        model=ollama_model,
                        senders=st.session_state.senders,
                        min_confidence=min_confidence,
                        progress_callback=update_progress,
                        status_callback=update_status,
                    )
                    rules = create_rule_preview(
                        st.session_state.senders,
                        classifications,
                    )

                    st.session_state.classifications = classifications
                    st.session_state.rules = rules
                    progress.progress(1.0)
                    status_box.success("Ollama-Analyse abgeschlossen.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Ollama-Fehler: {exc}")

    else:
        classification_rows = []
        for address, info in st.session_state.senders.items():
            result = st.session_state.classifications[address]
            classification_rows.append({
                "E-Mail": address,
                "Domain": info["domain"],
                "Anzahl": info["count"],
                "Kategorie": result["category"],
                "Sicherheit": result["confidence"],
                "Begründung": result["reason"],
            })

        class_df = pd.DataFrame(classification_rows)
        st.subheader("Klassifizierung")
        st.dataframe(
            class_df.sort_values(["Kategorie", "Anzahl"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Geplante Thunderbird-Regeln")
        rules_df = pd.DataFrame(st.session_state.rules)

        if rules_df.empty:
            st.warning("Es wurden keine sicheren Regeln erzeugt.")
        else:
            st.dataframe(
                rules_df[["email", "category", "confidence", "count", "folder", "reason"]],
                use_container_width=True,
                hide_index=True,
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Zurück zu den Absendern"):
                st.session_state.step = 2
                st.rerun()
        with c2:
            if st.button("Weiter zur Filterdatei", type="primary", use_container_width=True):
                st.session_state.step = 4
                st.rerun()

elif st.session_state.step == 4:
    st.header("4. Thunderbird-Filterdatei erzeugen")

    st.warning(
        "Die Zielordner in config.py sind Platzhalter. "
        "Passe FOLDER_MAP an dein tatsächliches IMAP-/Thunderbird-Konto an."
    )

    folder_df = pd.DataFrame([
        {"Kategorie": category, "Zielordner": folder}
        for category, folder in FOLDER_MAP.items()
    ])
    st.dataframe(folder_df, use_container_width=True, hide_index=True)

    if st.session_state.filter_text is None:
        if st.button("Jetzt msgFilterRules.dat erzeugen", type="primary", use_container_width=True):
            st.session_state.filter_text = generate_filter_text(st.session_state.rules)
            st.rerun()
    else:
        st.success("Filterdatei wurde erzeugt.")
        st.text_area("Vorschau", st.session_state.filter_text, height=350)

        st.download_button(
            "msgFilterRules.dat herunterladen",
            data=st.session_state.filter_text.encode("utf-8"),
            file_name="msgFilterRules.dat",
            mime="text/plain",
            type="primary",
            use_container_width=True,
        )

        if st.button("Neue Analyse starten"):
            st.session_state.clear()
            st.rerun()
