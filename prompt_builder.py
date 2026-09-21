import json

from config import CATEGORIES


def build_batch_prompt(batch):
    compact = []

    for address, info in batch:
        compact.append({
            "email": address,
            "name": info["name"],
            "domain": info["domain"],
            "count": info["count"],
            "subjects": info["subjects"],
        })

    return f"""
Du klassifizierst E-Mail-Absender für Thunderbird.

WICHTIG:
Die Kategorien sind gleichzeitig die gewünschten IMAP-Ordnernamen.
Verwende deshalb ausschließlich exakt einen dieser Werte:
{json.dumps(CATEGORIES, ensure_ascii=False)}

Definitionen:

Persönlich:
Direkte private Kommunikation zwischen realen Personen. Nicht als Auffangkategorie verwenden.

Arbeit:
Allgemeine berufliche Kommunikation, die weder Bewerbung noch Recruiting ist.

Bewerbungen:
Konkrete Kommunikation zu eigenen Bewerbungen, Arbeitgebern, Einladungen,
Absagen oder Bewerbungsprozessen.

Recruiter:
Personalvermittler, Headhunter und Recruiting-Agenturen.

Jobportale:
Automatische Stellenangebote und Jobbenachrichtigungen von Jobplattformen.

Rechnungen:
Rechnungen, Gutschriften, Zahlungsaufforderungen und Zahlungsbelege.

Banken:
Banken, Kreditkartenanbieter und sonstige Finanzinstitute.

Versicherungen:
Versicherungen, Krankenkassen und versicherungsbezogene Kommunikation.

Behörden:
Finanzamt/ELSTER, Arbeitsagentur-Verwaltung, Landkreis, Stadt,
Gemeinde und sonstige öffentliche Stellen.

Schule & Bildung:
Schulen, IServ, Lernplattformen, Weiterbildung, Kurse und Bildungseinrichtungen.

Termine:
Terminbestätigungen, Reservierungen, Abholtermine, Arzttermine
und sonstige konkrete Terminmitteilungen.

Konto & Sicherheit:
Login, Passwort, 2FA, Sicherheitswarnungen, Kontoänderungen
und Account-Schutz.

Bestellungen:
Bestell-, Kauf- oder Auftragsbestätigungen.

Versand:
Paketankündigungen, Tracking und Versandstatus.

Shops:
Allgemeine Kommunikation von Online-Shops, sofern keine passendere
Kategorie wie Bestellungen, Versand oder Rechnungen zutrifft.

Newsletter:
Regelmäßig versendete redaktionelle Newsletter.

Werbung:
Marketing, Rabatte, Aktionen und Verkaufsangebote.
Werbung ist nicht automatisch Spam.

Verträge & Service:
Hosting, Domains, Telefon, Energie, Software-Abonnements
und laufende Vertrags-/Serviceinformationen.

System:
Rein technische automatische Systemmeldungen einer Anwendung oder eines Dienstes.
Login- oder Sicherheitsmeldungen gehören stattdessen zu Konto & Sicherheit.

Kundenservice:
Individuelle Support-, Service- oder Rückfragekommunikation,
die keiner spezifischeren Kategorie zugeordnet werden kann.

Spam:
Nur eindeutig unerwünschte, betrügerische, verdächtige oder unspezifische Massenmail.
Bei Unsicherheit Werbung, Newsletter oder Unklar verwenden.

Unklar:
Nur wenn keine zuverlässige Zuordnung möglich ist.

Klassifiziere ALLE folgenden Einträge.

Eingabe:
{json.dumps(compact, ensure_ascii=False)}

Antworte ausschließlich mit JSON in diesem Format:

{{
  "results": [
    {{
      "email": "adresse@example.de",
      "category": "Rechnungen",
      "confidence": 0.95,
      "reason": "kurze Begründung"
    }}
  ]
}}
""".strip()
