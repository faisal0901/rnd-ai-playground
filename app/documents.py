"""Turn an uploaded file into plain text, or say clearly why that is not possible.

Used twice: the knowledge-base page (the text is embedded and kept) and the chat attachment (the text is only
handed to the model for that conversation). Both need the same answer to "what does this file say?".
"""

import io
import re
from pathlib import PurePath

from app import config

TEXT_SUFFIXES = (".md", ".txt", ".csv", ".json", ".log")
SUPPORTED = (*TEXT_SUFFIXES, ".pdf")


class DocumentError(Exception):
    """A file we cannot use. ``status`` is the HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def safe_name(filename: str | None) -> str:
    """The file name as it will be stored: no folders, no odd characters. '../../etc/passwd' becomes 'passwd'."""
    name = PurePath((filename or "").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .")
    if not name:
        raise DocumentError("The file needs a name.", 400)
    path = PurePath(name)
    return path.stem[:100] + path.suffix  # long names are cut, but the extension is kept


def extract_text(name: str, data: bytes) -> str:
    suffix = PurePath(name).suffix.lower()
    if suffix not in SUPPORTED:
        raise DocumentError(f"'{suffix or name}' is not supported. Use: {', '.join(SUPPORTED)}.", 415)
    text = _pdf_text(data) if suffix == ".pdf" else _decode(data)
    text = text.replace("\x00", "").strip()
    if not text:
        hint = " A scanned PDF has no text layer; it needs OCR first." if suffix == ".pdf" else ""
        raise DocumentError("No text found in the file." + hint, 422)
    return text


def clip(text: str, limit: int = config.MAX_ATTACH_CHARS) -> tuple[str, bool]:
    """The text cut to ``limit`` characters, and whether anything was cut."""
    return (text[:limit], True) if len(text) > limit else (text, False)


def _decode(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise DocumentError("This looks like a binary file, not text.", 415)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # old Windows files


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # imported here: only PDF uploads need it

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("The PDF is password-protected.", 422)
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except DocumentError:
        raise
    except Exception as error:  # pypdf raises many different errors for a damaged file
        raise DocumentError(f"The PDF could not be read ({type(error).__name__}).", 422) from error
