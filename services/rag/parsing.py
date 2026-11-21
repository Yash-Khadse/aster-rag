"""Bounded, non-executing document extraction with source provenance."""

import csv
import io
import re
import zipfile
from pathlib import Path


class DocumentError(ValueError):
    pass


def parse_document(data: bytes, filename: str, unit_size: int = 900) -> list[dict]:
    if not data or len(data) > 10 * 1024 * 1024:
        raise DocumentError("Document must contain between 1 byte and 10 MiB")
    suffix = Path(filename).suffix.lower()
    pages = []
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentError("PDF signature does not match extension")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported")
        if len(reader.pages) > 100:
            raise DocumentError("Maximum 100 pages per document")
        ocr_pages = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text(extraction_mode="layout") or ""
            if not text.strip():
                from .ocr import ocr_pdf_page

                ocr_pages += 1
                if ocr_pages > 10:
                    raise DocumentError("Maximum 10 OCR pages per document")
                try:
                    text = ocr_pdf_page(data, number)
                except ValueError as exc:
                    raise DocumentError(str(exc)) from exc
            pages.append({"text": text, "page": number, "section": ""})
    elif suffix == ".docx":
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise DocumentError("DOCX must be a valid Office ZIP document")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(x.file_size for x in entries) > 40 * 1024 * 1024:
                raise DocumentError("Expanded document exceeds processing budget")
            if "word/document.xml" not in archive.namelist():
                raise DocumentError("Missing Word document content")
            if any("vbaproject" in x.filename.lower() for x in entries):
                raise DocumentError("Macro-bearing documents are not accepted")
        from docx import Document

        document = Document(io.BytesIO(data))
        # Merge consecutive paragraphs up to unit_size; a heading always starts a new unit (and section).
        heading, unit = "", []
        for block in document.iter_inner_content():
            is_heading = bool(
                hasattr(block, "text") and block.style and block.style.name.startswith("Heading")
            )
            if hasattr(block, "text"):
                text = block.text
            else:
                text = "\n".join(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            if not text.strip():
                continue
            if unit and (is_heading or len("\n".join(unit)) + 1 + len(text) > unit_size):
                pages.append({"text": "\n".join(unit), "page": None, "section": heading})
                unit = []
            if is_heading:
                heading = text
            unit.append(text)
        if unit:
            pages.append({"text": "\n".join(unit), "page": None, "section": heading})
    elif suffix in {".txt", ".md", ".markdown", ".html", ".htm", ".csv"}:
        if b"\x00" in data or data.startswith((b"MZ", b"%PDF", b"PK\x03\x04")):
            raise DocumentError("Binary content is not accepted as text")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text documents must use UTF-8 encoding") from exc
        if suffix in {".html", ".htm"}:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "iframe", "object", "embed"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
        elif suffix == ".csv":
            rows = list(csv.reader(io.StringIO(text)))
            if rows:
                headers = rows[0]
                text = "\n".join(
                    "; ".join(
                        f"{headers[i] if i < len(headers) else i}: {cell}" for i, cell in enumerate(row)
                    )
                    for row in rows[1:]
                )
        section = ""
        for block in re.split(r"\n(?=#{1,6}\s)", text):
            heading = re.match(r"^#{1,6}\s+([^\n]+)", block)
            if heading:
                section = heading.group(1)
            pages.append({"text": block, "page": None, "section": section})
    else:
        raise DocumentError("Supported formats: PDF, DOCX, TXT, Markdown, HTML, CSV")
    normalized = []
    total = 0
    for page in pages:
        text = page["text"].replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        total += len(text)
        if total > 2_000_000:
            raise DocumentError("Extracted text exceeds processing budget")
        if text:
            normalized.append({**page, "text": text, "parser_version": "1"})
    if not normalized:
        raise DocumentError("Document contains no extractable text")
    return normalized


def chunk_pages(
    pages: list[dict], strategy: str = "recursive", size: int = 900, overlap: int = 120
) -> list[dict]:
    if strategy not in {"recursive", "fixed", "structure"}:
        raise ValueError("Chunk strategy must be recursive, fixed or structure")
    if size < 100 or size > 8000 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid chunk size or overlap")
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, add_start_index=True)
    result = []
    for parent, page in enumerate(pages):
        if strategy == "fixed":
            pieces = [
                (page["text"][i : i + size], i, page["section"])
                for i in range(0, len(page["text"]), size - overlap)
            ]
        elif strategy == "structure":
            # Split at markdown headings first so no chunk spans two sections, then size-limit each section.
            pieces, position = [], 0
            for block in re.split(r"\n(?=#{1,6}\s)", page["text"]):
                heading = re.match(r"^#{1,6}\s+([^\n]+)", block)
                section = heading.group(1) if heading else page["section"]
                for d in splitter.create_documents([block]):
                    pieces.append((d.page_content, position + d.metadata["start_index"], section))
                position += len(block) + 1
        else:
            docs = splitter.create_documents([page["text"]])
            pieces = [(d.page_content, d.metadata["start_index"], page["section"]) for d in docs]
        for text, offset, section in pieces:
            if not text.strip():
                continue
            result.append(
                {
                    **page,
                    "section": section,
                    "text": text,
                    "chunk_index": len(result),
                    "parent_index": parent,
                    "start_offset": offset,
                    "chunking_strategy": strategy,
                    "chunking_version": "1",
                }
            )
    return result
