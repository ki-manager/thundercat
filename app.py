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


# ---------------------------------------------------------
# Hilfsfunktionen für ChatGPT-CSV
# ---------------------------------------------------------

def build_chatgpt_export_df(senders):
    rows = []

    for address, info in sorted(
        senders.items(),
        key=lambda item: -item[1]["count"],
    ):
        rows.append({
            "Name": info.get("name", ""),
            "E-Mail": address,
            "Domain": info.get("domain", ""),
            "Anzahl": info.get("count", 0),
            "Betreff-Beispiele": " | ".join(
                info.get("subjects", [])
            ),
            "Kategorie": "",
            "Sicherheit": "",
            "Begründung": "",
        })

    return pd.DataFrame(rows)


def import_chatgpt_classifications(
    imported_df,
    senders,
    categories,
):
    required_columns = [
        "E-Mail",
        "Kategorie",
        "Sicherheit",
        "Begründung",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in imported_df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Fehlende Spalten: " + ", ".join(missing_columns)
        )

    original_addresses = {
        address.lower().strip()
        for address in senders.keys()
    }

    classifications = {}
    invalid_categories = []
    duplicate_addresses = []
    seen = set()

    for _, row in imported_df.iterrows():
        address = str(row["E-Mail"]).lower().strip()

        if not address or address == "nan":
            continue

        if address in seen:
            duplicate_addresses.append(address)
            continue

        seen.add(address)

        if address not in original_addresses:
            continue

        category = str(row["Kategorie"]).strip()

        if category not in categories:
            invalid_categories.append((address, category))
            category = "Unklar"

        try:
            confidence = float(row["Sicherheit"])
        except Exception:
            confidence = 0.0

        confidence = max(0.0, min(1.0, confidence))

        reason = str(row["Begründung"]).strip()
        if reason == "nan":
            reason = ""

        classifications[address] = {
            "category": category,
            "confidence": confidence,
            "reason": reason,
        }

    missing_addresses = sorted(
        original_addresses - set(classifications.keys())
    )

    return {
        "classifications": classifications,
        "missing_addresses": missing_addresses,
        "invalid_categories": invalid_categories,
        "duplicate_addresses": duplicate_addresses,
    }

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
    "provider": "ChatGPT",
    "api_log": [],
    "live_results": {},
    "classification_method": "Direkt per KI-API",
    "csv_import_preview": None,
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
    providers = ["ChatGPT", "OpenAI", "Gemini", "Ollama"]
    provider = st.selectbox(
        "Provider",
        providers,
        index=providers.index(st.session_state.provider if st.session_state.provider in providers else "ChatGPT"),
    )
    st.session_state.provider = provider

    if provider == "ChatGPT":
        api_key = None
        model = None
        batch_size = None
        ollama_url = None

    elif provider == "OpenAI":
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

    classification_method = (
        "CSV über ChatGPT klassifizieren"
        if provider == "ChatGPT"
        else "Direkt per KI-API"
    )

    st.session_state.classification_method = classification_method

    # =====================================================
    # VARIANTE A: DIREKT PER API
    # =====================================================

    if classification_method == "Direkt per KI-API":

        st.write(
            f"Provider: **{provider}**  \n"
            f"Modell: **{model}**"
        )

        st.caption(
            "Beim Start prüft ThunderCat automatisch "
            "die Verbindung zum gewählten Provider und "
            "beginnt anschließend direkt mit der "
            "Klassifizierung."
        )

        if st.session_state.classifications is None:

            if st.button(
                "Klassifizierung starten",
                type="primary",
                use_container_width=True,
            ):

                try:

                    connection_box = st.empty()
                    status_box = st.empty()

                    connection_box.info(
                        f"Prüfe Verbindung zu {provider} …"
                    )

                    provider_status = test_provider(
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        ollama_url=ollama_url,
                    )

                    if not provider_status["ok"]:

                        connection_box.error(
                            provider_status["message"]
                        )

                        if provider_status.get("models"):

                            st.write(
                                "Verfügbare lokale Modelle:"
                            )

                            for model_name in (
                                provider_status["models"]
                            ):
                                st.code(model_name)

                    else:

                        connection_box.success(
                            provider_status["message"]
                        )

                        status_box.info(
                            "Klassifizierung wird gestartet …"
                        )

                        progress = st.progress(0.0)
                        stats_box = st.empty()
                        live_title = st.empty()
                        live_table = st.empty()
                        log_box = st.empty()

                        start_time = time.time()

                        st.session_state.api_log = []
                        st.session_state.live_results = {}

                        live_title.subheader(
                            "Aktuelle Klassifizierungsergebnisse"
                        )

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

                        def update_detail(entry):

                            st.session_state.api_log.append(
                                entry
                            )

                            lines = []

                            for i, item in enumerate(
                                st.session_state.api_log[-8:],
                                start=max(
                                    1,
                                    len(
                                        st.session_state.api_log
                                    ) - 7,
                                ),
                            ):

                                if item["ok"]:

                                    line = (
                                        f"✓ Aufruf {i}: "
                                        f"{item['size']} Absender, "
                                        f"{item['elapsed']:.1f}s"
                                    )

                                    if item.get("request_id"):
                                        line += (
                                            f", Request-ID "
                                            f"{item['request_id']}"
                                        )

                                else:

                                    line = (
                                        f"✗ Aufruf {i}: "
                                        f"{item['size']} Absender, "
                                        f"{item['elapsed']:.1f}s – "
                                        f"{item['error']}"
                                    )

                                lines.append(line)

                            log_box.code(
                                "\n".join(lines)
                            )

                        def update_live_result(
                            address,
                            result,
                            done,
                            total,
                        ):

                            st.session_state.live_results[
                                address
                            ] = result

                            live_rows = []

                            for (
                                live_address,
                                live_result,
                            ) in (
                                st.session_state
                                .live_results
                                .items()
                            ):

                                sender_info = (
                                    st.session_state
                                    .senders
                                    .get(
                                        live_address,
                                        {},
                                    )
                                )

                                live_rows.append({
                                    "E-Mail":
                                        live_address,
                                    "Domain":
                                        sender_info.get(
                                            "domain",
                                            "",
                                        ),
                                    "Anzahl":
                                        sender_info.get(
                                            "count",
                                            0,
                                        ),
                                    "Kategorie":
                                        live_result.get(
                                            "category",
                                            "Unklar",
                                        ),
                                    "Sicherheit":
                                        live_result.get(
                                            "confidence",
                                            0.0,
                                        ),
                                    "Begründung":
                                        live_result.get(
                                            "reason",
                                            "",
                                        ),
                                })

                            live_df = pd.DataFrame(
                                live_rows
                            )

                            if not live_df.empty:

                                live_df = (
                                    live_df
                                    .sort_values(
                                        [
                                            "Kategorie",
                                            "Anzahl",
                                        ],
                                        ascending=[
                                            True,
                                            False,
                                        ],
                                    )
                                )

                            live_table.dataframe(
                                live_df,
                                use_container_width=True,
                                hide_index=True,
                            )

                            live_title.subheader(
                                "Aktuelle "
                                "Klassifizierungsergebnisse "
                                f"({done}/{total})"
                            )

                        classifications, stats = (
                            classify_all(
                                provider=provider,
                                model=model,
                                senders=(
                                    st.session_state
                                    .senders
                                ),
                                min_confidence=(
                                    min_confidence
                                ),
                                batch_size=int(
                                    batch_size
                                ),
                                api_key=api_key,
                                ollama_url=ollama_url,
                                progress_callback=(
                                    update_progress
                                ),
                                status_callback=(
                                    update_status
                                ),
                                detail_callback=(
                                    update_detail
                                ),
                                result_callback=(
                                    update_live_result
                                ),
                                force_reclassify=(
                                    force_reclassify
                                ),
                            )
                        )

                        st.session_state.classifications = (
                            classifications
                        )

                        st.session_state.stats = (
                            stats
                        )

                        progress.progress(1.0)

                        status_box.success(
                            "KI-Analyse abgeschlossen."
                        )

                        time.sleep(0.3)

                        st.rerun()

                except Exception as exc:

                    st.error(
                        f"KI-Fehler: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

    # =====================================================
    # VARIANTE B: CSV ÜBER CHATGPT
    # =====================================================

    else:

        st.subheader(
            "CSV über ChatGPT klassifizieren"
        )

        st.write(
            "Diese Variante benötigt keine direkte "
            "OpenAI-API-Verbindung in ThunderCat. "
            "Du lädst die Absenderliste herunter, "
            "lässt sie in ChatGPT ergänzen und "
            "importierst sie anschließend wieder."
        )

        export_df = build_chatgpt_export_df(
            st.session_state.senders
        )

        st.markdown(
            "#### 1. CSV herunterladen"
        )

        st.download_button(
            "CSV für ChatGPT herunterladen",
            data=export_df.to_csv(
                index=False,
                sep=";",
            ).encode(
                "utf-8-sig"
            ),
            file_name=(
                "thundercat_chatgpt_"
                "klassifizierung.csv"
            ),
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

        st.dataframe(
            export_df.head(20),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            f"{len(export_df)} Absender werden exportiert."
        )

        st.markdown(
            "#### 2. CSV in ChatGPT hochladen"
        )

        chatgpt_prompt = """
Analysiere die hochgeladene CSV-Datei mit E-Mail-Absendern.

Ergänze für jede Zeile ausschließlich die bereits vorhandenen Spalten:

Kategorie
Sicherheit
Begründung

Verwende für Kategorie ausschließlich exakt einen der folgenden Werte:

Persönlich
Arbeit
Bewerbungen
Recruiter
Jobportale
Rechnungen
Banken
Versicherungen
Behörden
Schule & Bildung
Termine
Konto & Sicherheit
Bestellungen
Versand
Shops
Newsletter
Werbung
Verträge & Service
System
Kundenservice
Spam
Unklar

Nutze für die Klassifizierung insbesondere:
- Name
- E-Mail
- Domain
- Betreff-Beispiele

Regeln:
- Persönlich nur für echte private Kommunikation.
- Spam nur für eindeutig unerwünschte, betrügerische oder verdächtige Massenmails.
- Werbung ist nicht automatisch Spam.
- Sicherheits- und Login-Mails gehören zu Konto & Sicherheit.
- Behörden wie ELSTER, Stadt, Landkreis oder öffentliche Stellen gehören zu Behörden.
- Schule, IServ, Lernplattformen und Weiterbildung gehören zu Schule & Bildung.
- Sicherheit muss als Dezimalzahl zwischen 0 und 1 angegeben werden.
- Ändere keine bestehenden Werte in den anderen Spalten.
- Entferne keine Zeilen.
- Füge keine zusätzlichen Zeilen hinzu.

Gib mir anschließend die vollständige bearbeitete CSV-Datei mit Semikolon als Trennzeichen zum Herunterladen zurück.
""".strip()

        st.code(
            chatgpt_prompt,
            language=None,
        )

        st.markdown(
            "#### 3. Bearbeitete CSV wieder hochladen"
        )

        uploaded_file = st.file_uploader(
            "Von ChatGPT ergänzte CSV auswählen",
            type=["csv"],
            key="chatgpt_classification_upload",
        )

        if uploaded_file is not None:

            try:

                imported_df = pd.read_csv(
                    uploaded_file,
                    sep=";",
                    dtype=str,
                    keep_default_na=False,
                )

                result = (
                    import_chatgpt_classifications(
                        imported_df=imported_df,
                        senders=(
                            st.session_state
                            .senders
                        ),
                        categories=CATEGORIES,
                    )
                )

                classifications = (
                    result["classifications"]
                )

                missing_addresses = (
                    result["missing_addresses"]
                )

                invalid_categories = (
                    result["invalid_categories"]
                )

                duplicate_addresses = (
                    result["duplicate_addresses"]
                )

                col_a, col_b, col_c = st.columns(3)

                col_a.metric(
                    "Importiert",
                    len(classifications),
                )

                col_b.metric(
                    "Fehlende Absender",
                    len(missing_addresses),
                )

                col_c.metric(
                    "Ungültige Kategorien",
                    len(invalid_categories),
                )

                if duplicate_addresses:

                    st.warning(
                        "Doppelte E-Mail-Adressen in der "
                        "importierten CSV:\n\n"
                        + "\n".join(
                            f"• {address}"
                            for address
                            in duplicate_addresses
                        )
                    )

                if invalid_categories:

                    st.warning(
                        "Diese Kategorien waren ungültig "
                        "und wurden als „Unklar“ übernommen:\n\n"
                        + "\n".join(
                            f"• {address}: {category}"
                            for (
                                address,
                                category,
                            ) in invalid_categories
                        )
                    )

                if missing_addresses:

                    st.error(
                        f"{len(missing_addresses)} von "
                        f"{len(st.session_state.senders)} "
                        "Absendern fehlen in der "
                        "bearbeiteten CSV."
                    )

                    with st.expander(
                        "Fehlende Absender anzeigen"
                    ):
                        st.code(
                            "\n".join(
                                missing_addresses
                            )
                        )

                preview_rows = []

                for address, classification in (
                    classifications.items()
                ):

                    sender_info = (
                        st.session_state
                        .senders
                        .get(
                            address,
                            {},
                        )
                    )

                    preview_rows.append({
                        "E-Mail": address,
                        "Domain": sender_info.get(
                            "domain",
                            "",
                        ),
                        "Anzahl": sender_info.get(
                            "count",
                            0,
                        ),
                        "Kategorie": (
                            classification[
                                "category"
                            ]
                        ),
                        "Sicherheit": (
                            classification[
                                "confidence"
                            ]
                        ),
                        "Begründung": (
                            classification[
                                "reason"
                            ]
                        ),
                    })

                preview_df = pd.DataFrame(
                    preview_rows
                )

                if not preview_df.empty:

                    st.subheader(
                        "Import-Vorschau"
                    )

                    st.dataframe(
                        preview_df.sort_values(
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

                can_import = (
                    len(classifications) > 0
                    and len(missing_addresses) == 0
                )

                if st.button(
                    "Klassifizierung übernehmen",
                    type="primary",
                    use_container_width=True,
                    disabled=not can_import,
                ):

                    st.session_state.classifications = (
                        classifications
                    )

                    st.session_state.stats = {
                        "total": len(
                            classifications
                        ),
                        "cached": 0,
                        "new": len(
                            classifications
                        ),
                    }

                    st.session_state.api_log = []
                    st.session_state.live_results = (
                        classifications.copy()
                    )

                    st.success(
                        "CSV-Klassifizierung "
                        "wurde übernommen."
                    )

                    st.rerun()

            except Exception as exc:

                st.error(
                    "CSV konnte nicht verarbeitet "
                    f"werden: {exc}"
                )

    # =====================================================
    # GEMEINSAME ERGEBNISANZEIGE
    # =====================================================

    if st.session_state.classifications is not None:

        st.divider()

        st.subheader(
            "Klassifizierungsergebnisse"
        )

        if st.session_state.stats:

            stats = (
                st.session_state.stats
            )

            st.success(
                f"{stats['total']} "
                f"Absender ausgewertet."
            )

        rows = []

        for address, info in (
            st.session_state
            .senders
            .items()
        ):

            result = (
                st.session_state
                .classifications
                .get(
                    address,
                    {
                        "category":
                            "Unklar",
                        "confidence":
                            0.0,
                        "reason":
                            "Kein Ergebnis.",
                    },
                )
            )

            rows.append({
                "E-Mail":
                    address,
                "Domain":
                    info["domain"],
                "Anzahl":
                    info["count"],
                "Kategorie":
                    result["category"],
                "Sicherheit":
                    result["confidence"],
                "Begründung":
                    result["reason"],
            })

        class_df = pd.DataFrame(
            rows
        )

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
            file_name=(
                "classifications.csv"
            ),
            mime="text/csv",
        )

        if st.session_state.api_log:

            with st.expander(
                "API-Diagnose"
            ):

                st.dataframe(
                    pd.DataFrame(
                        st.session_state
                        .api_log
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        c1, c2, c3 = st.columns(3)

        with c1:

            if st.button(
                "Zurück zu den Absendern"
            ):

                st.session_state.step = 2
                st.rerun()

        with c2:

            if st.button(
                "Klassifizierung zurücksetzen",
                use_container_width=True,
            ):

                st.session_state.classifications = None
                st.session_state.stats = None
                st.session_state.api_log = []
                st.session_state.live_results = {}
                st.session_state.csv_import_preview = None

                st.rerun()

        with c3:

            if st.button(
                "Weiter zu den Zielordnern",
                type="primary",
                use_container_width=True,
            ):

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
