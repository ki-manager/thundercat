import time
import pandas as pd
import streamlit as st

from config import (
    DEFAULT_PROVIDER, OPENAI_MODEL, GEMINI_MODEL, OLLAMA_URL, OLLAMA_MODEL,
    MAX_MAILS_PER_FOLDER, SUBJECTS_PER_SENDER, MIN_CONFIDENCE,
    BATCH_SIZE_OPENAI, BATCH_SIZE_GEMINI, BATCH_SIZE_OLLAMA,
    CATEGORIES, CATEGORY_LABELS,
)
from imap_reader import scan_mail_headers, refresh_folder_structure
from provider_client import test_provider
from folder_utils import auto_map_categories
from classifier import classify_all
from rules import create_rule_preview, generate_filter_text

st.set_page_config(
    page_title="ThunderCat",
    page_icon="assets/thundercat_icon.png",
    layout="wide",
)

col_logo, col_title = st.columns([0.35, 6], vertical_alignment="center")
with col_logo:
    st.image("assets/thundercat_logo.png", width=54)
with col_title:
    st.title("ThunderCat")
    st.caption("Intelligente E-Mail-Analyse mit IMAP, OpenAI, Gemini oder Ollama.")

DEFAULTS = {
    "step": 1,
    "senders": None,
    "classifications": None,
    "rules": None,
    "filter_text": None,
    "total_mails": 0,
    "folders": [],
    "category_to_folder": {},
    "imap_server": "",
    "imap_port": 993,
    "imap_username": "",
    "stats": None,
    "provider": DEFAULT_PROVIDER,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.header("Einstellungen")

    st.subheader("IMAP")
    imap_server = st.text_input("IMAP-Server", value=st.session_state.imap_server, placeholder="imap.example.de")
    imap_port = st.number_input("IMAP-Port", min_value=1, max_value=65535, value=int(st.session_state.imap_port))
    imap_username = st.text_input("Benutzername / E-Mail", value=st.session_state.imap_username, placeholder="name@example.de")
    imap_password = st.text_input("Passwort", type="password")

    st.divider()
    st.subheader("KI-Provider")
    providers = ["OpenAI", "Gemini", "Ollama"]
    provider = st.selectbox(
        "Provider",
        providers,
        index=providers.index(st.session_state.provider if st.session_state.provider in providers else "OpenAI"),
    )
    st.session_state.provider = provider

    if provider == "OpenAI":
        api_key = st.text_input("OpenAI API-Key", type="password")
        model = st.text_input("OpenAI-Modell", value=OPENAI_MODEL)
        batch_size = st.number_input("Batch-Größe", 1, 100, BATCH_SIZE_OPENAI)
        ollama_url = None
        st.warning("Absender, Domain und Beispiel-Betreffzeilen werden zur Klassifizierung an OpenAI übertragen.")
    elif provider == "Gemini":
        api_key = st.text_input("Gemini API-Key", type="password")
        model = st.text_input("Gemini-Modell", value=GEMINI_MODEL)
        batch_size = st.number_input("Batch-Größe", 1, 100, BATCH_SIZE_GEMINI)
        ollama_url = None
        st.warning("Absender, Domain und Beispiel-Betreffzeilen werden zur Klassifizierung an Google übertragen.")
    else:
        api_key = None
        ollama_url = st.text_input("Ollama-URL", value=OLLAMA_URL)
        model = st.text_input("Ollama-Modell", value=OLLAMA_MODEL)
        batch_size = st.number_input("Start-Batch-Größe", 1, 100, BATCH_SIZE_OLLAMA)
        st.success("Ollama läuft lokal; die Klassifizierungsdaten verlassen den Rechner nicht.")

    st.divider()
    st.subheader("Analyse")
    max_mails = st.number_input("Max. Mails pro Ordner", min_value=1, value=MAX_MAILS_PER_FOLDER, step=100)
    subjects_per_sender = st.number_input("Beispiel-Betreffzeilen pro Absender", 1, 20, SUBJECTS_PER_SENDER)
    min_confidence = st.slider("Mindest-Sicherheit", 0.0, 1.0, float(MIN_CONFIDENCE), 0.05)
    force_reclassify = st.checkbox("Cache ignorieren und alles neu klassifizieren", value=False)

st.info(f"Aktueller Schritt: {st.session_state.step} von 5")

if st.session_state.step == 1:
    st.header("1. IMAP-Zugang und Header auslesen")
    st.write("ThunderCat liest nur Absender, Domain und einige Betreffzeilen. Der vollständige Nachrichtentext wird nicht gelesen.")

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
                st.session_state.imap_server = imap_server
                st.session_state.imap_port = int(imap_port)
                st.session_state.imap_username = imap_username
                progress.progress(1.0)
                status_box.success("IMAP-Auslesen abgeschlossen.")
                st.success(f"{total} Mails analysiert, {len(senders)} eindeutige Absender gefunden.")
            except Exception as exc:
                st.error(f"IMAP-Fehler: {exc}")

    if st.session_state.senders:
        if st.button("Weiter zu den Absendern", type="primary"):
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    st.header("2. Gefundene Absender")
    rows = []
    for address, info in sorted(st.session_state.senders.items(), key=lambda item: -item[1]["count"]):
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
        if st.button("Weiter zur KI-Analyse", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()

elif st.session_state.step == 3:
    st.header("3. KI-Klassifizierung")
    st.write(f"Provider: **{provider}**  \nModell: **{model}**")

    if st.session_state.classifications is None:
        if st.button("Provider prüfen und Analyse starten", type="primary"):
            try:
                provider_status = test_provider(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    ollama_url=ollama_url,
                )

                if not provider_status["ok"]:
                    st.error(provider_status["message"])
                    for model_name in provider_status.get("models", []):
                        st.code(model_name)
                else:
                    st.success(provider_status["message"])
                    progress = st.progress(0.0)
                    status_box = st.empty()
                    stats_box = st.empty()
                    start_time = time.time()

                    def update_progress(done, total, cached, total_new):
                        progress.progress(done / max(total, 1))
                        elapsed = time.time() - start_time
                        stats_box.info(
                            f"{done}/{total} Absender | Cache: {cached} | "
                            f"Neu: {total_new} | Laufzeit: {elapsed:.1f}s"
                        )

                    def update_status(text):
                        status_box.info(text)

                    classifications, stats = classify_all(
                        provider=provider,
                        model=model,
                        senders=st.session_state.senders,
                        min_confidence=min_confidence,
                        batch_size=int(batch_size),
                        api_key=api_key,
                        ollama_url=ollama_url,
                        progress_callback=update_progress,
                        status_callback=update_status,
                        force_reclassify=force_reclassify,
                    )
                    st.session_state.classifications = classifications
                    st.session_state.stats = stats
                    progress.progress(1.0)
                    status_box.success("KI-Analyse abgeschlossen.")
                    st.rerun()
            except Exception as exc:
                st.error(f"KI-Fehler: {exc}")
    else:
        if st.session_state.stats:
            stats = st.session_state.stats
            st.success(
                f"{stats['total']} Absender ausgewertet: "
                f"{stats['cached']} aus Cache, {stats['new']} neu klassifiziert."
            )

        rows = []
        for address, info in st.session_state.senders.items():
            result = st.session_state.classifications[address]
            rows.append({
                "E-Mail": address,
                "Domain": info["domain"],
                "Anzahl": info["count"],
                "Kategorie": result["category"],
                "Sicherheit": result["confidence"],
                "Begründung": result["reason"],
            })
        class_df = pd.DataFrame(rows)
        st.dataframe(
            class_df.sort_values(["Kategorie", "Anzahl"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Klassifizierung als CSV herunterladen",
            data=class_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name="classifications.csv",
            mime="text/csv",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Zurück zu den Absendern"):
                st.session_state.step = 2
                st.rerun()
        with c2:
            if st.button("Weiter zu den Zielordnern", type="primary", use_container_width=True):
                st.session_state.step = 4
                st.rerun()

elif st.session_state.step == 4:
    st.header("4. Thunderbird-Zielordner prüfen")

    st.write(
        "Die Kategorienamen entsprechen jetzt direkt den gewünschten "
        "Thunderbird-Ordnernamen. ThunderCat versucht deshalb, vorhandene "
        "IMAP-Ordner automatisch zuzuordnen."
    )

    col_refresh, col_info = st.columns([1.4, 3])

    with col_refresh:
        refresh_clicked = st.button(
            "🔄 IMAP-Struktur erneut prüfen",
            type="primary",
            use_container_width=True,
        )

    with col_info:
        st.caption(
            "Die Ordnerliste wird direkt vom IMAP-Server neu geladen "
            "und danach automatisch erneut zugeordnet."
        )

    if refresh_clicked:
        if not imap_password:
            st.error(
                "Bitte links in der Seitenleiste das IMAP-Passwort "
                "erneut eingeben."
            )
        else:
            try:
                with st.spinner("Lese aktuelle IMAP-Ordnerstruktur …"):
                    refreshed_folders = refresh_folder_structure(
                        server=st.session_state.imap_server or imap_server,
                        port=st.session_state.imap_port or imap_port,
                        username=st.session_state.imap_username or imap_username,
                        password=imap_password,
                    )

                st.session_state.folders = refreshed_folders
                st.session_state.category_to_folder = {}

                # alte Selectbox-Werte entfernen, damit die automatische
                # Zuordnung sichtbar wird
                for category in CATEGORIES:
                    st.session_state.pop(f"folder_{category}", None)

                st.success(
                    f"IMAP-Struktur aktualisiert: "
                    f"{len(refreshed_folders)} Ordner gefunden."
                )
                st.rerun()

            except Exception as exc:
                st.error(f"IMAP-Fehler beim erneuten Prüfen: {exc}")

    folders = st.session_state.folders or []

    if not folders:
        st.error(
            "Es wurden keine IMAP-Ordner gefunden. "
            "Bitte die IMAP-Struktur erneut prüfen."
        )

    else:
        auto_mapping, missing, ambiguous = auto_map_categories(
            CATEGORIES,
            folders,
        )

        # Bereits manuell gewählte Werte haben Vorrang.
        current_mapping = dict(st.session_state.category_to_folder or {})

        for category, folder in auto_mapping.items():
            if not current_mapping.get(category) and folder:
                current_mapping[category] = folder

        st.subheader("Automatischer Abgleich")

        found_count = sum(
            1
            for category in CATEGORIES
            if category != "Unklar"
            and current_mapping.get(category) in folders
        )

        metric1, metric2, metric3 = st.columns(3)
        metric1.metric("IMAP-Ordner", len(folders))
        metric2.metric("Automatisch zugeordnet", found_count)
        metric3.metric("Fehlende Kategorien", len(missing) + len(ambiguous))

        if missing:
            st.warning(
                "Diese gewünschten Ordner fehlen auf dem IMAP-Server:\n\n"
                + "\n".join(f"• {name}" for name in missing)
            )

        if ambiguous:
            details = []
            for category, matches in ambiguous.items():
                details.append(
                    f"• {category}: " + ", ".join(matches)
                )
            st.warning(
                "Für diese Kategorien wurden mehrere passende Ordner gefunden. "
                "Bitte manuell auswählen:\n\n"
                + "\n".join(details)
            )

        if not missing and not ambiguous:
            st.success(
                "Alle Kategorien konnten einem vorhandenen IMAP-Ordner "
                "automatisch zugeordnet werden."
            )

        with st.expander("Aktuelle IMAP-Ordnerstruktur anzeigen"):
            folder_df = pd.DataFrame(
                {"IMAP-Ordner": folders}
            )
            st.dataframe(
                folder_df,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("Zuordnung")

        selected = {}

        # Leerer Eintrag erlaubt, fehlende Ordner sichtbar zu lassen.
        options = ["— nicht zugeordnet —"] + folders

        for category in CATEGORIES:
            if category == "Unklar":
                continue

            suggested = current_mapping.get(category)

            if suggested in folders:
                default_index = options.index(suggested)
            else:
                default_index = 0

            selected_value = st.selectbox(
                category,
                options=options,
                index=default_index,
                key=f"folder_{category}",
                help=(
                    "Kategorie und Zielordner sind idealerweise identisch. "
                    "Bei verschachtelten Ordnern wird auch der letzte "
                    "Ordnername automatisch erkannt."
                ),
            )

            selected[category] = (
                None
                if selected_value == "— nicht zugeordnet —"
                else selected_value
            )

        st.session_state.category_to_folder = selected

        final_missing = [
            category
            for category, folder in selected.items()
            if not folder
        ]

        mapping_df = pd.DataFrame([
            {
                "Kategorie / gewünschter Ordner": category,
                "Zugewiesener IMAP-Ordner": folder or "FEHLT",
                "Status": "OK" if folder else "FEHLT",
            }
            for category, folder in selected.items()
        ])

        st.dataframe(
            mapping_df,
            use_container_width=True,
            hide_index=True,
        )

        if final_missing:
            st.error(
                "Noch nicht zugeordnet: "
                + ", ".join(final_missing)
                + ". Lege diese Ordner in Thunderbird/auf dem IMAP-Server "
                  "an und klicke danach auf „IMAP-Struktur erneut prüfen“."
            )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Zurück zur Klassifizierung"):
                st.session_state.step = 3
                st.rerun()

        with c2:
            if st.button(
                "Weiter zur Regelvorschau",
                type="primary",
                use_container_width=True,
                disabled=bool(final_missing),
            ):
                st.session_state.rules = create_rule_preview(
                    senders=st.session_state.senders,
                    classifications=st.session_state.classifications,
                    category_to_folder=st.session_state.category_to_folder,
                    server=st.session_state.imap_server,
                    username=st.session_state.imap_username,
                )
                st.session_state.step = 5
                st.rerun()


elif st.session_state.step == 5:
    st.header("5. Regeln prüfen und Filterdatei erzeugen")
    rules_df = pd.DataFrame(st.session_state.rules)

    if rules_df.empty:
        st.warning("Es wurden keine Regeln erzeugt.")
    else:
        st.dataframe(
            rules_df[["email", "category", "confidence", "count", "folder", "reason"]],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Regelvorschau als CSV herunterladen",
            data=rules_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name="filter_preview.csv",
            mime="text/csv",
        )

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
