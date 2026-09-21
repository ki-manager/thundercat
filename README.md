# ThunderCat v4.1

ThunderCat analysiert IMAP-Mailheader, klassifiziert Absender per KI und erzeugt
daraus Thunderbird-Filterregeln.

## Neu in v4.1

Die KI-Kategorien entsprechen jetzt direkt den gewünschten Ordnernamen:

- Persönlich
- Arbeit
- Bewerbungen
- Recruiter
- Jobportale
- Rechnungen
- Banken
- Versicherungen
- Behörden
- Schule & Bildung
- Termine
- Konto & Sicherheit
- Bestellungen
- Versand
- Shops
- Newsletter
- Werbung
- Verträge & Service
- System
- Kundenservice
- Spam
- Unklar

### Schritt 4

ThunderCat:

1. liest die vorhandenen IMAP-Ordner,
2. ordnet Kategorien automatisch passenden Ordnern zu,
3. erkennt auch verschachtelte Ordner anhand des letzten Ordnernamens,
4. zeigt fehlende Ordner deutlich an,
5. kann die IMAP-Struktur per Button erneut direkt vom Server abrufen,
6. verhindert die Erzeugung der Filterdatei, solange Zielordner fehlen.

Beispiel:

```text
Kategorie: Rechnungen
IMAP-Ordner: Finanzen/Rechnungen
=> automatische Zuordnung
```

## Provider

- OpenAI
- Gemini
- Ollama lokal

## Installation

```powershell
pip install -r requirements.txt
```

Optional für Ollama:

```powershell
ollama pull qwen3:1.7b
```

## Start

```powershell
python -m streamlit run app.py
```

## Datenschutz

ThunderCat liest nicht den vollständigen Nachrichtentext. Für die Analyse werden
Absendername, E-Mail-Adresse, Domain und einige Beispiel-Betreffzeilen verwendet.

Bei OpenAI oder Gemini werden diese Daten an den gewählten Cloud-Anbieter übertragen.
Bei Ollama erfolgt die Klassifizierung lokal.

## Cache

Der Cache ist ab v4.1 an die neue Kategorieversion gebunden. Alte Klassifizierungen
aus früheren ThunderCat-Versionen werden daher nicht versehentlich wiederverwendet.

Technische Fehler mit `Unklar` und Confidence 0 werden nicht dauerhaft gecacht.
