"""Unit tests for document and PDF extraction."""

import pytest

from openpath.exceptions import ExtractionError
from openpath.extraction.documents import extract_pdf_text_safe


def test_extract_pdf_text_safe_valid() -> None:
    # Minimal synthetic PDF content with 1 page and BT / ET text
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
        b"stream\nBT\n/F1 12 Tf\n(National Research Fellowship 2026) Tj\n(Eligibility: B.Tech 2025/2026) Tj\nET\nendstream\n"
        b"%%EOF"
    )

    text, page_count = extract_pdf_text_safe(pdf_content)
    assert page_count == 1
    assert "National Research Fellowship 2026" in text
    assert "Eligibility: B.Tech 2025/2026" in text


def test_extract_pdf_text_safe_size_limit() -> None:
    # 200 bytes with limit of 100 bytes
    large_pdf = b"%PDF-1.4 " + (b"X" * 200)
    with pytest.raises(ExtractionError, match="exceeds maximum permitted limit"):
        extract_pdf_text_safe(large_pdf, max_bytes=100)
