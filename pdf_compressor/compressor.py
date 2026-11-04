"""PDF 压缩核心逻辑(不依赖 tkinter)。"""
import io
import os
import shutil

import fitz  # PyMuPDF
from PIL import Image

# level: (最大边长像素, JPEG 质量)
LEVELS = {
    "low": (3000, 85),
    "medium": (1800, 65),
    "high": (1200, 40),
}


class PDFCompressError(Exception):
    pass


def _recompress_image(doc, xref, max_side, quality):
    info = doc.extract_image(xref)
    if not info:
        return False
    img = Image.open(io.BytesIO(info["image"]))
    if info.get("smask"):
        return False  # 带透明蒙版的图片不处理,避免破坏外观
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    data = buf.getvalue()
    if len(data) >= len(info["image"]):
        return False
    return data, img.size


def compress_pdf(src, dst, level="medium", progress_cb=None):
    """压缩 src 保存到 dst,返回 (原大小, 新大小)。若结果更大则复制原文件。"""
    if level not in LEVELS:
        raise ValueError("未知压缩级别: %s" % level)
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("输出路径不能与源文件相同")
    max_side, quality = LEVELS[level]
    orig_size = os.path.getsize(src)
    try:
        doc = fitz.open(src)
    except Exception as e:
        raise PDFCompressError("无法打开 PDF: %s" % e)
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise PDFCompressError("文件已加密,无法压缩")
        pages = doc.page_count
        done = set()
        for i in range(pages):
            for item in doc.get_page_images(i):
                xref = item[0]
                if xref in done:
                    continue
                done.add(xref)
                try:
                    res = _recompress_image(doc, xref, max_side, quality)
                    if res:
                        data, size = res
                        page = doc[i]
                        page.replace_image(xref, stream=data)
                except Exception:
                    continue
            if progress_cb:
                progress_cb((i + 1) / max(pages, 1))
        tmp = dst + ".tmp"
        try:
            doc.save(tmp, garbage=4, deflate=True, clean=True, use_objstms=1)
        except Exception as e:
            raise PDFCompressError("保存失败: %s" % e)
    except PDFCompressError:
        raise
    except Exception as e:
        raise PDFCompressError("压缩失败: %s" % e)
    finally:
        doc.close()
    new_size = os.path.getsize(tmp)
    if new_size >= orig_size:
        os.remove(tmp)
        shutil.copyfile(src, dst)
        new_size = orig_size
    else:
        os.replace(tmp, dst)
    return orig_size, new_size
