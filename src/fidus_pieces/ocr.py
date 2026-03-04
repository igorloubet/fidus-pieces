# -*- coding: utf-8 -*-
"""
fidus-pieces — OCR Service
===========================

Tesseract OCR (primary) with PaddleOCR fallback + parallel processing.
Decoupled from any application config — all settings via constructor.
"""

import os
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from PIL import Image


class OCRService:
    """
    Service OCR basé sur Tesseract (principal) avec fallback PaddleOCR.

    Extraction de texte depuis :
    - Images (PNG, JPG, TIFF)
    - Pages PDF (converties en images via PyMuPDF)
    """

    def __init__(self, lang: str = 'fr', dpi: int = 300,
                 parallel_workers: int = 8,
                 tessdata_prefix: str = None,
                 tesseract_path: str = None):
        """
        Args:
            lang: Langue OCR ('fr', 'en', 'de')
            dpi: Résolution par défaut pour conversion PDF→Image
            parallel_workers: Nombre de threads pour OCR parallèle
            tessdata_prefix: Chemin vers tessdata/ (optionnel)
            tesseract_path: Chemin vers tesseract.exe (optionnel)
        """
        self.lang = lang
        self.dpi = dpi
        self.parallel_workers = parallel_workers
        self._tessdata_prefix = tessdata_prefix
        self._tesseract_path = tesseract_path
        self._tesseract_ok = None

    def _init_tesseract(self) -> bool:
        """Vérifie et configure Tesseract au premier appel."""
        if self._tesseract_ok is not None:
            return self._tesseract_ok

        try:
            import pytesseract

            # Chemin Tesseract personnalisé ou par défaut Windows
            tesseract_path = self._tesseract_path or r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

            # Tessdata personnalisé
            if self._tessdata_prefix and os.path.isdir(self._tessdata_prefix):
                os.environ['TESSDATA_PREFIX'] = self._tessdata_prefix

            # Test rapide
            pytesseract.get_tesseract_version()
            self._tesseract_ok = True
            print("  OCR: Tesseract OK")

        except Exception as e:
            print(f"  OCR: Tesseract indisponible ({e}), fallback PaddleOCR")
            self._tesseract_ok = False

        return self._tesseract_ok

    def _tesseract_lang(self) -> str:
        """Convertit le code langue pour Tesseract."""
        mapping = {'fr': 'fra+eng', 'en': 'eng', 'de': 'deu+eng'}
        return mapping.get(self.lang, 'fra+eng')

    def extraire_texte_image(self, chemin_image: str) -> str:
        """Extrait le texte d'une image."""
        if not os.path.exists(chemin_image):
            return ""
        if self._init_tesseract():
            return self._ocr_tesseract_image(chemin_image)
        else:
            return self._ocr_paddle_image(chemin_image)

    def _ocr_tesseract_image(self, chemin_image: str) -> str:
        """OCR via Tesseract sur une image."""
        try:
            import pytesseract
            img = Image.open(chemin_image)
            texte = pytesseract.image_to_string(img, lang=self._tesseract_lang())
            return texte.strip()
        except Exception as e:
            print(f"Erreur Tesseract image : {e}")
            return ""

    def _ocr_tesseract_pil(self, img: Image.Image) -> str:
        """OCR via Tesseract sur un objet PIL Image."""
        try:
            import pytesseract
            texte = pytesseract.image_to_string(img, lang=self._tesseract_lang())
            return texte.strip()
        except Exception as e:
            print(f"Erreur Tesseract PIL : {e}")
            return ""

    def _ocr_paddle_image(self, chemin_image: str) -> str:
        """OCR fallback via PaddleOCR sur une image."""
        try:
            os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
            os.environ['FLAGS_use_mkldnn'] = '0'
            import paddle
            paddle.set_flags({'FLAGS_use_mkldnn': 0})

            from paddleocr import PaddleOCR
            ocr = PaddleOCR(lang=self.lang, enable_mkldnn=False)
            resultats = list(ocr.predict(chemin_image))

            if not resultats:
                return ""

            lignes = []
            for r in resultats:
                rec_texts = r.get('rec_texts', [])
                lignes.extend(rec_texts)

            return "\n".join(lignes)

        except Exception as e:
            print(f"Erreur PaddleOCR image : {e}")
            return ""

    def ocr_page_from_fitz(self, page, dpi: int = 150) -> str:
        """OCR rapide sur un objet fitz.Page."""
        try:
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            if self._init_tesseract():
                return self._ocr_tesseract_pil(img)
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp_path = tmp.name
                    img.save(tmp_path)
                try:
                    return self._ocr_paddle_image(tmp_path)
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

        except Exception as e:
            print(f"Erreur OCR page fitz : {e}")
            return ""

    def extraire_texte_pdf_page(self, chemin_pdf: str, page_num: int = 0) -> str:
        """Extrait le texte d'une page PDF via OCR."""
        if not os.path.exists(chemin_pdf):
            return ""

        try:
            doc = fitz.open(chemin_pdf)
            if page_num >= len(doc):
                doc.close()
                return ""

            page = doc[page_num]
            zoom = self.dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            if self._init_tesseract():
                return self._ocr_tesseract_pil(img)
            else:
                temp_path = chemin_pdf + f"_page{page_num}_temp.png"
                try:
                    img.save(temp_path)
                    return self._ocr_paddle_image(temp_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

        except Exception as e:
            print(f"Erreur OCR page PDF : {e}")
            return ""

    def extraire_texte_pdf_complet(self, chemin_pdf: str) -> list[dict]:
        """Extrait le texte de toutes les pages d'un PDF (séquentiel)."""
        if not os.path.exists(chemin_pdf):
            return []

        resultats = []
        try:
            doc = fitz.open(chemin_pdf)
            for page_num in range(len(doc)):
                page = doc[page_num]
                texte_natif = page.get_text("text").strip()
                if len(texte_natif) > 50:
                    resultats.append({
                        'page': page_num + 1,
                        'texte': texte_natif,
                        'methode': 'natif'
                    })
                else:
                    texte_ocr = self.extraire_texte_pdf_page(chemin_pdf, page_num)
                    resultats.append({
                        'page': page_num + 1,
                        'texte': texte_ocr or texte_natif,
                        'methode': 'ocr' if texte_ocr else 'natif_faible'
                    })
            doc.close()
        except Exception as e:
            print(f"Erreur OCR PDF : {e}")

        return resultats

    def _ocr_single_page_from_pdf(self, chemin_pdf: str, page_idx: int,
                                    dpi: int = 150) -> tuple[int, str]:
        """OCR d'une page en ouvrant son propre fitz.Document (thread-safe)."""
        try:
            doc = fitz.open(chemin_pdf)
            if page_idx >= len(doc):
                doc.close()
                return (page_idx, "")
            page = doc[page_idx]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            if self._init_tesseract():
                return (page_idx, self._ocr_tesseract_pil(img))
            else:
                return (page_idx, "")
        except Exception as e:
            print(f"Erreur OCR parallele page {page_idx}: {e}")
            return (page_idx, "")

    def ocr_pages_parallel(self, chemin_pdf: str, page_indices: list[int],
                           dpi: int = 150,
                           max_workers: int = None) -> dict[int, str]:
        """OCR parallèle de plusieurs pages d'un PDF."""
        if not page_indices:
            return {}

        if max_workers is None:
            max_workers = self.parallel_workers

        if len(page_indices) <= 2:
            results = {}
            for idx in page_indices:
                _, texte = self._ocr_single_page_from_pdf(chemin_pdf, idx, dpi)
                results[idx] = texte
            return results

        results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._ocr_single_page_from_pdf, chemin_pdf, idx, dpi
                ): idx
                for idx in page_indices
            }
            for future in as_completed(futures):
                try:
                    page_idx, texte = future.result()
                    results[page_idx] = texte
                except Exception as e:
                    page_idx = futures[future]
                    print(f"Erreur OCR parallele page {page_idx}: {e}")
                    results[page_idx] = ""

        return results

    def extraire_texte_pdf_complet_parallel(self, chemin_pdf: str,
                                             dpi: int = None) -> list[dict]:
        """Extrait le texte de toutes les pages d'un PDF, avec OCR parallèle."""
        if not os.path.exists(chemin_pdf):
            return []

        dpi = dpi or self.dpi

        try:
            doc = fitz.open(chemin_pdf)
            nb_pages = len(doc)

            resultats = [None] * nb_pages
            pages_a_ocr = []

            for i in range(nb_pages):
                texte_natif = doc[i].get_text("text").strip()
                if len(texte_natif) > 50:
                    resultats[i] = {
                        'page': i + 1,
                        'texte': texte_natif,
                        'methode': 'natif',
                    }
                else:
                    pages_a_ocr.append((i, texte_natif))

            doc.close()

            if pages_a_ocr:
                indices = [p[0] for p in pages_a_ocr]
                textes_natifs = {p[0]: p[1] for p in pages_a_ocr}
                ocr_results = self.ocr_pages_parallel(chemin_pdf, indices, dpi=dpi)

                for idx in indices:
                    texte_ocr = ocr_results.get(idx, "")
                    texte_natif = textes_natifs[idx]
                    resultats[idx] = {
                        'page': idx + 1,
                        'texte': texte_ocr or texte_natif,
                        'methode': 'ocr' if texte_ocr else 'natif_faible',
                    }

            return resultats

        except Exception as e:
            print(f"Erreur OCR PDF parallele : {e}")
            return []

    def compter_pages_pdf(self, chemin_pdf: str) -> int:
        """Compte le nombre de pages d'un PDF."""
        try:
            doc = fitz.open(chemin_pdf)
            nb = len(doc)
            doc.close()
            return nb
        except Exception:
            return 0
