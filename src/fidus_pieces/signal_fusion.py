# -*- coding: utf-8 -*-
"""
Camt & Go - Fusion de signaux OCR multi-moteurs
=================================================

Fusionne les résultats structurés de _extraire_basique() exécuté sur
le texte Tesseract ET le texte docTR indépendamment.

Stratégie : Signal Fusion (pas Text Fusion).
On ne mélange pas le texte brut — on merge les champs extraits.

Règles :
    - TVA, IBAN : UNION (chaque moteur trouve des valeurs différentes)
    - Montants, dates, QR, n° doc : fill gaps (Tesseract primaire, docTR complète)
    - Type document : Tesseract primaire, docTR si Tess dit 'autre'
"""

import re


def fusionner_tva_lists(tvas_tess: list[str], tvas_doctr: list[str]) -> list[str]:
    """
    Union des listes de numéros TVA normalisés, sans doublons.

    Args:
        tvas_tess: Numéros TVA trouvés par Tesseract
        tvas_doctr: Numéros TVA trouvés par docTR

    Returns:
        Liste union dédupliquée (ordre: Tesseract d'abord)
    """
    seen = set()
    result = []

    for tva in tvas_tess + tvas_doctr:
        # Normaliser : CHE-123.456.789 → CHE123456789
        normalized = re.sub(r'[\s.\-]', '', tva).upper()
        # Retirer suffixes TVA/MWST/IVA
        normalized = re.sub(r'(TVA|MWST|IVA)$', '', normalized)

        if normalized not in seen and len(normalized) >= 12:
            seen.add(normalized)
            # Remettre au format standard CHE-XXX.XXX.XXX
            if normalized.startswith('CHE') and len(normalized) == 12:
                formatted = f"CHE-{normalized[3:6]}.{normalized[6:9]}.{normalized[9:12]}"
            else:
                formatted = tva  # Garder le format original si atypique
            result.append(formatted)

    return result


def fusionner_iban_lists(ibans_tess: list[str], ibans_doctr: list[str]) -> list[str]:
    """
    Union des IBANs suisses normalisés, sans doublons.

    Args:
        ibans_tess: IBANs trouvés par Tesseract
        ibans_doctr: IBANs trouvés par docTR

    Returns:
        Liste union dédupliquée
    """
    seen = set()
    result = []

    for iban in ibans_tess + ibans_doctr:
        normalized = re.sub(r'\s+', '', iban).upper()
        if normalized not in seen and normalized.startswith('CH') and len(normalized) == 21:
            seen.add(normalized)
            result.append(normalized)

    return result


def fusionner_signaux(infos_tess: dict, infos_doctr: dict) -> dict:
    """
    Fusionne les résultats de _extraire_basique() de deux moteurs OCR.

    Tesseract est le moteur primaire. docTR complète les gaps.
    TVA et IBAN sont en mode UNION (les deux moteurs sont complémentaires).

    Args:
        infos_tess: Dict retourné par _extraire_basique(texte_tesseract)
        infos_doctr: Dict retourné par _extraire_basique(texte_doctr)

    Returns:
        Dict fusionné, compatible _extraire_basique() (mêmes clés)
    """
    if not infos_doctr:
        return infos_tess

    merged = dict(infos_tess)  # Copie — Tesseract est la base

    # ── UNION : TVA ──
    tvas_tess = infos_tess.get('numeros_tva', [])
    tvas_doctr = infos_doctr.get('numeros_tva', [])
    if tvas_tess or tvas_doctr:
        merged_tvas = fusionner_tva_lists(tvas_tess, tvas_doctr)
        if merged_tvas:
            merged['numeros_tva'] = merged_tvas
            merged['numero_tva'] = merged_tvas[0]

    # ── UNION : IBAN ──
    # _extraire_basique retourne un seul IBAN, construire des listes
    ibans_tess = [infos_tess['iban']] if infos_tess.get('iban') else []
    ibans_doctr = [infos_doctr['iban']] if infos_doctr.get('iban') else []
    if ibans_tess or ibans_doctr:
        merged_ibans = fusionner_iban_lists(ibans_tess, ibans_doctr)
        if merged_ibans:
            merged['iban'] = merged_ibans[0]
            merged['ibans'] = merged_ibans  # Tous les IBANs trouvés

    # ── FILL GAPS : montants (Tesseract primaire, docTR complète) ──
    for champ in ('montant_ttc', 'montant_ht', 'montant_tva'):
        if not merged.get(champ) and infos_doctr.get(champ):
            merged[champ] = infos_doctr[champ]

    # ── FILL GAPS : date ──
    if not merged.get('date_document') and infos_doctr.get('date_document'):
        merged['date_document'] = infos_doctr['date_document']

    # ── FILL GAPS : référence QR ──
    if not merged.get('reference_qr') and infos_doctr.get('reference_qr'):
        merged['reference_qr'] = infos_doctr['reference_qr']

    # ── FILL GAPS : numéro document ──
    if not merged.get('numero_document') and infos_doctr.get('numero_document'):
        merged['numero_document'] = infos_doctr['numero_document']

    # ── FILL GAPS : type document ──
    if merged.get('type_document', 'autre') == 'autre' and infos_doctr.get('type_document', 'autre') != 'autre':
        merged['type_document'] = infos_doctr['type_document']

    return merged
