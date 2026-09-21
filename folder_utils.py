import re
import unicodedata


def normalize_folder_name(value):
    value = str(value or "").strip()

    # Nur den letzten Pfadteil für automatisches Matching nutzen.
    # Unterstützt typische IMAP-Trenner "/" und ".".
    leaf = re.split(r"[/.]", value)[-1].strip()

    normalized = unicodedata.normalize("NFKD", leaf)
    normalized = "".join(
        ch for ch in normalized
        if not unicodedata.combining(ch)
    )
    normalized = normalized.casefold()
    normalized = normalized.replace("&", "und")
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)

    return normalized


def auto_map_categories(categories, folders):
    """
    Ordnet Kategorien automatisch vorhandenen IMAP-Ordnern zu.

    Reihenfolge:
    1. exakter vollständiger Name
    2. exakter Leaf-Name (z. B. 'Finanzen/Rechnungen' -> 'Rechnungen')
    3. normalisierter Leaf-Name (Umlaute, &, Leerzeichen tolerant)

    Liefert:
      mapping: Kategorie -> Ordner oder None
      missing: nicht gefundene Kategorien
      ambiguous: Kategorie -> mehrere mögliche Ordner
    """
    folders = list(dict.fromkeys(folders or []))

    full_exact = {folder.casefold(): folder for folder in folders}

    normalized_lookup = {}
    leaf_lookup = {}

    for folder in folders:
        leaf = re.split(r"[/.]", folder)[-1].strip()
        leaf_lookup.setdefault(leaf.casefold(), []).append(folder)
        normalized_lookup.setdefault(
            normalize_folder_name(folder),
            []
        ).append(folder)

    mapping = {}
    missing = []
    ambiguous = {}

    for category in categories:
        if category == "Unklar":
            continue

        # 1. kompletter exakter Name
        exact = full_exact.get(category.casefold())
        if exact:
            mapping[category] = exact
            continue

        # 2. exakter Blattname
        leaf_matches = leaf_lookup.get(category.casefold(), [])
        if len(leaf_matches) == 1:
            mapping[category] = leaf_matches[0]
            continue
        if len(leaf_matches) > 1:
            ambiguous[category] = leaf_matches
            mapping[category] = None
            continue

        # 3. normalisierter Blattname
        norm_matches = normalized_lookup.get(
            normalize_folder_name(category),
            [],
        )

        if len(norm_matches) == 1:
            mapping[category] = norm_matches[0]
        elif len(norm_matches) > 1:
            ambiguous[category] = norm_matches
            mapping[category] = None
        else:
            mapping[category] = None
            missing.append(category)

    return mapping, missing, ambiguous
