import os
import sys

import fitz
import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pdf_compressor.compressor import compress_pdf, PDFCompressError  # noqa: E402


@pytest.fixture
def big_pdf(tmp_path):
    img = Image.effect_noise((2400, 2400), 60).convert("RGB")
    png = tmp_path / "a.png"
    img.save(png)
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(page.rect, filename=str(png))
    p = tmp_path / "big.pdf"
    doc.save(str(p))
    return str(p)


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_levels_shrink(big_pdf, tmp_path, level):
    dst = str(tmp_path / (level + ".pdf"))
    calls = []
    o, n = compress_pdf(big_pdf, dst, level, calls.append)
    assert n < o
    assert calls and calls[-1] == 1
    assert fitz.open(dst).page_count == 2


def test_fallback_when_not_smaller(tmp_path):
    doc = fitz.open()
    doc.new_page()
    p = tmp_path / "tiny.pdf"
    doc.save(str(p))
    dst = str(tmp_path / "out.pdf")
    o, n = compress_pdf(str(p), dst, "high")
    assert n <= o
    assert os.path.getsize(dst) == n


def test_bad_file(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(PDFCompressError):
        compress_pdf(str(p), str(tmp_path / "o.pdf"))
