# ThunderCat

Streamlit-App zur Analyse und Sortierung von Thunderbird-/IMAP-Mails mit lokalem Ollama.

## Funktionen

1. IMAP-Zugangsdaten im Browser eingeben
2. E-Mail-Header auslesen
3. Absender prüfen
4. Ollama-Klassifizierung mit Batch + Cache
5. IMAP-Zielordner auswählen
6. Thunderbird-Regeln prüfen
7. `msgFilterRules.dat` herunterladen

## Installation

```powershell
pip install -r requirements.txt
ollama pull qwen3:1.7b
```

## Start

```powershell
python -m streamlit run app.py
```

Danach normalerweise:

```text
http://localhost:8501
```

## Logo

Das Projekt enthält:

```text
assets/thundercat_logo.png
assets/thundercat_icon.png
```

Das Logo wird im Seitenkopf mit 64 px Breite angezeigt.

## Datenschutz

Der Nachrichtentext wird nicht gelesen. Verarbeitet werden nur:

- Absendername
- E-Mail-Adresse
- Domain
- einige Betreffzeilen

Ollama läuft lokal.

## Cache

Bereits analysierte Absender werden gespeichert in:

```text
cache/classification_cache.json
```
