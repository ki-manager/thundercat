import time
import json
import re
import pandas as pd
import streamlit as st

from config import (
    DEFAULT_PROVIDER, OPENAI_MODEL, GEMINI_MODEL, OLLAMA_URL, OLLAMA_MODEL,
    MAX_MAILS_PER_FOLDER, SUBJECTS_PER_SENDER, MIN_CONFIDENCE,
    BATCH_SIZE_OPENAI, BATCH_SIZE_GEMINI, BATCH_SIZE_OLLAMA,
    CATEGORIES, CATEGORY_LABELS,
)
from imap_reader import (
    scan_mail_headers,
    refresh_folder_structure,
    create_missing_folders_under_inbox,
)
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
        normalize_email_address(address)
        for address in senders.keys()
    }

    sender_lookup = {
        normalize_email_address(address): address
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



# ---------------------------------------------------------
# Hilfsfunktionen für ChatGPT-Text/JSON
# ---------------------------------------------------------



def normalize_email_address(value):
    """
    Normalisiert E-Mail-Adressen aus ChatGPT-/JSON-Antworten.

    Unterstützt u. a.:
    - user@example.com
    - <user@example.com>
    - mailto:user@example.com
    - [user@example.com](mailto:user@example.com)
    - Groß-/Kleinschreibung
    - umgebende Leerzeichen
    - Zero-Width-Zeichen
    """
    value = str(value or "")

    # Unsichtbare Unicode-Zeichen entfernen
    value = re.sub(
        r"[\u200b\u200c\u200d\u2060\ufeff]",
        "",
        value,
    )

    value = value.strip()

    # Markdown-Mailto-Link:
    # [user@example.com](mailto:user@example.com)
    markdown_match = re.fullmatch(
        r"\[([^\]]+)\]\(\s*mailto:([^)]+)\s*\)",
        value,
        flags=re.I,
    )

    if markdown_match:
        value = markdown_match.group(2).strip()

    # Falls ein normaler Markdown-Link mit der Adresse als Ziel vorkommt
    markdown_generic = re.fullmatch(
        r"\[([^\]]+)\]\(([^)]+)\)",
        value,
        flags=re.I,
    )

    if markdown_generic:
        target = markdown_generic.group(2).strip()

        if target.lower().startswith("mailto:"):
            value = target[7:]
        elif "@" in target:
            value = target

    value = re.sub(
        r"^mailto:",
        "",
        value,
        flags=re.I,
    )

    value = value.strip(
        "<> \t\r\n\"'"
    )

    # Falls ChatGPT hinter der Adresse noch Text ergänzt hat,
    # die erste plausible E-Mail-Adresse extrahieren.
    email_match = re.search(
        r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
        value,
        flags=re.I,
    )

    if email_match:
        value = email_match.group(0)

    return value.casefold()

def build_chatgpt_json_prompt(senders, categories):
    items = []

    for address, info in sorted(
        senders.items(),
        key=lambda item: -item[1]["count"],
    ):
        items.append({
            "email": address,
            "name": info.get("name", ""),
            "domain": info.get("domain", ""),
            "count": info.get("count", 0),
            "subjects": info.get("subjects", []),
            "category": "",
            "confidence": "",
            "reason": "",
        })

    categories_text = "\n".join(
        f"- {category}"
        for category in categories
    )

    data_json = json.dumps(
        items,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
Analysiere die folgenden E-Mail-Absender und ergänze ausschließlich die Felder
category, confidence und reason.

Verwende für category ausschließlich exakt einen der folgenden Werte:

{categories_text}

Regeln:
- Persönlich nur für echte private Kommunikation.
- Spam nur für eindeutig unerwünschte, betrügerische oder verdächtige Massenmails.
- Werbung ist nicht automatisch Spam.
- Sicherheits- und Login-Mails gehören zu Konto & Sicherheit.
- Behörden wie ELSTER, Stadt, Landkreis oder öffentliche Stellen gehören zu Behörden.
- Schule, IServ, Lernplattformen und Weiterbildung gehören zu Schule & Bildung.
- confidence muss als Dezimalzahl zwischen 0 und 1 angegeben werden.
- Ändere email, name, domain, count und subjects nicht.
- Entferne keine Einträge.
- Füge keine Einträge hinzu.
- Gib ausschließlich gültiges JSON zurück.
- Verwende exakt dieselbe Reihenfolge wie in der Eingabe.
- Keine Markdown-Codeblöcke und keinen zusätzlichen Text ausgeben.
- E-Mail-Adressen niemals als Markdown-Link formatieren.
- Das Feld email muss immer nur die reine Adresse enthalten, z. B. user@example.com.
- Kein mailto:, keine spitzen Klammern und keine Markdown-Syntax im Feld email.

Daten:

{data_json}
""".strip()

    return prompt


def parse_chatgpt_json_result(
    response_text,
    senders,
    categories,
):
    text = str(response_text or "").strip()

    if not text:
        raise ValueError(
            "Es wurde keine ChatGPT-Antwort eingefügt."
        )

    # Falls trotzdem ein Markdown-Codeblock zurückgegeben wurde.
    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    data = json.loads(text)

    if not isinstance(data, list):
        raise ValueError(
            "Die ChatGPT-Antwort muss eine JSON-Liste sein."
        )

    original_addresses = {
        address.lower().strip()
        for address in senders.keys()
    }

    classifications = {}
    invalid_categories = []
    duplicate_addresses = []
    unknown_addresses = []
    seen = set()

    for item in data:
        if not isinstance(item, dict):
            continue

        address = normalize_email_address(
            item.get("email", "")
        )

        if not address:
            continue

        if address in seen:
            duplicate_addresses.append(address)
            continue

        seen.add(address)

        if address not in original_addresses:
            unknown_addresses.append(address)
            continue

        category = str(
            item.get("category", "")
        ).strip()

        if category not in categories:
            invalid_categories.append(
                (address, category)
            )
            category = "Unklar"

        try:
            confidence = float(
                item.get("confidence", 0)
            )
        except Exception:
            confidence = 0.0

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        reason = str(
            item.get("reason", "")
        ).strip()

        classifications[address] = {
            "category": category,
            "confidence": confidence,
            "reason": reason,
        }

    missing_addresses = sorted(
        original_addresses
        - set(classifications.keys())
    )

    return {
        "classifications": classifications,
        "missing_addresses": missing_addresses,
        "invalid_categories": invalid_categories,
        "duplicate_addresses": duplicate_addresses,
        "unknown_addresses": unknown_addresses,
    }


def build_category_message_counts(senders, classifications):
    counts = {}

    for address, classification in classifications.items():
        category = classification.get("category", "Unklar")
        sender_info = senders.get(address, {})
        message_count = int(sender_info.get("count", 0) or 0)

        counts[category] = counts.get(category, 0) + message_count

    return counts


def build_effective_folder_mapping(
    auto_mapping,
    category_message_counts,
    minimum_messages=5,
    fallback_folder=None,
):
    result = {}

    for category, count in category_message_counts.items():
        if category == "Unklar":
            continue

        if count >= minimum_messages:
            folder = auto_mapping.get(category)
            if folder:
                result[category] = folder
        elif fallback_folder:
            result[category] = fallback_folder

    return result


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
    "imap_server": "imap.goneo.de",
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
    imap_server = st.text_input("IMAP-Server", value=st.session_state.imap_server or "imap.goneo.de", placeholder="imap.example.de")
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
    # VARIANTE B: CHATGPT OHNE API
    # =====================================================

    else:

        st.subheader(
            "Klassifizierung über ChatGPT"
        )

        chatgpt_transfer_mode = st.radio(
            "Übertragungsart",
            [
                "Text / JSON kopieren",
                "CSV-Datei",
            ],
            index=0,
            horizontal=True,
        )

        # -------------------------------------------------
        # TEXT / JSON
        # -------------------------------------------------

        if chatgpt_transfer_mode == "Text / JSON kopieren":

            st.write(
                "Du kopierst den kompletten Prompt inklusive "
                "Absenderdaten nach ChatGPT und anschließend "
                "die JSON-Antwort wieder zurück in ThunderCat."
            )

            st.markdown(
                "#### 1. Prompt für ChatGPT"
            )

            chatgpt_json_prompt = (
                build_chatgpt_json_prompt(
                    st.session_state.senders,
                    CATEGORIES,
                )
            )

            st.text_area(
                "Kompletten Text kopieren und in ChatGPT einfügen",
                value=chatgpt_json_prompt,
                height=210,
                key="chatgpt_json_prompt_text",
            )

            st.download_button(
                "⬇️ Prompt als TXT herunterladen",
                data=chatgpt_json_prompt.encode("utf-8-sig"),
                file_name="thundercat_chatgpt_prompt.txt",
                mime="text/plain",
                use_container_width=True,
                key="download_chatgpt_prompt_txt",
            )

            st.components.v1.html(
                """
                <button
                    id="copyPrompt"
                    style="
                        border:1px solid #d0d0d0;
                        border-radius:8px;
                        padding:8px 14px;
                        background:white;
                        cursor:pointer;
                        font-size:14px;
                    "
                >
                    📋 Prompt kopieren
                </button>

                <script>
                const button = document.getElementById("copyPrompt");

                button.addEventListener("click", async () => {
                    const textareas = parent.document.querySelectorAll("textarea");
                    let promptArea = null;

                    for (const area of textareas) {
                        if (
                            area.getAttribute("aria-label") ===
                            "Kompletten Text kopieren und in ChatGPT einfügen"
                        ) {
                            promptArea = area;
                            break;
                        }
                    }

                    if (!promptArea) {
                        button.innerText = "Textfeld nicht gefunden";
                        return;
                    }

                    try {
                        await navigator.clipboard.writeText(promptArea.value);
                        button.innerText = "✓ Prompt kopiert";
                    } catch (error) {
                        button.innerText = "Kopieren nicht möglich";
                    }
                });
                </script>
                """,
                height=45,
            )

            st.caption(
                f"{len(st.session_state.senders)} Absender "
                "sind im Prompt enthalten."
            )

            st.markdown(
                "#### 2. JSON-Antwort aus ChatGPT einfügen"
            )

            uploaded_json_file = st.file_uploader(
                "Fertige JSON-Datei aus ChatGPT hochladen",
                type=["json"],
                key="chatgpt_json_file_upload",
                help=(
                    "Die JSON-Datei muss dieselbe Liste von Absendern enthalten "
                    "und die Felder category, confidence und reason ergänzen."
                ),
            )

            uploaded_json_text = ""

            if uploaded_json_file is not None:
                try:
                    uploaded_json_text = (
                        uploaded_json_file
                        .getvalue()
                        .decode("utf-8-sig")
                    )
                    st.success(
                        "JSON-Datei geladen. "
                        "Die Daten werden automatisch geprüft."
                    )
                except Exception as exc:
                    st.error(
                        f"JSON-Datei konnte nicht gelesen werden: {exc}"
                    )

            json_response = st.text_area(
                "ChatGPT-Antwort",
                value="",
                height=180,
                placeholder=(
                    '[\n'
                    '  {\n'
                    '    "email": "portal@elster.de",\n'
                    '    "name": "ELSTER",\n'
                    '    "domain": "elster.de",\n'
                    '    "count": 4,\n'
                    '    "subjects": ["Neue Nachricht"],\n'
                    '    "category": "Behörden",\n'
                    '    "confidence": 0.99,\n'
                    '    "reason": "Kommunikation der Finanzverwaltung."\n'
                    '  }\n'
                    ']'
                ),
                key="chatgpt_json_response_text",
            )

            st.components.v1.html(
                """
                <button
                    id="pasteData"
                    style="
                        border:1px solid #d0d0d0;
                        border-radius:8px;
                        padding:8px 14px;
                        background:white;
                        cursor:pointer;
                        font-size:14px;
                    "
                >
                    📥 Daten einfügen
                </button>

                <script>
                const button = document.getElementById("pasteData");

                button.addEventListener("click", async () => {
                    try {
                        const text = await navigator.clipboard.readText();
                        const textareas = parent.document.querySelectorAll("textarea");
                        let responseArea = null;

                        for (const area of textareas) {
                            if (
                                area.getAttribute("aria-label") ===
                                "ChatGPT-Antwort"
                            ) {
                                responseArea = area;
                                break;
                            }
                        }

                        if (!responseArea) {
                            button.innerText = "Textfeld nicht gefunden";
                            return;
                        }

                        const setter = Object.getOwnPropertyDescriptor(
                            parent.HTMLTextAreaElement.prototype,
                            "value"
                        ).set;

                        setter.call(responseArea, text);

                        responseArea.dispatchEvent(
                            new Event("input", {
                                bubbles: true
                            })
                        );

                        responseArea.dispatchEvent(
                            new Event("change", {
                                bubbles: true
                            })
                        );

                        responseArea.focus();

                        button.innerText = "✓ Daten eingefügt";
                    } catch (error) {
                        button.innerText = "Einfügen nicht möglich";
                    }
                });
                </script>
                """,
                height=45,
            )

            json_input = (
                uploaded_json_text
                if uploaded_json_text.strip()
                else json_response
            )

            if json_input.strip():

                try:

                    result = (
                        parse_chatgpt_json_result(
                            response_text=json_input,
                            senders=(
                                st.session_state.senders
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

                    unknown_addresses = (
                        result["unknown_addresses"]
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
                            "Doppelte E-Mail-Adressen:\n\n"
                            + "\n".join(
                                f"• {address}"
                                for address
                                in duplicate_addresses
                            )
                        )

                    if unknown_addresses:
                        st.warning(
                            "Unbekannte E-Mail-Adressen "
                            "in der ChatGPT-Antwort:\n\n"
                            + "\n".join(
                                f"• {address}"
                                for address
                                in unknown_addresses
                            )
                        )

                    if invalid_categories:
                        st.warning(
                            "Ungültige Kategorien wurden "
                            "als „Unklar“ übernommen:\n\n"
                            + "\n".join(
                                f"• {address}: {category}"
                                for address, category
                                in invalid_categories
                            )
                        )

                    if missing_addresses:
                        st.error(
                            f"{len(missing_addresses)} von "
                            f"{len(st.session_state.senders)} "
                            "Absendern fehlen in der Antwort."
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
                        original_sender_key = next(
                            (
                                original_address
                                for original_address
                                in st.session_state.senders.keys()
                                if normalize_email_address(
                                    original_address
                                )
                                == normalize_email_address(
                                    address
                                )
                            ),
                            address,
                        )

                        sender_info = (
                            st.session_state.senders.get(
                                original_sender_key,
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
                            "Kategorie": classification[
                                "category"
                            ],
                            "Sicherheit": classification[
                                "confidence"
                            ],
                            "Begründung": classification[
                                "reason"
                            ],
                        })

                    preview_df = pd.DataFrame(
                        preview_rows
                    )

                    if not preview_df.empty:
                        with st.expander(
                            "Import-Vorschau",
                            expanded=False,
                        ):
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
                        "JSON-Klassifizierung übernehmen",
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
                            "ChatGPT-Klassifizierung "
                            "wurde übernommen."
                        )

                        st.rerun()

                except json.JSONDecodeError as exc:

                    st.error(
                        "Die eingefügte Antwort ist kein "
                        f"gültiges JSON: {exc}"
                    )

                except Exception as exc:

                    st.error(
                        "ChatGPT-Antwort konnte nicht "
                        f"verarbeitet werden: {exc}"
                    )

        # -------------------------------------------------
        # CSV ALS ALTERNATIVE
        # -------------------------------------------------

        else:

            st.write(
                "Alternativ kannst du weiterhin eine CSV-Datei "
                "herunterladen, in ChatGPT bearbeiten lassen "
                "und anschließend wieder hochladen."
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

            st.markdown(
                "#### 2. CSV in ChatGPT klassifizieren"
            )

            chatgpt_prompt = """
Analysiere die hochgeladene CSV-Datei mit E-Mail-Absendern.

Ergänze ausschließlich die Spalten Kategorie, Sicherheit und Begründung.

Verwende ausschließlich die in ThunderCat vorgegebenen Kategorien.
Ändere keine bestehenden Werte, entferne keine Zeilen und füge keine hinzu.

Gib anschließend die vollständige CSV-Datei mit Semikolon als Trennzeichen zurück.
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
                                st.session_state.senders
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
                            "Doppelte E-Mail-Adressen:\n\n"
                            + "\n".join(
                                f"• {address}"
                                for address
                                in duplicate_addresses
                            )
                        )

                    if invalid_categories:
                        st.warning(
                            "Ungültige Kategorien wurden "
                            "als „Unklar“ übernommen:\n\n"
                            + "\n".join(
                                f"• {address}: {category}"
                                for address, category
                                in invalid_categories
                            )
                        )

                    if missing_addresses:
                        st.error(
                            f"{len(missing_addresses)} von "
                            f"{len(st.session_state.senders)} "
                            "Absendern fehlen in der CSV."
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
                            st.session_state.senders.get(
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
                            "Kategorie": classification[
                                "category"
                            ],
                            "Sicherheit": classification[
                                "confidence"
                            ],
                            "Begründung": classification[
                                "reason"
                            ],
                        })

                    preview_df = pd.DataFrame(
                        preview_rows
                    )

                    if not preview_df.empty:
                        with st.expander(
                            "Import-Vorschau",
                            expanded=False,
                        ):
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
                        "CSV-Klassifizierung übernehmen",
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

    # -----------------------------------------------------
    # Navigation
    # -----------------------------------------------------

    st.divider()

    classifications_ready = bool(
        st.session_state.classifications
    )

    col_back, col_next = st.columns(2)

    with col_back:
        if st.button(
            "Zurück",
            key="step3_back",
        ):
            st.session_state.step = 2
            st.rerun()

    with col_next:
        if st.button(
            "Weiter zur Ordnerzuordnung",
            type="primary",
            use_container_width=True,
            disabled=not classifications_ready,
            key="step3_next",
        ):
            st.session_state.step = 4
            st.rerun()

    if not classifications_ready:
        st.caption(
            "Der Weiter-Button wird aktiv, sobald "
            "eine Klassifizierung übernommen wurde."
        )


elif st.session_state.step == 4:

    st.header("4. Thunderbird-Zielordner prüfen")

    st.write(
        "ThunderCat erstellt nur für Kategorien mit mindestens "
        "**5 vorhandenen Nachrichten** einen eigenen Zielordner. "
        "Kategorien mit weniger Nachrichten werden automatisch "
        "nach **Sonstiges** verschoben."
    )

    MIN_MESSAGES_FOR_FOLDER = 5
    FALLBACK_CATEGORY = "Sonstiges"

    folders = st.session_state.folders or []

    category_message_counts = build_category_message_counts(
        st.session_state.senders,
        st.session_state.classifications,
    )

    own_folder_categories = [
        category
        for category, count in category_message_counts.items()
        if category != "Unklar"
        and count >= MIN_MESSAGES_FOR_FOLDER
    ]

    fallback_categories = [
        category
        for category, count in category_message_counts.items()
        if category != "Unklar"
        and count < MIN_MESSAGES_FOR_FOLDER
    ]

    auto_mapping_all, _, ambiguous_all = auto_map_categories(
        CATEGORIES,
        folders,
    )

    auto_mapping = {
        category: folder
        for category, folder in auto_mapping_all.items()
        if category in own_folder_categories
        and folder
    }

    ambiguous = {
        category: matches
        for category, matches in ambiguous_all.items()
        if category in own_folder_categories
    }

    fallback_mapping, _, fallback_ambiguous = auto_map_categories(
        [FALLBACK_CATEGORY],
        folders,
    )

    fallback_folder = fallback_mapping.get(FALLBACK_CATEGORY)

    if fallback_ambiguous:
        ambiguous.update(fallback_ambiguous)

    missing_own_folders = [
        category
        for category in own_folder_categories
        if category not in auto_mapping
        and category not in ambiguous
    ]

    needs_fallback_folder = bool(fallback_categories)

    missing_to_create = list(missing_own_folders)

    if (
        needs_fallback_folder
        and not fallback_folder
        and FALLBACK_CATEGORY not in ambiguous
    ):
        missing_to_create.append(FALLBACK_CATEGORY)

    col_create, col_refresh = st.columns(2)

    with col_create:
        create_clicked = st.button(
            "➕ Fehlende Ordner unter INBOX anlegen",
            type="primary",
            use_container_width=True,
            disabled=not bool(missing_to_create),
        )

    with col_refresh:
        refresh_clicked = st.button(
            "🔄 IMAP-Struktur erneut prüfen",
            use_container_width=True,
        )

    if create_clicked:
        if not imap_password:
            st.error(
                "Bitte links in der Seitenleiste "
                "das IMAP-Passwort erneut eingeben."
            )
        else:
            try:
                with st.spinner(
                    "Fehlende Ordner werden unter INBOX angelegt …"
                ):
                    create_results, separator = (
                        create_missing_folders_under_inbox(
                            server=st.session_state.imap_server or imap_server,
                            port=st.session_state.imap_port or imap_port,
                            username=st.session_state.imap_username or imap_username,
                            password=imap_password,
                            folder_names=missing_to_create,
                            parent="INBOX",
                        )
                    )

                refreshed_folders = refresh_folder_structure(
                    server=st.session_state.imap_server or imap_server,
                    port=st.session_state.imap_port or imap_port,
                    username=st.session_state.imap_username or imap_username,
                    password=imap_password,
                )

                st.session_state.folders = refreshed_folders
                st.rerun()

            except Exception as exc:
                st.error(
                    f"Fehler beim Anlegen der IMAP-Ordner: {exc}"
                )

    if refresh_clicked:
        if not imap_password:
            st.error(
                "Bitte links in der Seitenleiste "
                "das IMAP-Passwort erneut eingeben."
            )
        else:
            try:
                refreshed_folders = refresh_folder_structure(
                    server=st.session_state.imap_server or imap_server,
                    port=st.session_state.imap_port or imap_port,
                    username=st.session_state.imap_username or imap_username,
                    password=imap_password,
                )

                st.session_state.folders = refreshed_folders
                st.rerun()

            except Exception as exc:
                st.error(
                    f"IMAP-Fehler beim erneuten Prüfen: {exc}"
                )

    folders = st.session_state.folders or []

    auto_mapping_all, _, ambiguous_all = auto_map_categories(
        CATEGORIES,
        folders,
    )

    auto_mapping = {
        category: folder
        for category, folder in auto_mapping_all.items()
        if category in own_folder_categories
        and folder
    }

    ambiguous = {
        category: matches
        for category, matches in ambiguous_all.items()
        if category in own_folder_categories
    }

    fallback_mapping, _, fallback_ambiguous = auto_map_categories(
        [FALLBACK_CATEGORY],
        folders,
    )

    fallback_folder = fallback_mapping.get(FALLBACK_CATEGORY)

    if fallback_ambiguous:
        ambiguous.update(fallback_ambiguous)

    missing_own_folders = [
        category
        for category in own_folder_categories
        if category not in auto_mapping
        and category not in ambiguous
    ]

    fallback_missing_now = (
        needs_fallback_folder
        and not fallback_folder
    )

    effective_mapping = build_effective_folder_mapping(
        auto_mapping=auto_mapping,
        category_message_counts=category_message_counts,
        minimum_messages=MIN_MESSAGES_FOR_FOLDER,
        fallback_folder=fallback_folder,
    )

    st.session_state.category_to_folder = effective_mapping.copy()

    st.subheader("Automatischer Abgleich")

    metric1, metric2, metric3 = st.columns(3)

    metric1.metric(
        "Eigene Kategorie-Ordner",
        len(own_folder_categories),
    )

    metric2.metric(
        "Nach Sonstiges",
        len(fallback_categories),
    )

    metric3.metric(
        "Fehlende Ordner",
        len(missing_own_folders)
        + (1 if fallback_missing_now else 0)
        + len(ambiguous),
    )

    count_rows = []

    for category, count in sorted(
        category_message_counts.items(),
        key=lambda item: (-item[1], item[0].casefold()),
    ):
        if category == "Unklar":
            target = "Keine Regel"
        elif count >= MIN_MESSAGES_FOR_FOLDER:
            target = auto_mapping.get(
                category,
                f"INBOX/{category}",
            )
        else:
            target = fallback_folder or "INBOX/Sonstiges"

        count_rows.append({
            "Kategorie": category,
            "Nachrichten": count,
            "Ziel": target,
        })

    with st.expander(
        "Kategorie-Verteilung anzeigen",
        expanded=False,
    ):
        st.dataframe(
            pd.DataFrame(count_rows),
            use_container_width=True,
            hide_index=True,
        )

    if missing_own_folders:
        st.warning(
            "Für diese Kategorien mit mindestens "
            f"{MIN_MESSAGES_FOR_FOLDER} Nachrichten fehlen eigene Ordner:\n\n"
            + "\n".join(
                f"• INBOX/{category}"
                for category in missing_own_folders
            )
        )

    if fallback_missing_now:
        st.warning(
            "Für Kategorien mit weniger als "
            f"{MIN_MESSAGES_FOR_FOLDER} Nachrichten fehlt noch:\n\n"
            "• INBOX/Sonstiges"
        )

    if ambiguous:
        details = [
            f"• {category}: " + ", ".join(matches)
            for category, matches in ambiguous.items()
        ]

        st.error(
            "Mehrdeutige Ordnerzuordnung:\n\n"
            + "\n".join(details)
        )

    if (
        not missing_own_folders
        and not fallback_missing_now
        and not ambiguous
    ):
        st.success(
            "Ordnerzuordnung vollständig. Kategorien ab 5 Nachrichten "
            "erhalten einen eigenen Ordner; kleinere Kategorien werden "
            "nach Sonstiges verschoben."
        )

    with st.expander(
        "Effektive Zuordnung anzeigen",
        expanded=False,
    ):
        effective_rows = [
            {
                "Kategorie": category,
                "Nachrichten": category_message_counts.get(category, 0),
                "Zielordner": folder,
            }
            for category, folder in sorted(
                effective_mapping.items(),
                key=lambda item: item[0].casefold(),
            )
        ]

        st.dataframe(
            pd.DataFrame(effective_rows),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander(
        "Aktuelle IMAP-Ordnerstruktur anzeigen"
    ):
        st.dataframe(
            pd.DataFrame({
                "IMAP-Ordner": folders
            }),
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
        can_continue = (
            not missing_own_folders
            and not fallback_missing_now
            and not ambiguous
        )

        if st.button(
            "Weiter zur Regelvorschau",
            type="primary",
            use_container_width=True,
            disabled=not can_continue,
        ):
            st.session_state.category_to_folder = (
                effective_mapping.copy()
            )

            rules = create_rule_preview(
                senders=st.session_state.senders,
                classifications=st.session_state.classifications,
                category_to_folder=effective_mapping,
                server=st.session_state.imap_server,
                username=st.session_state.imap_username,
            )

            st.session_state.rules = rules
            st.session_state.step = 5
            st.rerun()


elif st.session_state.step == 5:
    st.header("5. Regeln prüfen und Filterdatei erzeugen")
    rules_df = pd.DataFrame(st.session_state.rules)

    if rules_df.empty:
        st.warning("Es wurden keine Regeln erzeugt.")
    else:
        with st.expander(
            "Regeln prüfen und Vorschau",
            expanded=False,
        ):
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
            if st.button(
                "Jetzt msgFilterRules.dat erzeugen",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.filter_text = generate_filter_text(
                    st.session_state.rules
                )
                st.rerun()
        else:
            st.success("Filterdatei wurde erzeugt.")

            with st.expander(
                "msgFilterRules.dat Vorschau",
                expanded=False,
            ):
                st.text_area(
                    "Vorschau",
                    st.session_state.filter_text,
                    height=350,
                )
            st.download_button(
                "msgFilterRules.dat herunterladen",
                data=st.session_state.filter_text.encode("utf-8"),
                file_name="msgFilterRules.dat",
                mime="text/plain",
                type="primary",
                use_container_width=True,
            )

            st.divider()

            st.subheader(
                "So fügst du die Filter in Thunderbird ein"
            )

            st.markdown(
                """
1. **Thunderbird komplett beenden.**
2. Die heruntergeladene Datei `msgFilterRules.dat` bereithalten.
3. Unter Windows `Win + R` drücken und folgenden Pfad öffnen:

   `%APPDATA%\\Thunderbird\\Profiles\\`

4. Den verwendeten Profilordner öffnen.
5. Danach in den Ordner des IMAP-Kontos wechseln, meist:

   `ImapMail\\imap.goneo.de`

6. Eine vorhandene `msgFilterRules.dat` **vorher sichern**.
7. Die von ThunderCat erzeugte `msgFilterRules.dat` in diesen Ordner kopieren bzw. ersetzen.
8. Thunderbird wieder starten.
9. Die Regeln findest du anschließend unter **Extras → Nachrichtenfilter** beim betreffenden Konto.

**Wichtig:** Wenn bereits eigene Filter vorhanden sind, solltest du die bestehende Datei nicht einfach überschreiben, da sonst vorhandene Regeln verloren gehen können.
"""
            )

            if st.button("Neue Analyse starten"):
                st.session_state.clear()
                st.rerun()
