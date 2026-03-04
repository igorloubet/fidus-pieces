# -*- coding: utf-8 -*-
"""
fidus-pieces — Extraction regex pour documents comptables suisses
==================================================================

Fonctions pures d'extraction de données structurées depuis du texte brut (OCR ou natif).
Zéro couplage DB/config — n'utilise que re, Decimal, datetime.

Fonctions exportées :
- extraire_basique() — extraction complète (date, IBAN, QR, montants, TVA, type)
- generer_mots_cles() — mots-clés fournisseur depuis le nom
- extraire_nom_crediteur_qr() — nom créancier depuis QR-slip suisse
- nom_coherent_avec_texte() — vérification nom↔texte OCR
- texte_necessite_ocr() — détection scan (texte insuffisant)
"""

import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation


def texte_necessite_ocr(texte: str, pages_fitz: list = None) -> bool:
    """Détecte si le texte embarqué est insuffisant et nécessite un OCR.

    Stratégie adaptative :
    - Texte trop court (<= 50 chars) → OCR nécessaire
    - Scan détecté (image pleine page >1000x1000) → toujours OCR
    - Texte natif sans image → PDF natif propre, pas d'OCR
    """
    if len(texte) <= 50:
        return True
    if not pages_fitz:
        return False
    for page in pages_fitz:
        imgs = page.get_images(full=True)
        for img in imgs:
            if img[2] > 1000 and img[3] > 1000:
                return True
    return False


def _parse_montant(raw: str) -> Decimal | None:
    """Parse un montant brut en Decimal, gère les formats suisses."""
    val = raw.replace("'", "").replace("\u2019", "").replace(" ", "")
    if ',' in val and '.' in val:
        if val.rindex(',') > val.rindex('.'):
            val = val.replace('.', '').replace(',', '.')
        else:
            val = val.replace(',', '')
    elif ',' in val:
        parts = val.split(',')
        if len(parts[-1]) == 2:
            val = val.replace(',', '.')
        else:
            val = val.replace(',', '')
    try:
        m = Decimal(val)
        return m if m > 0 else None
    except (InvalidOperation, ValueError):
        return None


def extraire_basique(texte: str) -> dict:
    """Extraction basique par regex — dates, IBAN, QR, montants, TVA, type document.

    Args:
        texte: Texte brut de la pièce (natif ou OCR)

    Returns:
        Dict avec les champs extraits
    """
    resultat = {
        'date_document': None,
        'iban': None,
        'reference_qr': None,
        'numero_document': None,
        'montant_ttc': None,
        'fournisseur': '',
        'type_document': 'autre',
        'numero_tva': None,
    }

    if not texte:
        return resultat

    # ── Date suisse (DD.MM.YYYY) ──
    dates = re.findall(r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b', texte)
    for d in dates:
        d_clean = d.replace('/', '.')
        parts = d_clean.split('.')
        try:
            from datetime import date as dt_date
            jour, mois, annee = int(parts[0]), int(parts[1]), int(parts[2])
            dt_date(annee, mois, jour)
            resultat['date_document'] = f"{annee:04d}-{mois:02d}-{jour:02d}"
            break
        except (ValueError, IndexError):
            continue

    # ── IBAN suisse (CH + 19 chars) ──
    iban_match = re.search(
        r'\b(CH\s?\d{2}\s?[\dA-Z]{4}\s?[\dA-Z]{4}\s?[\dA-Z]{4}\s?[\dA-Z]{4}\s?[\dA-Z])\b',
        texte, re.IGNORECASE
    )
    if iban_match:
        iban = re.sub(r'\s+', '', iban_match.group(1)).upper()
        if len(iban) == 21 and iban.startswith('CH'):
            resultat['iban'] = iban

    # ── Référence QR (27 chiffres) — 3 niveaux ──
    qr_found = None
    kw_qr = re.search(
        r'(?:R[ée]f[ée]rence|Referenz|Ref\.?)\s*:?\s*([\d\s]{20,40})',
        texte, re.IGNORECASE
    )
    if kw_qr:
        digits = re.sub(r'\s+', '', kw_qr.group(1))
        if len(digits) >= 27:
            digits = digits[:27]
        if len(digits) == 27 and digits.isdigit():
            qr_found = digits

    if not qr_found:
        qr_match = re.search(r'\b(\d{27})\b', texte)
        if qr_match:
            qr_found = qr_match.group(1)

    if not qr_found:
        for m in re.finditer(r'(\d{2,7}(?:\s{1,3}\d{2,7}){2,})', texte):
            digits = re.sub(r'\s+', '', m.group(1))
            if len(digits) == 27 and digits.isdigit():
                qr_found = digits
                break

    if qr_found:
        resultat['reference_qr'] = qr_found

    # ── Numéro de facture (FR/DE/EN) ──
    kw_facture = [
        r'Facture\s*N[°o.]?\s*:?\s*',
        r'N[°o.]\s*(?:de\s*)?facture\s*:?\s*',
        r'Rechnung(?:s)?[- ]?Nr\.?\s*:?\s*',
        r'Invoice\s*(?:No\.?|#|number)\s*:?\s*',
        r'Beleg[- ]?Nr\.?\s*:?\s*',
        r'Our\s*ref(?:erence)?\.?\s*:?\s*',
        r'Votre\s*r[ée]f[ée]rence\s*:?\s*',
        r'Notre\s*r[ée]f[ée]rence\s*:?\s*',
    ]
    num_pattern = r'([A-Za-z0-9][\w\-/\.]{2,19})'
    for kw in kw_facture:
        nm = re.search(kw + num_pattern, texte, re.IGNORECASE)
        if nm:
            candidat = nm.group(1).strip().rstrip('.')
            if len(re.findall(r'\d', candidat)) < 3:
                continue
            if re.fullmatch(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', candidat):
                continue
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', candidat):
                continue
            if candidat.upper().startswith('CHE'):
                continue
            resultat['numero_document'] = candidat
            break

    # ── Montants (TTC, HT, TVA) ──
    montant_pattern = r"(\d[\d''\u2019\s,]*?[\.,]\d{2})(?!\d)"

    # TTC
    kw_ttc = [
        r'Total\s+de\s+tous\s+les\s+services\s+et\s+livraisons\s*:?\s*(?:CHF\s*)?',
        r'Total\s+aller\s+Leistungen\s+und\s+Lieferungen\s*:?\s*(?:CHF\s*)?',
        r'Total\s*TTC\s*:?\s*(?:CHF\s*)?',
        r'Montant\s*TTC\s*(?:\w+\s*)?[,:;]?\s*(?:CHF\s*)?',
        r'Total\s*net\s*TVA\s*inclu[es]?\s*:?\s*(?:CHF\s*)?',
        r'Total\s*TVA\s*incl[.]?\s*:?\s*(?:CHF\s*)?',
        r'Gesamtpreis\s*:?\s*(?:CHF\s*)?',
        r'Gesamtbetrag\s*:?\s*(?:CHF\s*)?',
        r'Rechnungsbetrag\s*:?\s*(?:CHF\s*)?',
        r'Zu\s*zahlen\s*:?\s*(?:CHF\s*)?',
        r'Zahlbar\s*:?\s*(?:CHF\s*)?',
        r'Montant\s*total\s*(?:[àa]\s*payer\s*)?(?:en\s*)?(?:CHF\s*)?',
        r'Paiement\s+avant\s+[^:\n]{0,60}:\s*(?:CHF\s*)?',
        r'Montant\s+final\s*:?\s*(?:CHF\s*)?',
        r'Total\s+T\.?T\.?C\.?\s*:?\s*(?:CHF|EUR)?\s*',
        r'(?:TOTAL|MONTANT\s+(?:NET|TOTAL))\s*\((?:CHF|EUR)\)\s*',
        r'Montant\s+d[uû]\s*\((?:CHF|EUR)\)\s*',
    ]
    kw_ttc_generiques = [
        r'Total\s*(?:g[ée]n[ée]ral\s*)?:?\s*(?:CHF\s*)?',
        r'Montant\s*(?:total\s*)?:?\s*(?:CHF\s*)?',
        r'Sous-total\s*:?\s*(?:CHF\s*)?',
        r'Betrag\s*:?\s*(?:CHF\s*)?',
        r'Amount\s*:?\s*(?:CHF\s*)?',
    ]

    for kw in kw_ttc:
        m = re.search(kw + montant_pattern, texte, re.IGNORECASE)
        if m:
            montant = _parse_montant(m.group(1))
            if montant:
                resultat['montant_ttc'] = montant
                break

    if not resultat.get('montant_ttc'):
        candidats_ttc = []
        for kw in kw_ttc_generiques:
            for m in re.finditer(kw + montant_pattern, texte, re.IGNORECASE):
                montant = _parse_montant(m.group(1))
                if montant:
                    candidats_ttc.append(montant)
        if not candidats_ttc:
            for m in re.finditer(r'CHF\s*' + montant_pattern, texte, re.IGNORECASE):
                montant = _parse_montant(m.group(1))
                if montant:
                    candidats_ttc.append(montant)
        if not candidats_ttc:
            for m in re.finditer(montant_pattern + r'\s*(?:CHF|EUR|Fr\.?)\b', texte, re.IGNORECASE):
                montant = _parse_montant(m.group(1))
                if montant and montant >= Decimal('1'):
                    candidats_ttc.append(montant)
        if candidats_ttc:
            resultat['montant_ttc'] = max(candidats_ttc)

    # Cross-validation QR
    ttc = resultat.get('montant_ttc')
    qr_candidats = []
    for m in re.finditer(
        r'Monn\w+\s+Montant.{0,80}?(?:CHF|CHI|CHE|EUR)\s*' + montant_pattern,
        texte, re.IGNORECASE | re.DOTALL
    ):
        qr_val = _parse_montant(m.group(1))
        if qr_val and qr_val >= Decimal('1'):
            qr_candidats.append(qr_val)
    if qr_candidats:
        qr_montant = Counter(qr_candidats).most_common(1)[0][0]
        if ttc is None:
            resultat['montant_ttc'] = qr_montant
        elif ttc > qr_montant:
            s_ttc, s_qr = str(ttc), str(qr_montant)
            ratio = ttc / qr_montant
            if ratio > 2 and len(s_ttc) > 1 and len(s_qr) > 1 and s_ttc[1:] == s_qr[1:]:
                resultat['montant_ttc'] = qr_montant
            elif ratio <= 2:
                resultat['montant_ttc'] = qr_montant

    # HT
    kw_ht = [
        r'(?<!\bsur le )(?<!\bsur le montant )Total\s*HT\s*:?\s*(?:CHF\s*)?',
        r'Net\s*HT\s*:?\s*(?:CHF\s*)?',
        r'Montant\s*hors\s*taxes?\s*:?\s*(?:CHF\s*)?',
        r'Total\s*net\s*TVA\s*exclu[es]?\s*:?\s*(?:CHF\s*)?',
        r'Total\s*net\s*:?\s*(?:CHF\s*)?',
        r'MONTANT\s*NET\s*\(?(?:CHF)?\)?\s*',
        r'Positionsnetto\s*:?\s*',
        r'Nettobetrag\s*:?\s*(?:CHF\s*)?',
    ]
    for kw in kw_ht:
        m = re.search(kw + montant_pattern, texte, re.IGNORECASE)
        if m:
            montant = _parse_montant(m.group(1))
            if montant:
                resultat['montant_ht'] = montant
                break

    # TVA montant
    kw_tva_montant = [
        r'Total\s*TVA\s*:?\s*(?:CHF\s*)?',
        r'TVA\s+\d[\d.,]*\s*%\s*:?\s*(?:CHF\s*)?',
        r'TVA\s+\d[\d.,]*\s*%\s*(?:sur\s+[\d\s\'.,]+\s+)?',
        r'MWST\s+\d[\d.,]*\s*%\s*:?\s*(?:CHF\s*)?',
        r'MWST\s+\d[\d.,]*\s*%\s*',
    ]
    for kw in kw_tva_montant:
        m = re.search(kw + montant_pattern, texte, re.IGNORECASE)
        if m:
            montant = _parse_montant(m.group(1))
            if montant:
                if resultat.get('montant_ttc') and montant > resultat['montant_ttc'] * Decimal('0.15'):
                    continue
                if resultat.get('montant_ht') and montant >= resultat['montant_ht']:
                    continue
                if not resultat.get('montant_ttc') and not resultat.get('montant_ht'):
                    continue
                resultat['montant_tva'] = montant
                break

    # Déductions logiques
    ttc = resultat.get('montant_ttc')
    ht = resultat.get('montant_ht')
    tva_m = resultat.get('montant_tva')

    if ttc and ht:
        diff = ttc - ht
        if Decimal('0') < diff <= ttc * Decimal('0.15'):
            if tva_m and abs(tva_m - diff) > Decimal('1'):
                tva_m = diff
            elif not tva_m:
                tva_m = diff
            resultat['montant_tva'] = tva_m
    if not ttc and ht and tva_m:
        resultat['montant_ttc'] = ht + tva_m
    if ttc and not ht and tva_m:
        diff = ttc - tva_m
        if diff > 0:
            resultat['montant_ht'] = diff

    # ── N° TVA suisse ──
    tva_matches = re.findall(
        r'CHE[- ]?(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})\s*(?:TVA|MWST|IVA)?',
        texte, re.IGNORECASE
    )
    numeros_tva = []
    seen = set()
    for m in tva_matches:
        tva = f"CHE-{m[0]}.{m[1]}.{m[2]}"
        if tva not in seen:
            numeros_tva.append(tva)
            seen.add(tva)
    if numeros_tva:
        resultat['numero_tva'] = numeros_tva[0]
        resultat['numeros_tva'] = numeros_tva

    # ── Type document ──
    texte_lower = texte.lower()
    credit_kw = ['note de crédit', 'note de credit', 'avoir', 'gutschrift', 'credit note',
                 'remboursement', 'storno', 'ristourne', 'annulation facture']
    if any(k in texte_lower for k in credit_kw):
        resultat['type_document'] = 'credit_note'
    elif any(k in texte_lower for k in ['facture', 'invoice', 'rechnung']):
        resultat['type_document'] = 'facture'
    elif any(k in texte_lower for k in ['quittance', 'reçu', 'receipt', 'quittung']):
        resultat['type_document'] = 'quittance'
    elif any(k in texte_lower for k in ['relevé', 'auszug', 'statement']):
        resultat['type_document'] = 'releve'

    # ── Détection multi-TVA ──
    tva_rates_found = set()
    for m in re.finditer(r'(?:TVA|MwSt|MWST|VAT|IVA)\s*[:]?\s*(\d[.,]\d+)\s*%', texte, re.IGNORECASE):
        rate = m.group(1).replace(',', '.')
        if rate in {'8.1', '2.6', '3.8', '7.7'}:
            tva_rates_found.add(rate)
    for m in re.finditer(r'(\d[.,]\d{1,2})\s*%', texte):
        rate = m.group(1).replace(',', '.')
        if rate in {'8.1', '2.6', '3.8', '7.7', '8.10', '2.60', '3.80', '7.70'}:
            rate = rate.rstrip('0').rstrip('.')
            if rate in {'8.1', '2.6', '3.8', '7.7'}:
                tva_rates_found.add(rate)
    resultat['tva_rates_detected'] = sorted(tva_rates_found)
    resultat['multi_tva'] = len(tva_rates_found) > 1

    return resultat


def generer_mots_cles(nom: str) -> str:
    """Génère des mots-clés de recherche à partir du nom d'un fournisseur.

    Supprime les mots génériques (SA, AG, SARL, etc.) et retourne les termes
    significatifs en minuscules, séparés par virgule.
    """
    if not nom:
        return ''

    suffixes = {'sa', 'ag', 'sarl', 'sàrl', 'gmbh', 'srl', 'ltd', 'inc', 'bv',
                'se', 'co', 'cie', 'et', 'de', 'du', 'des', 'la', 'le', 'les',
                'the', 'der', 'die', 'das', 'von', 'und'}

    nom_lower = nom.lower().strip()
    nom_clean = re.sub(r'[.,()&/]', ' ', nom_lower)
    mots = [m.strip() for m in nom_clean.split() if m.strip()]
    mots_significatifs = [m for m in mots if m not in suffixes and len(m) > 1]

    if not mots_significatifs:
        return nom_lower

    nom_complet = ' '.join(mots_significatifs)
    keywords = [nom_complet]

    if len(mots_significatifs) > 2:
        keywords.append(' '.join(mots_significatifs[:2]))

    return ','.join(keywords)


def extraire_nom_crediteur_qr(texte: str) -> str | None:
    """Extrait le nom du créancier depuis la section paiement d'un QR-slip suisse."""
    if not texte:
        return None

    patterns_label = [
        r'(?:Konto\s*/\s*Zahlbar\s+an|Compte\s*/\s*Payable\s+[àa]|Conto\s*/\s*Pagabile\s+a)',
        r'(?:Zahlbar\s+an|Payable\s+[àa]|Pagabile\s+a)',
        r'(?:Zugunsten\s+von|En\s+faveur\s+de|A\s+favore\s+di)',
        r'Section\s+paiement',
    ]

    for pat in patterns_label:
        m = re.search(pat, texte, re.IGNORECASE)
        if not m:
            continue

        reste = texte[m.end():]
        lignes = [l.strip() for l in reste.split('\n') if l.strip()]

        for ligne in lignes[:6]:
            if re.match(r'^[*>]?\s*CH\s*\d', ligne) or re.match(r'^[*>]?\s*>\s*CH', ligne):
                continue
            if re.match(r'^[\d\s]{10,}$', ligne):
                continue
            if len(ligne) < 3:
                continue
            if re.match(r'^\d{4}\s', ligne):
                continue
            if re.match(r'^(R[ée]f[ée]rence|Payable par|Informations|Monnaie|Point de)', ligne, re.IGNORECASE):
                continue
            ligne = re.sub(r'^[*>\-_\s]+', '', ligne).strip()
            if len(ligne) >= 3:
                return ligne

    return None


def nom_coherent_avec_texte(nom_fournisseur: str, texte_ocr: str,
                            mots_client: set[str] | None = None) -> bool:
    """Vérifie qu'au moins un mot significatif du nom apparaît dans le texte OCR.

    Normalise les accents pour éviter les faux négatifs OCR.
    """
    def _noaccent(s: str) -> str:
        s = unicodedata.normalize('NFD', s)
        return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()

    texte_norm = _noaccent(texte_ocr)
    nom_norm = _noaccent(nom_fournisseur)
    mots = [m for m in re.findall(r'[a-z0-9]+', nom_norm) if len(m) >= 4]
    if not mots:
        return True

    if mots_client:
        mots_client_norm = {_noaccent(m) for m in mots_client}
        lignes_propres = []
        for line in texte_norm.split('\n'):
            line_words = set(re.findall(r'[a-z0-9]+', line))
            if not (line_words & mots_client_norm):
                lignes_propres.append(line)
        texte_norm = '\n'.join(lignes_propres)

    return any(m in texte_norm for m in mots)
