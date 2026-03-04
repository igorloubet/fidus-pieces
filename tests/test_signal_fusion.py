# -*- coding: utf-8 -*-
"""Tests for fidus_pieces.signal_fusion — multi-engine OCR signal merging."""

from decimal import Decimal

from fidus_pieces.signal_fusion import (
    fusionner_signaux,
    fusionner_tva_lists,
    fusionner_iban_lists,
)


# ══════════════════════════════════════════════════════════════
# fusionner_tva_lists
# ══════════════════════════════════════════════════════════════

class TestFusionnerTvaLists:
    def test_union(self):
        tess = ["CHE-111.222.333"]
        doctr = ["CHE-444.555.666"]
        result = fusionner_tva_lists(tess, doctr)
        assert len(result) == 2
        assert "CHE-111.222.333" in result
        assert "CHE-444.555.666" in result

    def test_dedup(self):
        tess = ["CHE-111.222.333"]
        doctr = ["CHE 111 222 333"]  # Same number, different format
        result = fusionner_tva_lists(tess, doctr)
        assert len(result) == 1

    def test_empty(self):
        assert fusionner_tva_lists([], []) == []

    def test_normalization(self):
        result = fusionner_tva_lists(["CHE-111.222.333 TVA"], [])
        assert result == ["CHE-111.222.333"]


# ══════════════════════════════════════════════════════════════
# fusionner_iban_lists
# ══════════════════════════════════════════════════════════════

class TestFusionnerIbanLists:
    def test_union(self):
        result = fusionner_iban_lists(
            ["CH9300762011623852957"],
            ["CH3908704016075473007"]
        )
        assert len(result) == 2

    def test_dedup_spaces(self):
        result = fusionner_iban_lists(
            ["CH9300762011623852957"],
            ["CH93 0076 2011 6238 5295 7"]
        )
        assert len(result) == 1

    def test_rejects_non_swiss(self):
        result = fusionner_iban_lists(["DE89370400440532013000"], [])
        assert len(result) == 0

    def test_empty(self):
        assert fusionner_iban_lists([], []) == []


# ══════════════════════════════════════════════════════════════
# fusionner_signaux
# ══════════════════════════════════════════════════════════════

class TestFusionnerSignaux:
    def _base_infos(self, **overrides):
        """Create a base extraction result dict."""
        base = {
            'date_document': None,
            'iban': None,
            'reference_qr': None,
            'numero_document': None,
            'montant_ttc': None,
            'fournisseur': '',
            'type_document': 'autre',
            'numero_tva': None,
        }
        base.update(overrides)
        return base

    def test_fill_gaps_montant(self):
        tess = self._base_infos()
        doctr = self._base_infos(montant_ttc=Decimal("123.45"))
        merged = fusionner_signaux(tess, doctr)
        assert merged['montant_ttc'] == Decimal("123.45")

    def test_tesseract_primary(self):
        """Tesseract value wins when both have data."""
        tess = self._base_infos(montant_ttc=Decimal("100.00"))
        doctr = self._base_infos(montant_ttc=Decimal("200.00"))
        merged = fusionner_signaux(tess, doctr)
        assert merged['montant_ttc'] == Decimal("100.00")

    def test_fill_gaps_date(self):
        tess = self._base_infos()
        doctr = self._base_infos(date_document="2026-01-15")
        merged = fusionner_signaux(tess, doctr)
        assert merged['date_document'] == "2026-01-15"

    def test_tva_union(self):
        tess = self._base_infos(numeros_tva=["CHE-111.222.333"])
        doctr = self._base_infos(numeros_tva=["CHE-444.555.666"])
        merged = fusionner_signaux(tess, doctr)
        assert len(merged['numeros_tva']) == 2

    def test_iban_union(self):
        tess = self._base_infos(iban="CH9300762011623852957")
        doctr = self._base_infos(iban="CH3908704016075473007")
        merged = fusionner_signaux(tess, doctr)
        assert len(merged.get('ibans', [])) == 2

    def test_type_fallback(self):
        tess = self._base_infos(type_document='autre')
        doctr = self._base_infos(type_document='facture')
        merged = fusionner_signaux(tess, doctr)
        assert merged['type_document'] == 'facture'

    def test_none_doctr(self):
        tess = self._base_infos(montant_ttc=Decimal("50.00"))
        merged = fusionner_signaux(tess, None)
        assert merged['montant_ttc'] == Decimal("50.00")

    def test_all_none(self):
        tess = self._base_infos()
        doctr = self._base_infos()
        merged = fusionner_signaux(tess, doctr)
        assert merged['montant_ttc'] is None
        assert merged['date_document'] is None
