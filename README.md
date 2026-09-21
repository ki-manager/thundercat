# Thunderbird Ollama Mail Sorter – Streamlit

## Funktionen

- IMAP-Zugangsdaten direkt in der Weboberfläche eingeben
- Headerdaten des Postfachs auslesen
- Absender und Domains als Tabelle anzeigen
- lokale Klassifizierung über Ollama
- Thunderbird-Regeln vorab prüfen
- `msgFilterRules.dat` erst nach Bestätigung erzeugen

## Installation

```bash
pip install -r requirements.txt
ollama pull qwen3:4b
```

## Start

```bash
streamlit run app.py
```

Danach im Browser:

```text
http://localhost:8501
```

## Ablauf

1. IMAP-Zugang eingeben und Header auslesen
2. Absender prüfen
3. Ollama-Klassifizierung und Regelvorschau
4. Filterdatei erzeugen und herunterladen

## Datenschutz

Das Tool liest nur:

- Absendername
- Absenderadresse
- Domain
- einige Betreffzeilen

Der Nachrichtentext wird nicht gelesen.
Die Klassifizierung erfolgt lokal über Ollama.

## Thunderbird-Zielordner

Passe `FOLDER_MAP` in `config.py` an dein tatsächliches IMAP-/Thunderbird-Konto an.

Vor dem Ersetzen einer vorhandenen `msgFilterRules.dat` Thunderbird vollständig schließen und zuerst eine Sicherung der bestehenden Datei erstellen.
