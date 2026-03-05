# -*- coding: utf-8 -*-
"""Tests for fidus_pieces.qr_decoder — Swiss QR-bill decoding."""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from fidus_pieces.qr_decoder import parse_spc_payload, decode_qr_from_pdf


# ══════════════════════════════════════════════════════════════
# Standard SPC v0200 payload (31+ lines)
# ══════════════════════════════════════════════════════════════

# SPC v0200: 31 lines minimum (indices 0-30)
# Lines 11-17 = Ultimate Creditor (reserved, empty in v0200)
VALID_SPC_PAYLOAD = "\n".join([
    "SPC",                               # 0: QRType
    "0200",                              # 1: Version
    "1",                                 # 2: Coding
    "CH4431999123000889012",             # 3: IBAN
    "S",                                 # 4: Creditor addr type
    "Robert Schneider AG",              # 5: Creditor name
    "Rue du Lac",                        # 6: Street
    "1268",                              # 7: Building number
    "2501",                              # 8: Postal code
    "Biel",                              # 9: City
    "CH",                                # 10: Country
    "",                                  # 11: UltmtCdtr addr type (empty)
    "",                                  # 12: UltmtCdtr name (empty)
    "",                                  # 13: UltmtCdtr street (empty)
    "",                                  # 14: UltmtCdtr number (empty)
    "",                                  # 15: UltmtCdtr postal code (empty)
    "",                                  # 16: UltmtCdtr city (empty)
    "",                                  # 17: UltmtCdtr country (empty)
    "1949.75",                           # 18: Amount
    "CHF",                               # 19: Currency
    "S",                                 # 20: Debtor addr type
    "Pia-Maria Rutschmann-Schnyder",    # 21: Debtor name
    "Grosse Marktgasse",                 # 22: Street
    "28",                                # 23: Building number
    "9400",                              # 24: Postal code
    "Rorschach",                         # 25: City
    "CH",                                # 26: Country
    "QRR",                               # 27: Reference type
    "210000000003139471430009017",       # 28: Reference
    "EPD",                               # 29: Trailer
    "Facture 2026-001",                  # 30: Unstructured message
])

SPC_NO_AMOUNT = "\n".join([
    "SPC",                               # 0
    "0200",                              # 1
    "1",                                 # 2
    "CH4431999123000889012",             # 3
    "S",                                 # 4
    "Robert Schneider AG",              # 5
    "Rue du Lac",                        # 6
    "1268",                              # 7
    "2501",                              # 8
    "Biel",                              # 9
    "CH",                                # 10
    "", "", "", "", "", "", "",          # 11-17: UltmtCdtr (empty)
    "",                                  # 18: Amount (empty = open)
    "CHF",                               # 19
    "S",                                 # 20
    "Pia-Maria Rutschmann-Schnyder",    # 21
    "Grosse Marktgasse",                 # 22
    "28",                                # 23
    "9400",                              # 24
    "Rorschach",                         # 25
    "CH",                                # 26
    "QRR",                               # 27
    "210000000003139471430009017",       # 28
    "EPD",                               # 29
    "Facture open",                      # 30
])


# ══════════════════════════════════════════════════════════════
# parse_spc_payload
# ══════════════════════════════════════════════════════════════

class TestParseSpcPayload:
    def test_valid_payload(self):
        result = parse_spc_payload(VALID_SPC_PAYLOAD)
        assert result is not None
        assert result['iban'] == 'CH4431999123000889012'
        assert result['creditor_name'] == 'Robert Schneider AG'
        assert result['currency'] == 'CHF'
        assert result['ref_type'] == 'QRR'
        assert result['reference'] == '210000000003139471430009017'

    def test_amount_is_decimal(self):
        result = parse_spc_payload(VALID_SPC_PAYLOAD)
        assert isinstance(result['amount'], Decimal)
        assert result['amount'] == Decimal('1949.75')

    def test_invalid_not_spc(self):
        assert parse_spc_payload("NOT A QR CODE") is None
        assert parse_spc_payload("") is None
        assert parse_spc_payload(None) is None

    def test_too_few_lines(self):
        assert parse_spc_payload("SPC\n0200\n1") is None

    def test_no_amount(self):
        result = parse_spc_payload(SPC_NO_AMOUNT)
        assert result is not None
        assert result['amount'] is None
        assert result['iban'] == 'CH4431999123000889012'

    def test_payload_with_leading_whitespace(self):
        result = parse_spc_payload("  " + VALID_SPC_PAYLOAD)
        assert result is not None


# ══════════════════════════════════════════════════════════════
# decode_qr_from_pdf
# ══════════════════════════════════════════════════════════════

class TestDecodeQrFromPdf:
    def test_no_qr_returns_none(self, tmp_path):
        """PDF without QR code returns None."""
        import fitz
        pdf_path = str(tmp_path / "empty.pdf")
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 100), "No QR code here")
        doc.save(pdf_path)
        doc.close()

        result = decode_qr_from_pdf(pdf_path)
        assert result is None

    def test_nonexistent_file_returns_none(self):
        result = decode_qr_from_pdf("/nonexistent/file.pdf")
        assert result is None

    def test_graceful_no_zxing(self):
        """If zxingcpp is not importable, returns None gracefully."""
        with patch.dict('sys.modules', {'zxingcpp': None}):
            # Force reimport
            import importlib
            from fidus_pieces import qr_decoder
            importlib.reload(qr_decoder)
            result = qr_decoder.decode_qr_from_pdf("dummy.pdf")
            assert result is None
            # Restore
            importlib.reload(qr_decoder)
