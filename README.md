# Thunderbird Ollama Mail Sorter – Streamlit v3

Neu in v3:
- Batch-Klassifizierung mehrerer Absender pro Ollama-Anfrage
- lokaler Cache in `cache/classification_cache.json`
- Fortschrittsanzeige mit Cache-/Neu-Zähler und Laufzeit
- CSV-Downloads für Klassifizierung und Regelvorschau
- Option, den Cache zu ignorieren und alles neu zu klassifizieren

## Installation
```bash
pip install -r requirements.txt
ollama pull qwen3:4b
```

## Start
```bash
streamlit run app.py
```

Browser: `http://localhost:8501`

## Ablauf
1. IMAP-Zugang eingeben und Header auslesen
2. Absender prüfen
3. Ollama-Batch-Klassifizierung mit Cache
4. Zielordner auswählen
5. Regeln prüfen und `msgFilterRules.dat` erzeugen

## Batch-Größe
Für `qwen3:4b` sind 10–20 ein guter Start. Bei wenig RAM eher 5–10.

## Datenschutz
Die IMAP-Zugangsdaten werden nur während der laufenden Streamlit-Sitzung verwendet. Der Mailtext wird nicht gelesen; verarbeitet werden Absender, Domain und einige Betreffzeilen. Ollama läuft lokal.
