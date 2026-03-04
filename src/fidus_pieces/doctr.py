# -*- coding: utf-8 -*-
"""
fidus-pieces — DocTR OCR Service (GPU)
========================================

OCR secondaire basé sur docTR (deep learning, GPU-accelerated).
Complémentaire à Tesseract : chaque moteur trouve des signaux différents.
Decoupled from any application config — all settings via constructor.
"""

import os
import gc
from typing import Optional

from PIL import Image


class DocTRService:
    """
    Service OCR docTR avec chargement paresseux du modèle.

    Modèles : db_resnet50 (détection) + crnn_vgg16_bn (reconnaissance).
    Batch processing sur GPU.
    """

    def __init__(self, batch_size: int = 10, dpi: int = 150):
        self.batch_size = batch_size
        self.dpi = dpi
        self._model = None
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Vérifie si docTR + torch sont installés et fonctionnels."""
        if self._available is not None:
            return self._available

        try:
            os.environ['DOCTR_MULTIPROCESSING_DISABLE'] = '1'
            import torch
            from doctr.models import ocr_predictor
            self._available = True
            print(f"  docTR: OK (torch={torch.__version__}, "
                  f"CUDA={'oui' if torch.cuda.is_available() else 'non'})")
        except Exception as e:
            print(f"  docTR: indisponible ({e})")
            self._available = False

        return self._available

    def _load_model(self):
        """Charge le modèle docTR au premier appel."""
        if self._model is not None:
            return

        os.environ['DOCTR_MULTIPROCESSING_DISABLE'] = '1'
        import torch
        from doctr.models import ocr_predictor

        use_gpu = torch.cuda.is_available()

        self._model = ocr_predictor(
            det_arch='db_resnet50',
            reco_arch='crnn_vgg16_bn',
            pretrained=True,
        )

        if use_gpu:
            self._model = self._model.cuda()

        device = 'GPU' if use_gpu else 'CPU'
        print(f"  docTR: modèle chargé ({device})")

    def ocr_batch(self, images: list[Image.Image]) -> list[str]:
        """OCR par batch sur une liste d'images PIL."""
        if not images:
            return []

        if not self.is_available():
            return [''] * len(images)

        self._load_model()

        import numpy as np
        from doctr.io import DocumentFile

        results = [''] * len(images)

        for batch_start in range(0, len(images), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(images))
            batch_imgs = images[batch_start:batch_end]

            try:
                import io
                bytes_list = []
                for img in batch_imgs:
                    buf = io.BytesIO()
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    max_dim = 5000
                    if max(img.size) > max_dim:
                        ratio = max_dim / max(img.size)
                        new_size = (int(img.width * ratio), int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                    img.save(buf, format='PNG')
                    bytes_list.append(buf.getvalue())

                doc = DocumentFile.from_images(bytes_list)
                result = self._model(doc)

                for page_idx, page in enumerate(result.pages):
                    lines = []
                    for block in page.blocks:
                        for line in block.lines:
                            words = [w.value for w in line.words]
                            lines.append(' '.join(words))
                    results[batch_start + page_idx] = '\n'.join(lines)

            except Exception as e:
                print(f"  docTR batch erreur [{batch_start}:{batch_end}]: {e}")

            gc.collect()

        return results

    def ocr_page_from_fitz(self, page, dpi: int = None) -> str:
        """OCR d'une page fitz.Page via docTR."""
        if not self.is_available():
            return ""

        try:
            import fitz
            dpi = dpi or self.dpi
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            results = self.ocr_batch([img])
            return results[0] if results else ""

        except Exception as e:
            print(f"  docTR page erreur: {e}")
            return ""
