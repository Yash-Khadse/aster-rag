import io
import zipfile
from pathlib import Path

import httpx

MAX_PDF_PAGES = 100  # matches the extraction limit in services/rag/parsing.py
MAX_XML_PART_BYTES = 10_000_000


def validate_upload(data: bytes, filename: str):
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".docx", ".txt", ".md", ".html", ".csv"}:
        raise ValueError("Supported formats: PDF, DOCX, TXT, Markdown, HTML and CSV")
    if not data or data.startswith(b"MZ"):
        raise ValueError("Empty or executable content is not allowed")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    if ext == ".pdf":
        from pypdf import PdfReader

        try:
            page_count = len(PdfReader(io.BytesIO(data)).pages)
        except Exception as exc:
            raise ValueError("Unreadable PDF") from exc
        if page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds {MAX_PDF_PAGES} pages")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
                if len(infos) > 1000 or sum(i.file_size for i in infos) > 30_000_000:
                    raise ValueError("Expanded archive exceeds limits")
                # Reject oversized XML parts and bomb-like compression ratios.
                if any(
                    i.file_size > MAX_XML_PART_BYTES
                    or (i.file_size > 1_000_000 and i.file_size > 100 * max(i.compress_size, 1))
                    for i in infos
                ):
                    raise ValueError("DOCX XML part exceeds size limits")
                if "word/document.xml" not in z.namelist() or any("vbaProject" in i.filename for i in infos):
                    raise ValueError("Invalid or macro-bearing DOCX")
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid DOCX archive") from exc
    if ext in {".txt", ".md", ".html", ".csv"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text documents must be UTF-8") from exc
        if "\x00" in text:
            raise ValueError("Binary data in text document")


class Storage:
    def __init__(self, settings):
        self.settings = settings
        self.root = Path(settings.data_dir).resolve() / "uploads"
        self.root.mkdir(parents=True, exist_ok=True)

    def local_path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid object key")
        return path

    def remote(self, method, key, data=None):
        s = self.settings
        url = f"{s.supabase_url.rstrip('/')}/storage/v1/object/{s.supabase_bucket}/{key}"
        response = httpx.request(
            method,
            url,
            content=data,
            timeout=60,
            headers={
                "Authorization": f"Bearer {s.supabase_service_key}",
                "apikey": s.supabase_service_key,
                "x-upsert": "true",
            },
        )
        if method == "DELETE" and response.status_code == 404:
            return b""
        response.raise_for_status()
        return response.content

    def put(self, key, data):
        if self.settings.storage_backend == "supabase":
            self.remote("POST", key, data)
        else:
            path = self.local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def get(self, key):
        return (
            self.remote("GET", key)
            if self.settings.storage_backend == "supabase"
            else self.local_path(key).read_bytes()
        )

    def delete(self, key):
        if self.settings.storage_backend == "supabase":
            self.remote("DELETE", key)
        else:
            self.local_path(key).unlink(missing_ok=True)
