"""Bounded, traceable document extraction; optional OCR never runs at import time."""
from __future__ import annotations

import importlib
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from xml.etree import ElementTree
import zipfile

from .models import DocumentRead, SourceBlock

SUPPORTED_EXTENSIONS = {".txt", ".text", ".md", ".markdown", ".pdf", ".docx",
                        ".png", ".jpg", ".jpeg", ".webp"}
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_IMAGE_PIXELS = 30_000_000
MAX_TEXT_CHARS = 2_000_000
OCR_TIMEOUT = 45
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _optional(module: str):
    try:
        return importlib.import_module(module)
    except ImportError:
        raise ValueError(
            f"Reading this format requires {module}; install document support: "
            "pip install 'interview-forge[documents]' (from source: pip install '.[documents]')"
        ) from None


def read_document(path: str | Path, *, ocr_language: str = "chi_sim+eng", client=None,
                  ocr: str = "auto") -> DocumentRead:
    """Extract text with source locations. OCR modes: auto, local, vision, off.

    Auto uses Tesseract first, then the configured vision client if local OCR fails.
    A text PDF keeps its text layer; pages without text are individually OCRed.
    Missing text, dependencies, languages and partial PDF failures are explicit.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Document is not a regular file: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Document exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MiB file limit: {path.name}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported document format {suffix or '(none)'}; use TXT, MD, PDF, DOCX, PNG, JPEG or WebP")
    ocr = "local" if ocr == "on" else ocr
    if ocr not in {"auto", "local", "vision", "off"}:
        raise ValueError("ocr must be auto, local, vision, or off")
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", ocr_language):
        raise ValueError("ocr_language must contain language codes such as chi_sim+eng")

    if suffix in {".txt", ".text", ".md", ".markdown"}:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Text documents must be UTF-8; convert this file to UTF-8 first") from None
        if "\x00" in content:
            raise ValueError("Text document contains binary NUL bytes; provide UTF-8 text")
        result = DocumentRead(blocks=_text_blocks(content))
    elif suffix == ".docx":
        result = _read_docx(path)
    elif suffix == ".pdf":
        result = _read_pdf(path, ocr_language, client, ocr)
    else:
        with tempfile.TemporaryDirectory(prefix="interviewforge-ocr-") as temporary:
            normalized = Path(temporary) / "image.png"
            _normalize_image(path, normalized)
            text, method, messages = _ocr_image(normalized, ocr_language, client, ocr)
        result = DocumentRead(blocks=[SourceBlock(location="image:1", text=text, method=method)],
                              warnings=messages)
    result.blocks = [block for block in result.blocks if block.text.strip()]
    if not result.blocks:
        details = "; ".join(result.warnings)
        raise ValueError("No readable text found in document" + (f": {details}" if details else ""))
    if sum(len(block.text) for block in result.blocks) > MAX_TEXT_CHARS:
        raise ValueError(f"Extracted document exceeds the {MAX_TEXT_CHARS:,} character limit; split the document")
    return result


def _text_blocks(content: str) -> list[SourceBlock]:
    blocks = []
    start = 0
    paragraph = []
    for number, line in enumerate(content.splitlines(), 1):
        if line.strip():
            if not paragraph:
                start = number
            paragraph.append(line)
        elif paragraph:
            blocks.append(SourceBlock(location=f"lines:{start}-{number - 1}", text="\n".join(paragraph)))
            paragraph = []
    if paragraph:
        blocks.append(SourceBlock(location=f"lines:{start}-{start + len(paragraph) - 1}",
                                  text="\n".join(paragraph)))
    return blocks


def _paragraph_text(element) -> str:
    pieces = []
    for child in element.iter():
        if child.tag == _W + "t":
            pieces.append(child.text or "")
        elif child.tag == _W + "tab":
            pieces.append("\t")
        elif child.tag in {_W + "br", _W + "cr"}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _read_docx(path: Path) -> DocumentRead:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES or sum(item.file_size for item in entries) > MAX_ZIP_BYTES:
                raise ValueError("DOCX archive exceeds entry or expanded-size limits (100 MiB)")
            if len({item.filename for item in entries}) != len(entries):
                raise ValueError("DOCX contains duplicate archive entries")
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise ValueError("DOCX document XML exceeds the 16 MiB limit")
            # Read one entry in memory: never extract paths or open external relationships.
            xml = archive.read(info)
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError) as exc:
        raise ValueError(f"Cannot read DOCX document ({type(exc).__name__})") from None
    normalized_xml = xml.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in normalized_xml or b"<!ENTITY" in normalized_xml:
        raise ValueError("DOCX XML declarations with DTDs or entities are unsupported")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        raise ValueError("DOCX contains malformed document XML") from None
    body = root.find(_W + "body")
    blocks = []
    paragraph_number = table_number = 0
    for element in body if body is not None else []:
        if element.tag == _W + "p":
            paragraph_number += 1
            text = _paragraph_text(element)
            if text:
                blocks.append(SourceBlock(location=f"paragraph:{paragraph_number}", text=text, method="docx"))
        elif element.tag == _W + "tbl":
            table_number += 1
            for row_number, row in enumerate(element.findall(_W + "tr"), 1):
                cells = ["\n".join(filter(None, (_paragraph_text(p) for p in cell.findall(_W + "p"))))
                         for cell in row.findall(_W + "tc")]
                text = " | ".join(cells).strip()
                if any(cells):
                    blocks.append(SourceBlock(location=f"table:{table_number}/row:{row_number}",
                                              text=text, method="docx"))
    messages = []
    if any(item.filename.startswith("word/media/") for item in entries):
        messages.append("DOCX text and tables extracted; embedded images are not OCRed. Import those images or export a PDF to read them.")
    return DocumentRead(blocks=blocks, warnings=messages)


def _read_pdf(path: Path, language: str, client, ocr: str) -> DocumentRead:
    pypdf = _optional("pypdf")
    try:
        document = pypdf.PdfReader(str(path))
        if document.is_encrypted:
            raise ValueError("Encrypted PDF is unsupported; export an unlocked copy first")
        count = len(document.pages)
        if count > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit; split the document")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot open PDF ({type(exc).__name__})") from None
    blocks = []
    messages = []
    total_chars = 0
    for index, page in enumerate(document.pages):
        location = f"page:{index + 1}"
        try:
            content = (page.extract_text() or "").strip()
        except Exception as exc:
            content = ""
            messages.append(f"{location}: PDF text extraction failed ({type(exc).__name__}); trying OCR")
        method = "pdf-text"
        if not content:
            if ocr == "off":
                messages.append(f"{location}: no text layer; OCR is off. Enable local or vision OCR to read this page.")
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="interviewforge-pdf-") as temporary:
                    image_path = Path(temporary) / "page.png"
                    _render_pdf_page(path, index, image_path)
                    content, method, ocr_messages = _ocr_image(image_path, language, client, ocr)
                    messages.extend(f"{location}: {message}" for message in ocr_messages)
            except ValueError as exc:
                messages.append(f"{location}: {exc}")
                continue
        if content:
            total_chars += len(content)
            if total_chars > MAX_TEXT_CHARS:
                raise ValueError(f"Extracted PDF exceeds the {MAX_TEXT_CHARS:,} character limit; split the document")
            blocks.append(SourceBlock(location=location, text=content, method=method))
    return DocumentRead(blocks=blocks, warnings=messages)


def _normalize_image(source: Path, target: Path) -> None:
    Image = _optional("PIL.Image")
    ImageOps = _optional("PIL.ImageOps")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as original:
                if original.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Image content must be PNG, JPEG or WebP")
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise ValueError(f"Image exceeds the {MAX_IMAGE_PIXELS:,}-pixel limit")
                transposed = ImageOps.exif_transpose(original)
                image = transposed.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                background.save(target, "PNG")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot decode image ({type(exc).__name__})") from None


def _render_pdf_page(path: Path, index: int, target: Path) -> None:
    pdfium = _optional("pypdfium2")
    _optional("PIL.Image")
    try:
        with pdfium.PdfDocument(str(path)) as document:
            page = document[index]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(d) and d > 0 for d in (width, height)):
                    raise ValueError("PDF page has invalid dimensions")
                scale = min(2.5, math.sqrt(MAX_IMAGE_PIXELS / (width * height)))
                if scale < 0.25:
                    raise ValueError("PDF page dimensions exceed the rasterization limit")
                bitmap = page.render(scale=scale)
                try:
                    bitmap.to_pil().save(target, "PNG")
                finally:
                    bitmap.close()
            finally:
                page.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot render PDF page for OCR ({type(exc).__name__})") from None


def _tesseract(path: Path, language: str) -> str:
    executable = shutil.which("tesseract")
    if not executable:
        virtualenv_executable = Path(sys.prefix) / "bin" / "tesseract"
        if virtualenv_executable.is_file():
            executable = str(virtualenv_executable)
    if not executable:
        raise ValueError("Local OCR requires Tesseract. On Ubuntu install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng, or configure a vision model and use --ocr vision")
    try:
        listed = subprocess.run([executable, "--list-langs"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10, check=False)
        if listed.returncode:
            raise ValueError("Tesseract cannot list language data; check TESSDATA_PREFIX or use --ocr vision")
        available = set(listed.stdout.splitlines()[1:])
        missing = set(language.split("+")) - available
        if missing:
            raise ValueError(f"Tesseract language data missing: {', '.join(sorted(missing))}. Install tesseract-ocr-chi-sim / tesseract-ocr-eng as needed, or configure a vision model and use --ocr vision")
        result = subprocess.run([executable, str(path), "stdout", "-l", language], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=OCR_TIMEOUT, check=False)
        if result.returncode:
            raise ValueError("Tesseract OCR failed; check the image and installed language data, or use --ocr vision")
        content = result.stdout.strip()
        if not content:
            raise ValueError("Tesseract found no readable text; try a clearer image or --ocr vision")
        return content
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError(f"Tesseract unavailable or timed out ({type(exc).__name__}); try --ocr vision") from None


def _ocr_image(path: Path, language: str, client, ocr: str) -> tuple[str, str, list[str]]:
    if ocr == "off":
        raise ValueError("Image needs OCR but OCR is off; use --ocr auto, --ocr local, or --ocr vision")
    messages = []
    if ocr in {"auto", "local"}:
        try:
            return _tesseract(path, language), "ocr-tesseract", messages
        except ValueError as exc:
            if ocr == "local" or not callable(getattr(client, "transcribe_image", None)):
                raise
            messages.append(f"Local OCR unavailable: {exc}; used configured vision model")
    if not callable(getattr(client, "transcribe_image", None)):
        raise ValueError("Vision OCR requires a compatible vision model; set --provider compatible --base-url and --model, or install Tesseract and use --ocr local")
    try:
        content = client.transcribe_image(path, language=language)
    except Exception as exc:
        raise ValueError(f"Vision OCR failed ({type(exc).__name__}): {exc}") from None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Vision model returned no readable text; check the image and model vision support")
    return content.strip(), "ocr-vision", messages
