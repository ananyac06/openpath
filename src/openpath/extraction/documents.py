"""Document extraction utilities for PDF and text notifications."""

from __future__ import annotations

import logging
import re

from openpath.exceptions import ExtractionError

logger = logging.getLogger(__name__)


def extract_pdf_text_safe(pdf_bytes: bytes, max_bytes: int = 10 * 1024 * 1024) -> tuple[str, int]:
    """
    Safely extract text and page count from PDF bytes without code execution.
    Enforces payload size limits and text extraction sandboxing.
    """
    if len(pdf_bytes) > max_bytes:
        raise ExtractionError(
            f"PDF file size ({len(pdf_bytes)} bytes) exceeds maximum permitted limit ({max_bytes} bytes)."
        )

    # Basic pure-Python PDF stream scanner for text and page markers
    # Finds /Type /Page and extracts text streams between BT and ET markers
    try:
        content = pdf_bytes.decode("latin-1", errors="replace")

        # Estimate page count by counting /Type\s*/Page (not /Pages)
        pages = re.findall(r"/Type\s*/Page\b", content)
        page_count = max(1, len(pages))

        # Extract text blocks between Begin Text (BT) and End Text (ET) operators
        text_blocks: list[str] = []
        bt_matches = re.finditer(r"BT(.*?)ET", content, re.DOTALL)
        for match in bt_matches:
            block = match.group(1)
            # Find literal strings in parentheses (Text)
            strings = re.findall(r"\((.*?)\)", block)
            if strings:
                text_blocks.append(" ".join(strings))

        extracted_text = " ".join(text_blocks)
        clean_text = re.sub(r"\s+", " ", extracted_text).strip()

        return (clean_text, page_count)
    except Exception as err:
        raise ExtractionError(f"Failed to extract text from PDF document: {err}") from err
