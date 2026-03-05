# -*- coding: utf-8 -*-
"""
fidus-pieces — QR-bill decoder for Swiss payment slips
=======================================================

Decodes Swiss QR-bills (SPC format v0200) from PDF documents.
Uses zxing-cpp for barcode detection. Thread-safe, zero DB/config coupling.

Exported:
- parse_spc_payload() — parse raw QR text into structured dict
- decode_qr_from_pdf() — decode QR from a PDF file (last pages first)
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


def parse_spc_payload(raw: str) -> Optional[dict]:
    """Parse a Swiss QR-bill payload (SPC v0200 format).

    The SPC format is a fixed-order newline-separated text with ~31 fields.
    See: https://www.paymentstandards.ch/dam/downloads/ig-qr-bill-en.pdf

    Args:
        raw: Raw text content from QR code.

    Returns:
        Dict with keys: iban, amount, currency, creditor_name, reference, ref_type.
        None if not a valid SPC payload.
    """
    if not raw or not raw.strip().startswith("SPC"):
        return None

    lines = raw.strip().split("\n")
    # Minimum SPC payload has ~31 lines
    if len(lines) < 28:
        return None

    try:
        # SPC v0200 fixed indices:
        # [3]=IBAN, [5]=creditor name, [18]=amount, [19]=currency,
        # [27]=ref type (QRR/SCOR/NON), [28]=reference
        result = {
            'iban': lines[3].strip() if len(lines) > 3 else None,
            'creditor_name': lines[5].strip() if len(lines) > 5 else None,
            'currency': lines[19].strip() if len(lines) > 19 else None,
            'ref_type': lines[27].strip() if len(lines) > 27 else None,
            'reference': lines[28].strip() if len(lines) > 28 else None,
        }

        # Amount is at line 18 — may be empty (open amount)
        amount_str = lines[18].strip() if len(lines) > 18 else ""
        if amount_str:
            try:
                result['amount'] = Decimal(amount_str)
            except InvalidOperation:
                result['amount'] = None
        else:
            result['amount'] = None

        # Clean up empty strings
        for key in ('iban', 'creditor_name', 'reference', 'ref_type', 'currency'):
            if result.get(key) == '':
                result[key] = None

        # Validate IBAN format (CH/LI, 21 chars)
        iban = result.get('iban')
        if iban and not (len(iban) == 21 and iban[:2] in ('CH', 'LI')):
            result['iban'] = None

        # Validate reference: QRR = 27 digits, SCOR = structured creditor ref
        ref = result.get('reference')
        ref_type = result.get('ref_type')
        if ref and ref_type == 'QRR' and len(ref.replace(' ', '')) != 27:
            result['reference'] = None

        return result

    except (IndexError, ValueError):
        return None


def decode_qr_from_pdf(chemin_pdf: str, max_pages: int = 5,
                       dpi: int = 300) -> Optional[dict]:
    """Decode a Swiss QR-bill from a PDF file.

    Scans from the LAST page backwards (QR-slip is typically at the end).
    Returns the first valid SPC QR code found.

    Args:
        chemin_pdf: Path to the PDF file.
        max_pages: Maximum number of pages to scan (from the end).
        dpi: Resolution for PDF-to-image conversion.

    Returns:
        Parsed SPC dict (see parse_spc_payload), or None.
    """
    try:
        import zxingcpp
    except ImportError:
        logger.debug("zxingcpp not installed — QR decode disabled")
        return None

    try:
        import fitz  # PyMuPDF
        import numpy as np
    except ImportError:
        logger.debug("fitz or numpy not available — QR decode disabled")
        return None

    try:
        doc = fitz.open(chemin_pdf)
    except Exception:
        logger.debug("Cannot open PDF: %s", chemin_pdf)
        return None

    try:
        nb_pages = len(doc)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        # Scan from last page backwards
        pages_to_scan = range(nb_pages - 1, max(nb_pages - 1 - max_pages, -1), -1)

        for page_idx in pages_to_scan:
            try:
                pix = doc[page_idx].get_pixmap(matrix=mat)
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )

                # Convert RGBA to RGB if needed
                if pix.n == 4:
                    img_np = img_np[:, :, :3]

                barcodes = zxingcpp.read_barcodes(
                    img_np,
                    formats=zxingcpp.BarcodeFormat.QRCode,
                )

                for barcode in barcodes:
                    payload = barcode.text
                    result = parse_spc_payload(payload)
                    if result is not None:
                        return result

            except Exception:
                logger.debug("QR decode error on page %d of %s", page_idx, chemin_pdf)
                continue

    finally:
        doc.close()

    return None
