"""Opt-in CPU OCR through installed Poppler and Tesseract, with bounded subprocesses."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def ocr_pdf_page(data: bytes, page: int) -> str:
    if os.getenv("OCR_ENABLED", "false").lower() != "true":
        raise ValueError(f"Page {page} requires OCR; enable OCR and install Poppler/Tesseract")
    poppler = shutil.which(os.getenv("PDFTOPPM_PATH", "pdftoppm"))
    tesseract = shutil.which(os.getenv("TESSERACT_PATH", "tesseract"))
    if not poppler or not tesseract:
        raise ValueError("OCR is enabled but Poppler or Tesseract is unavailable")
    with tempfile.TemporaryDirectory(prefix="rag-ocr-") as directory:
        source = Path(directory) / "source.pdf"
        target = Path(directory) / "page"
        source.write_bytes(data)
        subprocess.run(
            [
                poppler,
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                "120",
                "-scale-to",
                "2400",
                "-singlefile",
                "-png",
                str(source),
                str(target),
            ],
            check=True,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        image = target.with_suffix(".png")
        if not image.exists() or image.stat().st_size > 20_000_000:
            raise ValueError("OCR raster exceeds processing limits")
        response = subprocess.run(
            [tesseract, str(image), "stdout", "-l", os.getenv("OCR_LANGUAGE", "eng")],
            check=True,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        text = response.stdout.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError(f"OCR produced no readable text for page {page}")
        return text
