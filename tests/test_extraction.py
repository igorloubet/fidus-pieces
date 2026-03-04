# -*- coding: utf-8 -*-
"""Tests for fidus_pieces.extraction — Swiss document regex extraction."""

import pytest
from decimal import Decimal

from fidus_pieces.extraction import (
    extraire_basique,
    generer_mots_cles,
    extraire_nom_crediteur_qr,
    nom_coherent_avec_texte,
    texte_necessite_ocr,
    _parse_montant,
)


# ══════════════════════════════════════════════════════════════
# _parse_montant
# ══════════════════════════════════════════════════════════════

class TestParseMontant:
    def test_simple_amount(self):
        assert _parse_montant("1234.56") == Decimal("1234.56")

    def test_swiss_apostrophe(self):
        assert _parse_montant("1'234.56") == Decimal("1234.56")

    def test_comma_decimal(self):
        assert _parse_montant("1234,56") == Decimal("1234.56")

    def test_european_format(self):
        """1.234,56 = 1234.56 in European format."""
        assert _parse_montant("1.234,56") == Decimal("1234.56")

    def test_zero_returns_none(self):
        assert _parse_montant("0.00") is None

    def test_negative_returns_none(self):
        assert _parse_montant("-5.00") is None

    def test_garbage_returns_none(self):
        assert _parse_montant("abc") is None


# ══════════════════════════════════════════════════════════════
# extraire_basique
# ══════════════════════════════════════════════════════════════

class TestExtraireBasique:
    def test_empty_text(self):
        r = extraire_basique("")
        assert r['date_document'] is None
        assert r['montant_ttc'] is None
        assert r['type_document'] == 'autre'

    def test_none_text(self):
        r = extraire_basique(None)
        assert r['date_document'] is None

    def test_date_swiss(self):
        r = extraire_basique("Facture du 15.03.2026")
        assert r['date_document'] == '2026-03-15'

    def test_date_slash(self):
        r = extraire_basique("Date: 01/12/2025")
        assert r['date_document'] == '2025-12-01'

    def test_iban_swiss(self):
        r = extraire_basique("IBAN: CH93 0076 2011 6238 5295 7")
        assert r['iban'] == 'CH9300762011623852957'

    def test_qr_reference_27digits(self):
        r = extraire_basique("Référence: 210000000003139471430009017")
        assert r['reference_qr'] == '210000000003139471430009017'

    def test_montant_ttc_keyword(self):
        r = extraire_basique("Total TTC: CHF 1'234.56")
        assert r['montant_ttc'] == Decimal("1234.56")

    def test_montant_chf_suffix(self):
        r = extraire_basique("Montant 500.00 CHF à payer")
        assert r['montant_ttc'] == Decimal("500.00")

    def test_numero_tva(self):
        r = extraire_basique("N° TVA: CHE-123.456.789 TVA")
        assert r['numero_tva'] == 'CHE-123.456.789'

    def test_multiple_tva(self):
        r = extraire_basique("CHE-111.222.333 TVA et CHE-444.555.666 MWST")
        assert len(r['numeros_tva']) == 2

    def test_type_facture(self):
        r = extraire_basique("FACTURE N° 2026-001")
        assert r['type_document'] == 'facture'

    def test_type_credit_note(self):
        r = extraire_basique("Note de crédit NC-001")
        assert r['type_document'] == 'credit_note'

    def test_numero_document(self):
        r = extraire_basique("Facture N° 2026-00142")
        assert r['numero_document'] == '2026-00142'

    def test_multi_tva_detection(self):
        r = extraire_basique("TVA 8.1% sur 1000.00\nTVA 2.6% sur 500.00")
        assert r['multi_tva'] is True
        assert '8.1' in r['tva_rates_detected']
        assert '2.6' in r['tva_rates_detected']

    def test_montant_deduction_ht_tva(self):
        """TTC = HT + TVA when TTC missing."""
        r = extraire_basique("Total HT: 100.00\nTotal TVA: 8.10\nFacture")
        assert r['montant_ht'] == Decimal("100.00")
        # TTC should be deduced
        assert r['montant_ttc'] == Decimal("108.10")


# ══════════════════════════════════════════════════════════════
# generer_mots_cles
# ══════════════════════════════════════════════════════════════

class TestGenererMotsCles:
    def test_simple_name(self):
        kw = generer_mots_cles("Swisscom AG")
        assert "swisscom" in kw

    def test_removes_suffixes(self):
        kw = generer_mots_cles("Dupont SA")
        assert "sa" not in kw.split(',')[0].split()

    def test_multi_word(self):
        kw = generer_mots_cles("Fischer Connectors SA")
        parts = kw.split(',')
        assert "fischer connectors" in parts[0]

    def test_empty(self):
        assert generer_mots_cles("") == ''
        assert generer_mots_cles(None) == ''


# ══════════════════════════════════════════════════════════════
# extraire_nom_crediteur_qr
# ══════════════════════════════════════════════════════════════

class TestExtraireNomCrediteurQr:
    def test_payable_a(self):
        texte = "Compte / Payable à\nCH44 3199 9123 0008 8901 2\nSwisscom (Schweiz) AG\n3050 Bern"
        nom = extraire_nom_crediteur_qr(texte)
        assert nom == "Swisscom (Schweiz) AG"

    def test_zahlbar_an(self):
        texte = "Zahlbar an\nCH93 0076 2011 6238 5295 7\nMeier GmbH\n8001 Zürich"
        nom = extraire_nom_crediteur_qr(texte)
        assert nom == "Meier GmbH"

    def test_empty(self):
        assert extraire_nom_crediteur_qr("") is None
        assert extraire_nom_crediteur_qr(None) is None

    def test_no_match(self):
        assert extraire_nom_crediteur_qr("Some random text without QR section") is None


# ══════════════════════════════════════════════════════════════
# nom_coherent_avec_texte
# ══════════════════════════════════════════════════════════════

class TestNomCoherentAvecTexte:
    def test_name_found(self):
        assert nom_coherent_avec_texte("Swisscom AG", "Facture Swisscom Fixnet") is True

    def test_name_not_found(self):
        assert nom_coherent_avec_texte("Sunrise AG", "Facture Swisscom Fixnet") is False

    def test_accent_insensitive(self):
        assert nom_coherent_avec_texte("Défago Services", "facture defago pour travaux") is True

    def test_short_words_ignored(self):
        """Words < 4 chars are ignored → always True if no significant words."""
        assert nom_coherent_avec_texte("SA AG", "random text") is True

    def test_client_exclusion(self):
        """Client words should be excluded from the OCR text."""
        # "oxmetal" is a client word → the line containing it is excluded
        texte = "Payable par\nOxmetal Serrurerie & Construction\nFacture Debrunner"
        assert nom_coherent_avec_texte("Debrunner Acifer", texte, mots_client={"Oxmetal"}) is True


# ══════════════════════════════════════════════════════════════
# texte_necessite_ocr
# ══════════════════════════════════════════════════════════════

class TestTexteNecessiteOcr:
    def test_short_text(self):
        assert texte_necessite_ocr("abc") is True

    def test_sufficient_text_no_pages(self):
        assert texte_necessite_ocr("x" * 100) is False

    def test_empty(self):
        assert texte_necessite_ocr("") is True
