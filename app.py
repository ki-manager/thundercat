import time

import pandas as pd
import streamlit as st

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    MAX_MAILS_PER_FOLDER,
    SUBJECTS_PER_SENDER,
    MIN_CONFIDENCE,
    BATCH_SIZE,
    CATEGORIES,
    CATEGORY_LABELS,
)
from imap_reader import scan_mail_headers
from ollama_client import (
    test_ollama,
    classify_all,
)
from rules import (
    create_rule_preview,
    generate_filter_text,
)


st.set_page_config(
    page_title="ThunderCat",
    page_icon="assets/thundercat_icon.png",
    layout="wide",
)

col_logo, col_title = st.columns(
    [0.4, 6],
    vertical_alignment="center",
)


with col_logo:
    st.image(
        "assets/thundercat_logo.png",
        width=64,
    )

with col_title:
    st.title("ThunderCat")
    st.caption(
        "Intelligente E-Mail-Analyse mit IMAP, "
        "Ollama und Thunderbird."
    )

defaults = {
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
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


with st.sidebar:
    st.header("Einstellungen")

    st.subheader("IMAP")

    imap_server = st.text_input(
        "IMAP-Server",
        value=st.session_state.imap_server,
        placeholder="imap.example.de",
    )

    imap_port = st.number_input(
        "IMAP-Port",
        min_value=1,
        max_value=65535,
        value=int(
            st.session_state.imap_port
        ),
    )

    imap_username = st.text_input(
        "Benutzername / E-Mail",
        value=st.session_state.imap_username,
        placeholder="name@example.de",
    )

    imap_password = st.text_input(
        "Passwort",
        type="password",
    )

    st.divider()

    st.subheader("Ollama")

    ollama_url = st.text_input(
        "Ollama-URL",
        value=OLLAMA_URL,
    )

    ollama_model = st.text_input(
        "Ollama-Modell",
        value=OLLAMA_MODEL,
    )

    batch_size = st.number_input(
        "Start-Batch-Größe",
        min_value=1,
        max_value=100,
        value=BATCH_SIZE,
        step=1,
        help=(
            "Bei Timeout verkleinert "
            "das Programm den Batch "
            "automatisch."
        ),
    )

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

    force_reclassify = st.checkbox(
        "Cache ignorieren und alles neu klassifizieren",
        value=False,
    )


st.info(
    f"Aktueller Schritt: "
    f"{st.session_state.step} "
    f"von 5"
)


if st.session_state.step == 1:
    st.header(
        "1. IMAP-Zugang und Header auslesen"
    )

    st.write(
        "Es werden nur Absender, Domain und einige "
        "Betreffzeilen gelesen."
    )

    if st.button(
        "IMAP testen und Header auslesen",
        type="primary",
        use_container_width=True,
    ):
        if (
            not imap_server
            or not imap_username
            or not imap_password
        ):
            st.error(
                "Bitte IMAP-Server, Benutzername "
                "und Passwort eintragen."
            )

        else:
            progress = st.progress(0.0)
            status_box = st.empty()

            def update_progress(done, total):
                progress.progress(
                    done / max(total, 1)
                )

            def update_status(text):
                status_box.info(text)

            try:
                senders, total, folders = (
                    scan_mail_headers(
                        server=imap_server,
                        port=imap_port,
                        username=imap_username,
                        password=imap_password,
                        max_mails_per_folder=max_mails,
                        subjects_per_sender=subjects_per_sender,
                        progress_callback=update_progress,
                        status_callback=update_status,
                    )
                )

                st.session_state.senders = senders
                st.session_state.total_mails = total
                st.session_state.folders = folders
                st.session_state.imap_server = imap_server
                st.session_state.imap_port = int(imap_port)
                st.session_state.imap_username = imap_username

                progress.progress(1.0)

                status_box.success(
                    "IMAP-Auslesen abgeschlossen."
                )

                st.success(
                    f"{total} Mails analysiert, "
                    f"{len(senders)} eindeutige "
                    f"Absender gefunden."
                )

            except Exception as exc:
                st.error(
                    f"IMAP-Fehler: {exc}"
                )

    if st.session_state.senders:
        if st.button(
            "Weiter zu den Absendern",
            type="primary",
        ):
            st.session_state.step = 2
            st.rerun()


elif st.session_state.step == 2:
    st.header(
        "2. Gefundene Absender"
    )

    rows = []

    for address, info in sorted(
        st.session_state.senders.items(),
        key=lambda item:
        -item[1]["count"],
    ):
        rows.append({
            "Name": info["name"],
            "E-Mail": address,
            "Domain": info["domain"],
            "Anzahl": info["count"],
            "Betreff-Beispiele": " | ".join(
                info["subjects"]
            ),
        })

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Absenderliste als CSV herunterladen",
        data=df.to_csv(
            index=False,
            sep=";",
        ).encode(
            "utf-8-sig"
        ),
        file_name="senders.csv",
        mime="text/csv",
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("Zurück"):
            st.session_state.step = 1
            st.rerun()

    with c2:
        if st.button(
            "Weiter zur Ollama-Analyse",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.step = 3
            st.rerun()


elif st.session_state.step == 3:
    st.header(
        "3. Ollama-Klassifizierung"
    )

    st.caption(
        "Bei Timeout wird ein Batch automatisch "
        "halbiert, bis notfalls einzelne Absender "
        "verarbeitet werden."
    )

    if st.session_state.classifications is None:
        if st.button(
            "Ollama prüfen und Analyse starten",
            type="primary",
        ):
            try:
                ollama_status = test_ollama(
                    ollama_url,
                    ollama_model,
                )

                if not ollama_status["ok"]:
                    st.error(
                        f"Modell '{ollama_model}' "
                        f"wurde nicht gefunden."
                    )

                    if ollama_status["models"]:
                        st.write(
                            "Installierte Modelle:"
                        )

                        for model_name in ollama_status["models"]:
                            st.code(model_name)

                else:
                    progress = st.progress(0.0)
                    status_box = st.empty()
                    stats_box = st.empty()
                    start_time = time.time()

                    def update_progress(
                        done,
                        total,
                        cached,
                        total_new,
                    ):
                        progress.progress(
                            done / max(total, 1)
                        )

                        elapsed = (
                            time.time()
                            - start_time
                        )

                        stats_box.info(
                            f"{done}/{total} Absender | "
                            f"Cache: {cached} | "
                            f"Neu: {total_new} | "
                            f"Laufzeit: {elapsed:.1f}s"
                        )

                    def update_status(text):
                        status_box.info(text)

                    classifications, stats = classify_all(
                        base_url=ollama_url,
                        model=ollama_model,
                        senders=st.session_state.senders,
                        min_confidence=min_confidence,
                        batch_size=int(batch_size),
                        progress_callback=update_progress,
                        status_callback=update_status,
                        force_reclassify=force_reclassify,
                    )

                    st.session_state.classifications = classifications
                    st.session_state.stats = stats

                    progress.progress(1.0)

                    status_box.success(
                        "Ollama-Analyse abgeschlossen."
                    )

                    st.rerun()

            except Exception as exc:
                st.error(
                    f"Ollama-Fehler: {exc}"
                )

    else:
        if st.session_state.stats:
            stats = st.session_state.stats

            st.success(
                f"{stats['total']} Absender ausgewertet: "
                f"{stats['cached']} aus Cache, "
                f"{stats['new']} neu mit Ollama."
            )

        rows = []

        for address, info in (
            st.session_state.senders.items()
        ):
            result = st.session_state.classifications[
                address
            ]

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
            class_df.sort_values(
                [
                    "Kategorie",
                    "Anzahl",
                ],
                ascending=[
                    True,
                    False,
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Klassifizierung als CSV herunterladen",
            data=class_df.to_csv(
                index=False,
                sep=";",
            ).encode(
                "utf-8-sig"
            ),
            file_name="classifications.csv",
            mime="text/csv",
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "Zurück zu den Absendern"
            ):
                st.session_state.step = 2
                st.rerun()

        with c2:
            if st.button(
                "Weiter zu den Zielordnern",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.step = 4
                st.rerun()


elif st.session_state.step == 4:
    st.header(
        "4. Thunderbird-Zielordner auswählen"
    )

    st.write(
        "Wähle für jede Kategorie einen "
        "vorhandenen IMAP-Ordner."
    )

    folders = st.session_state.folders

    if not folders:
        st.error(
            "Es wurden keine IMAP-Ordner gefunden."
        )

    else:
        selected = {}

        for category in CATEGORIES:
            if category == "UNKLAR":
                continue

            label = CATEGORY_LABELS.get(
                category,
                category,
            )

            current = (
                st.session_state.category_to_folder
                .get(
                    category,
                    folders[0],
                )
            )

            default_index = (
                folders.index(current)
                if current in folders
                else 0
            )

            selected[category] = st.selectbox(
                label,
                options=folders,
                index=default_index,
                key=f"folder_{category}",
            )

        st.session_state.category_to_folder = selected

        mapping_df = pd.DataFrame([
            {
                "Kategorie": CATEGORY_LABELS.get(
                    category,
                    category,
                ),
                "IMAP-Ordner": folder,
            }
            for category, folder
            in selected.items()
        ])

        st.dataframe(
            mapping_df,
            use_container_width=True,
            hide_index=True,
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "Zurück zur Klassifizierung"
            ):
                st.session_state.step = 3
                st.rerun()

        with c2:
            if st.button(
                "Weiter zur Regelvorschau",
                type="primary",
                use_container_width=True,
            ):
                rules = create_rule_preview(
                    senders=st.session_state.senders,
                    classifications=st.session_state.classifications,
                    category_to_folder=st.session_state.category_to_folder,
                    server=st.session_state.imap_server,
                    username=st.session_state.imap_username,
                )

                st.session_state.rules = rules
                st.session_state.step = 5
                st.rerun()


elif st.session_state.step == 5:
    st.header(
        "5. Regeln prüfen und Filterdatei erzeugen"
    )

    rules_df = pd.DataFrame(
        st.session_state.rules
    )

    if rules_df.empty:
        st.warning(
            "Es wurden keine Regeln erzeugt."
        )

    else:
        st.dataframe(
            rules_df[
                [
                    "email",
                    "category",
                    "confidence",
                    "count",
                    "folder",
                    "reason",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Regelvorschau als CSV herunterladen",
            data=rules_df.to_csv(
                index=False,
                sep=";",
            ).encode(
                "utf-8-sig"
            ),
            file_name="filter_preview.csv",
            mime="text/csv",
        )

        if st.session_state.filter_text is None:
            if st.button(
                "Jetzt msgFilterRules.dat erzeugen",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.filter_text = (
                    generate_filter_text(
                        st.session_state.rules
                    )
                )

                st.rerun()

        else:
            st.success(
                "Filterdatei wurde erzeugt."
            )

            st.text_area(
                "Vorschau",
                st.session_state.filter_text,
                height=350,
            )

            st.download_button(
                "msgFilterRules.dat herunterladen",
                data=(
                    st.session_state
                    .filter_text
                    .encode(
                        "utf-8"
                    )
                ),
                file_name="msgFilterRules.dat",
                mime="text/plain",
                type="primary",
                use_container_width=True,
            )

            if st.button(
                "Neue Analyse starten"
            ):
                st.session_state.clear()
                st.rerun()
