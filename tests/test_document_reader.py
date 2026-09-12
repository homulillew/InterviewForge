"""Document parsing, page provenance, OCR and vision transport integration."""
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread
from types import SimpleNamespace
import zipfile

import pytest

from interview_forge.llm import CompatibleClient
from interview_forge.materials import reader


def _image(path, *, chinese=False):
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")
    image = Image.new("RGB", (1500, 350), "white")
    font_path = (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc") if chinese
                 else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    if chinese and not font_path.exists():
        pytest.skip("Chinese OCR integration fixture needs Noto CJK font")
    font = ImageFont.truetype(str(font_path), 48) if font_path.exists() else ImageFont.load_default(size=40)
    content = ("技术面试记录\nRedis 缓存如何保证一致性？\n如何处理并发请求和库存超卖？" if chinese else
               "Interview question\nHow does Redis prevent overselling?\nExplain atomic updates and retries.")
    ImageDraw.Draw(image).multiline_text((40, 30), content, font=font, fill="black", spacing=20)
    image.save(path)
    return image


def _docx(path, content):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", content)


def _pdf(path, pages):
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = pypdf.PdfWriter()
    for text in pages:
        page = writer.add_blank_page(600, 800)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 16 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def test_utf8_paragraph_line_provenance_and_empty_failure(tmp_path):
    source = tmp_path / "面经.md"
    source.write_text("\ufeffRedis 面经\n问题：什么是原子性？\n\n追问：失败后回滚吗？\n", encoding="utf-8")
    document = reader.read_document(source)
    assert [(b.location, b.method) for b in document.blocks] == [("lines:1-2", "text"), ("lines:4-4", "text")]
    assert document.blocks[0].text.startswith("Redis")
    source.write_text("\n \n", encoding="utf-8")
    with pytest.raises(ValueError, match="No readable text"):
        reader.read_document(source)


def test_invalid_text_format_and_file_size_are_explicit(tmp_path, monkeypatch):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"\xff\xfe\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        reader.read_document(source)
    monkeypatch.setattr(reader, "MAX_FILE_BYTES", 2)
    with pytest.raises(ValueError, match="file limit"):
        reader.read_document(source)
    source = tmp_path / "macro.docm"
    source.write_bytes(b"a")
    with pytest.raises(ValueError, match="Unsupported"):
        reader.read_document(source)


def test_docx_preserves_paragraph_table_order_and_ignores_embedded_code(tmp_path):
    source = tmp_path / "reference.docx"
    _docx(source, '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>问题：缓存如何更新？</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>方案</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>先更新数据库</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:t>追问</w:t><w:tab/><w:t>删除失败怎么办？</w:t></w:r></w:p>
        </w:body></w:document>''')
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr("word/vbaProject.bin", "raise Exception('never execute')")
        archive.writestr("../outside.txt", "should never be extracted")
    document = reader.read_document(source)
    assert [b.location for b in document.blocks] == ["paragraph:1", "table:1/row:1", "paragraph:2"]
    assert document.blocks[1].text == "方案 | 先更新数据库"
    assert document.blocks[2].text == "追问\t删除失败怎么办？"
    assert not (tmp_path / "outside.txt").exists()


def test_docx_archive_and_xml_expansion_limits(tmp_path, monkeypatch):
    source = tmp_path / "large.docx"
    _docx(source, " " * 500)
    monkeypatch.setattr(reader, "MAX_ZIP_BYTES", 100)
    with pytest.raises(ValueError, match="expanded-size"):
        reader.read_document(source)
    monkeypatch.setattr(reader, "MAX_ZIP_BYTES", 10_000)
    _docx(source, '<!DOCTYPE x [<!ENTITY y "test">]><x>&y;</x>')
    with pytest.raises(ValueError, match="DTDs or entities"):
        reader.read_document(source)


def test_pdf_text_has_page_provenance_and_reports_unread_pages(tmp_path):
    source = tmp_path / "interview.pdf"
    _pdf(source, ["Why use Redis?", None, "How do retries work?"])
    document = reader.read_document(source, ocr="off")
    assert [b.location for b in document.blocks] == ["page:1", "page:3"]
    assert document.blocks[0].text == "Why use Redis?"
    assert all(b.method == "pdf-text" for b in document.blocks)
    assert "page:2" in document.warnings[0] and "OCR is off" in document.warnings[0]


def test_pdf_page_limit_and_empty_pdf_are_errors(tmp_path, monkeypatch):
    source = tmp_path / "blank.pdf"
    _pdf(source, [None, None])
    monkeypatch.setattr(reader, "MAX_PDF_PAGES", 1)
    with pytest.raises(ValueError, match="page limit"):
        reader.read_document(source)
    monkeypatch.setattr(reader, "MAX_PDF_PAGES", 100)
    with pytest.raises(ValueError, match="No readable text.*OCR is off"):
        reader.read_document(source, ocr="off")


def test_missing_optional_dependency_has_install_instruction(tmp_path, monkeypatch):
    source = tmp_path / "file.pdf"
    source.write_bytes(b"%PDF")
    def missing(name):
        raise ImportError(name)
    monkeypatch.setattr(reader.importlib, "import_module", missing)
    with pytest.raises(ValueError, match=r"pip install.*documents"):
        reader.read_document(source)


def test_image_modes_and_local_to_vision_fallback(tmp_path, monkeypatch):
    source = tmp_path / "screen.png"
    _image(source)
    def absent(*args):
        raise ValueError("missing chi_sim")
    monkeypatch.setattr(reader, "_tesseract", absent)
    received = []
    class Vision:
        def transcribe_image(self, path, *, language):
            received.append((Path(path).read_bytes()[:8], language))
            return "问题：Redis 如何防止超卖？"
    result = reader.read_document(source, client=Vision())
    assert result.blocks[0].method == "ocr-vision"
    assert result.blocks[0].location == "image:1"
    assert "missing chi_sim" in result.warnings[0]
    assert received == [(b"\x89PNG\r\n\x1a\n", "chi_sim+eng")]
    with pytest.raises(ValueError, match="OCR is off"):
        reader.read_document(source, ocr="off")
    with pytest.raises(ValueError, match="missing chi_sim"):
        reader.read_document(source, client=Vision(), ocr="local")
    with pytest.raises(ValueError, match="requires a compatible vision model"):
        reader.read_document(source, ocr="vision")


def test_empty_vision_and_invalid_image_are_not_success(tmp_path):
    source = tmp_path / "image.png"
    _image(source)
    client = SimpleNamespace(transcribe_image=lambda *args, **kwargs: "  ")
    with pytest.raises(ValueError, match="no readable text"):
        reader.read_document(source, client=client, ocr="vision")
    source.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Cannot decode image"):
        reader.read_document(source, client=client, ocr="vision")


def test_missing_tesseract_and_requested_language_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.shutil, "which", lambda command: None)
    monkeypatch.setattr(reader.sys, "prefix", str(tmp_path))
    with pytest.raises(ValueError, match="tesseract-ocr-chi-sim.*vision"):
        reader._tesseract(tmp_path / "image.png", "chi_sim+eng")
    monkeypatch.setattr(reader.shutil, "which", lambda command: "/mock/tesseract")
    monkeypatch.setattr(reader.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="List of available languages (1):\neng\n"))
    with pytest.raises(ValueError, match="language data missing: chi_sim"):
        reader._tesseract(tmp_path / "image.png", "chi_sim+eng")


def test_ocr_timeout_and_pixel_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.shutil, "which", lambda command: "/mock/tesseract")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 10)
    monkeypatch.setattr(reader.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timed out"):
        reader._tesseract(tmp_path / "image.png", "eng")
    source = tmp_path / "image.png"
    _image(source)
    monkeypatch.setattr(reader, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ValueError, match="pixel limit"):
        reader.read_document(source)


def test_real_chinese_image_and_scanned_pdf_ocr(tmp_path):
    """Actual OCR, skipped only when optional runtime/font dependencies are absent."""
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    executable = shutil.which("tesseract") or str(Path(sys.prefix) / "bin" / "tesseract")
    if not Path(executable).is_file():
        pytest.skip("Install Tesseract for OCR integration")
    languages = subprocess.run([executable, "--list-langs"], capture_output=True, text=True, timeout=10)
    if "chi_sim" not in languages.stdout or "eng" not in languages.stdout:
        pytest.skip("Install chi_sim+eng Tesseract data for Chinese OCR integration")
    source = tmp_path / "chinese.png"
    image = _image(source, chinese=True)
    image_result = reader.read_document(source, ocr="local")
    compact = "".join(image_result.blocks[0].text.split())
    assert "技术面试记录" in compact and "Redis" in compact and "库存超卖" in compact
    source = tmp_path / "scan.pdf"
    image.save(source, "PDF", resolution=150)
    pdf_result = reader.read_document(source, ocr="local")
    assert pdf_result.blocks[0].location == "page:1"
    assert pdf_result.blocks[0].method == "ocr-tesseract"
    assert "技术面试记录" in "".join(pdf_result.blocks[0].text.split())


def test_compatible_vision_uses_data_url_and_shared_local_transport(tmp_path, monkeypatch):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "面试问题"}}]}).encode())
    source = tmp_path / "question.png"
    source.write_bytes(b"fixture-image")
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    try:
        client = CompatibleClient(f"http://127.0.0.1:{server.server_port}/v1", "vision-model", api_key="")
        assert client.transcribe_image(source) == "面试问题"
        message = received[0]["messages"][1]
        url = message["content"][1]["image_url"]["url"]
        assert url == "data:image/png;base64," + base64.b64encode(b"fixture-image").decode()
        assert "chi_sim+eng" in message["content"][0]["text"]
        assert received[0]["model"] == "vision-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
