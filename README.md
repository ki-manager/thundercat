# ThunderCat v4.15

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
## Neu in v4.2: OpenAI-Diagnose

Schritt 3 ist in drei klar sichtbare Aktionen getrennt:

1. **Provider-Verbindung testen**
2. **Einen Absender klassifizieren**
3. **Gesamte Klassifizierung starten**

Für OpenAI gelten standardmäßig:

```text
Batch-Größe: 5
Timeout: 45 Sekunden
SDK-Retries: 0
```

Die OpenAI-Klassifizierung verwendet Structured Outputs mit JSON Schema.
Dadurch muss ThunderCat nicht auf frei formuliertes JSON hoffen.

Zusätzlich zeigt die Oberfläche:

- Status vor jedem API-Aufruf
- Laufzeit jedes Batches
- OpenAI Request-ID, sofern vorhanden
- konkrete API-/Timeout-Fehler
- Fortschritt und Cache-Zähler

Cloud-Fehler werden nicht mehr rekursiv minutenlang mit immer kleineren
Batches wiederholt. Ollama behält eine begrenzte lokale Batch-Aufteilung.

Wenn ein einzelner Test-Absender erfolgreich klassifiziert wird, ist die
grundsätzliche Provider-/Modell-/API-Key-Konfiguration funktionsfähig.
## Neu in v4.3: Live-Ergebnisse

Während der vollständigen KI-Klassifizierung zeigt Schritt 3 jetzt laufend die
bereits verarbeiteten Absender an.

Die Tabelle wird nach jedem klassifizierten Absender aktualisiert und enthält:

- E-Mail-Adresse
- Domain
- Anzahl der gefundenen Nachrichten
- Kategorie
- Sicherheit
- Begründung

Zusätzlich wird der Stand direkt in der Überschrift angezeigt, z. B.:

```text
Aktuelle Klassifizierungsergebnisse (15/87)
```

Auch der Test mit einem einzelnen Absender zeigt das Ergebnis jetzt zusätzlich
als Tabelle an.

Nach einem erfolgreichen Verbindungstest weist ThunderCat ausdrücklich darauf
hin, dass anschließend der Einzeltest oder der Gesamtlauf gestartet werden kann.
## Neu in v4.4

Die separaten Testschritte in Schritt 3 wurden wieder entfernt.

Der Ablauf ist jetzt wieder einfacher:

1. `Klassifizierung starten`
2. ThunderCat prüft intern automatisch die Provider-Verbindung
3. anschließend startet sofort die Klassifizierung
4. die Ergebnisse werden live während der Verarbeitung angezeigt

Die Live-Tabelle bleibt erhalten und zeigt nach jedem verarbeiteten
Absender den aktuellen Stand.
## Neu in v4.5: CSV-Klassifizierung über ChatGPT

In Schritt 3 kann jetzt zwischen zwei Verfahren gewählt werden:

### Direkt per KI-API

- OpenAI
- Gemini
- Ollama
- Live-Ergebnisse während der Verarbeitung

### CSV über ChatGPT klassifizieren

1. ThunderCat erzeugt eine CSV mit allen Absendern.
2. Die CSV wird heruntergeladen.
3. Die Datei wird in ChatGPT hochgeladen.
4. ChatGPT ergänzt:
   - Kategorie
   - Sicherheit
   - Begründung
5. Die bearbeitete CSV wird wieder in ThunderCat hochgeladen.
6. ThunderCat validiert die Datei.
7. Die Klassifizierungen werden übernommen.
8. Danach geht es wie gewohnt mit der automatischen Ordnerzuordnung weiter.

ThunderCat prüft beim Import:

- ob alle notwendigen Spalten vorhanden sind
- ob alle ursprünglichen Absender wieder enthalten sind
- ob doppelte Adressen vorhanden sind
- ob nur erlaubte Kategorien verwendet wurden
- ob die Sicherheit zwischen 0 und 1 liegt

Die CSV verwendet Semikolon als Trennzeichen und UTF-8 mit BOM.


## Fix v4.5.1

Die ChatGPT-CSV-Hilfsfunktionen sind jetzt direkt in `app.py` definiert. Der NameError bei `build_chatgpt_export_df()` ist behoben.


## Fix v4.6.1

- ChatGPT ist jetzt tatsächlich der erste Eintrag unter KI-Provider.
- ChatGPT ist voreingestellt.
- Bei ChatGPT werden keine weiteren Provider-Optionen angezeigt.
- Schritt 3 verwendet bei ChatGPT automatisch den CSV-Workflow.


## Neu in v4.7

Fehlende IMAP-Zielordner können in Schritt 4 automatisch direkt unterhalb von
`INBOX` angelegt werden.

Beispiele:

```text
INBOX/Rechnungen
INBOX/Behörden
INBOX/Newsletter
INBOX/Konto & Sicherheit
```

ThunderCat erkennt den IMAP-Hierarchie-Trenner automatisch. Falls der Server
statt `/` beispielsweise `.` verwendet, wird entsprechend `INBOX.Rechnungen`
angelegt.

Nach dem Erstellen liest ThunderCat die IMAP-Struktur sofort neu ein und
führt die automatische Ordnerzuordnung erneut aus.

`Unklar` wird bewusst nicht automatisch als Ordner angelegt.
## Neu in v4.8: Schritt 4 vereinfacht

Die automatische Ordnerzuordnung ist jetzt die einzige Quelle für die
Thunderbird-Zielordner.

- Der manuelle Abschnitt `Zuordnung` wurde entfernt.
- `Fehlende Ordner unter INBOX anlegen` steht links.
- `IMAP-Struktur erneut prüfen` steht rechts.
- Automatisch erkannte Zuordnungen werden direkt in
  `st.session_state.category_to_folder` übernommen.
- `Weiter zur Regelvorschau` verwendet exakt diese automatische Zuordnung.
- Bei fehlenden oder mehrdeutigen Ordnern ist `Weiter` deaktiviert.
- Die Zuordnung kann optional in einem aufklappbaren Kontrollbereich
  angezeigt werden.
- Modified UTF-7 für IMAP-Ordner mit Umlauten ist integriert.
## Neu in v4.9

Schritt 5 enthält nach dem Download der `msgFilterRules.dat` jetzt direkt eine
kurze Anleitung zur Installation in Thunderbird inklusive Profilpfad, typischem
Goneo-IMAP-Unterordner und Sicherungshinweis für bestehende Filter.
## Neu in v4.10

In Schritt 5 sind die umfangreichen Vorschauen standardmäßig eingeklappt:

- `Regeln prüfen und Vorschau`
- `msgFilterRules.dat Vorschau`

Die Erstellung der Filterdatei und die Thunderbird-Anleitung bleiben direkt sichtbar.
## Neu in v4.11: ChatGPT per Text/JSON

Für den Provider ChatGPT ist jetzt `Text / JSON kopieren` die Standardmethode.

Ablauf:

1. ThunderCat erzeugt einen vollständigen Prompt inklusive aller Absenderdaten.
2. Den Text nach ChatGPT kopieren.
3. ChatGPT ergänzt Kategorie, Sicherheit und Begründung.
4. Die reine JSON-Antwort zurück in ThunderCat kopieren.
5. ThunderCat validiert die Antwort und übernimmt die Klassifizierung.

Die bisherige CSV-Methode bleibt als Alternative erhalten.


## Neu in v4.12

Im ChatGPT-Text/JSON-Modus wurden zwei Komfortfunktionen ergänzt:

- `Prompt kopieren` kopiert den vollständigen Prompt in die Zwischenablage.
- `Daten einfügen` übernimmt die ChatGPT-Antwort aus der Zwischenablage.
- Das Prompt-Feld wurde von 420 auf 210 Pixel reduziert.
- Das Antwort-Feld wurde von 360 auf 180 Pixel reduziert.

Je nach Browser kann beim ersten Zugriff auf die Zwischenablage eine Berechtigungsabfrage erscheinen.


## Neu in v4.13

Schritt 3 enthält jetzt unten einen klaren Navigationsbereich:

- `Zurück`
- `Weiter zur Ordnerzuordnung`

Der Weiter-Button wird erst aktiv, wenn eine KI-/ChatGPT-Klassifizierung
erfolgreich übernommen wurde.


## Neu in v4.14: robuste E-Mail-Normalisierung

Beim Import einer ChatGPT-JSON-Antwort werden E-Mail-Adressen jetzt automatisch
bereinigt.

Unterstützte Varianten sind zum Beispiel:

- `christine@hoeke.net`
- `<christine@hoeke.net>`
- `mailto:christine@hoeke.net`
- `[christine@hoeke.net](mailto:christine@hoeke.net)`

Zusätzlich werden unsichtbare Unicode-Zeichen entfernt und Groß-/Kleinschreibung
vereinheitlicht.

Der ChatGPT-Prompt weist außerdem ausdrücklich darauf hin, E-Mail-Adressen nicht
als Markdown-Link auszugeben.


## Fix in v4.15

Fehler behoben:

`name 'sender_lookup' is not defined`

Die JSON-Importvorschau ermittelt den ursprünglichen Absender jetzt direkt über
die normalisierte E-Mail-Adresse. Die vorhandene CSV-Importlogik bleibt
unverändert.
