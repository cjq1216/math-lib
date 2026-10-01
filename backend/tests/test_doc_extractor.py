"""试卷文档文本提取引擎测试用例。"""

import io

import docx
import pypdf
import pytest

from app.services.doc_extractor import (
    DocumentExtractionError,
    extract_document_text,
)


def _create_mock_docx() -> bytes:
    doc = docx.Document()
    doc.add_heading("2026年八年级期末数学试卷", level=1)
    doc.add_paragraph("一、单项选择题")
    doc.add_paragraph("1. 已知 x + 1 = 0，求 x 的值。")
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "A. 1"
    t.rows[0].cells[1].text = "B. -1"
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


def _create_mock_pdf_with_text() -> bytes:
    writer = pypdf.PdfWriter()
    # 创建含文本注释或文本层的页面
    writer.add_blank_page(width=595, height=842)
    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()


def test_extract_docx():
    docx_bytes = _create_mock_docx()
    doc = extract_document_text("math_exam.docx", docx_bytes)
    assert doc.file_type == "docx"
    assert "2026年八年级期末数学试卷" in doc.content
    assert "一、单项选择题" in doc.content
    assert "1. 已知 x + 1 = 0，求 x 的值。" in doc.content
    assert "A. 1 | B. -1" in doc.content
    assert doc.total_chars > 20


def test_extract_text_utf8_and_gbk():
    utf8_text = "# 期中数学练习\n\n1. 若 a=1, b=2，求 a+b。"
    doc1 = extract_document_text("test.md", utf8_text.encode("utf-8"))
    assert doc1.file_type == "text"
    assert "期中数学练习" in doc1.content

    gbk_text = "几何综合试卷第一大题"
    doc2 = extract_document_text("test_gbk.txt", gbk_text.encode("gbk"))
    assert doc2.file_type == "text"
    assert "几何综合试卷第一大题" in doc2.content


def test_extract_scanned_pdf_intercepted():
    # 空白或无文字 PDF
    empty_pdf = _create_mock_pdf_with_text()
    with pytest.raises(DocumentExtractionError) as exc_info:
        extract_document_text("scan_test.pdf", empty_pdf)
    assert exc_info.value.code == "scanned_image_pdf"
    assert "纯扫描图片版" in exc_info.value.message


def test_unsupported_format_and_empty():
    with pytest.raises(DocumentExtractionError) as exc1:
        extract_document_text("archive.zip", b"PK12345")
    assert exc1.value.code == "unsupported_format"

    with pytest.raises(DocumentExtractionError) as exc2:
        extract_document_text("empty.txt", b"")
    assert exc2.value.code == "empty_file"
