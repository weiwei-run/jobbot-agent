#!/usr/bin/env python3
"""纯标准库 PDF 文本提取（零依赖，无需安装 pypdf）。

覆盖常见文字版 PDF（Word / WPS / 在线工具导出的简历）。
扫描件 / 图片版 PDF 没有文字层，返回空字符串。
"""

import re
import zlib


_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_STREAM_RE2 = re.compile(rb"stream(.*?)endstream", re.S)


def _decode_stream(raw: bytes) -> bytes:
    m = _STREAM_RE.search(raw) or _STREAM_RE2.search(raw)
    if not m:
        return b""
    data = m.group(1)
    if b"FlateDecode" in raw:
        for candidate in (data, data.rstrip(b"\r\n")):
            try:
                return zlib.decompress(candidate)
            except Exception:
                continue
        return b""
    return data


def _bytes_to_unicode(b: bytes) -> str:
    if not b:
        return ""
    if b.startswith(b"\xfe\xff"):
        b = b[2:]
    for enc in ("utf-16-be", "utf-8"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("latin-1", "ignore")


def _parse_cmap(raw_obj: bytes) -> dict[int, str]:
    data = _decode_stream(raw_obj)
    if not data:
        return {}
    cmap: dict[int, str] = {}
    for m in re.finditer(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for pair in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            try:
                src = int(pair.group(1), 16)
                dst = _bytes_to_unicode(bytes.fromhex(pair.group(2).decode("latin-1")))
                if dst:
                    cmap[src] = dst
            except Exception:
                continue
    for m in re.finditer(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for tri in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            try:
                lo, hi = int(tri.group(1), 16), int(tri.group(2), 16)
                dst0 = int.from_bytes(bytes.fromhex(tri.group(3).decode("latin-1")), "big")
                for i in range(lo, min(hi, lo + 5000) + 1):
                    cmap[i] = chr(dst0 + (i - lo))
            except Exception:
                continue
    return cmap


def _read_literal(data: bytes, i: int) -> tuple[bytes, int]:
    """读取 (...) 字面字符串（处理转义）。返回 (内容, 结束位置)。"""
    j = i + 1
    buf = bytearray()
    while j < len(data):
        c = data[j]
        if c == 0x5C:  # backslash
            if j + 1 < len(data):
                e = data[j + 1]
                if e == ord("n"):
                    buf += b"\n"
                elif e == ord("r"):
                    buf += b"\r"
                elif e == ord("t"):
                    buf += b"\t"
                elif e == ord("b"):
                    buf += b"\b"
                elif e == ord("f"):
                    buf += b"\f"
                elif e in (ord("("), ord(")"), ord("\\")):
                    buf += bytes([e])
                elif 48 <= e <= 55:  # octal
                    k = j + 1
                    num = b""
                    while k < len(data) and len(num) < 3 and 48 <= data[k] <= 55:
                        num += bytes([data[k]])
                        k += 1
                    buf += bytes([int(num, 8) & 0xFF])
                    j = k - 1
                else:
                    buf += bytes([e])
                j += 2
            else:
                j += 1
        elif c == 0x29:  # ')'
            return bytes(buf), j + 1
        else:
            buf += bytes([c])
            j += 1
    return bytes(buf), j


def _peek_op(data: bytes, i: int) -> bytes:
    while i < len(data) and data[i] in b" \t\r\n\f\v":
        i += 1
    j = i
    while j < len(data) and data[j] not in b" \t\r\n\f\v[]<>()/":
        j += 1
    return data[i:j]


def _decode_bytes(data: bytes, cmap: dict[int, str] | None) -> str:
    if not data:
        return ""
    if data.startswith(b"\xfe\xff"):
        try:
            return data[2:].decode("utf-16-be")
        except Exception:
            pass
    if cmap:
        out = []
        i = 0
        while i < len(data):
            if i + 1 < len(data):
                code2 = (data[i] << 8) | data[i + 1]
                if code2 in cmap:
                    out.append(cmap[code2])
                    i += 2
                    continue
            code1 = data[i]
            out.append(cmap.get(code1, chr(code1)))
            i += 1
        return "".join(out)
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("latin-1", "ignore")


def _extract_stream(data: bytes, fonts: dict[str, dict[int, str]]) -> str:
    out: list[str] = []
    i, n = 0, len(data)
    current_font: str | None = None
    while i < n:
        b = data[i]
        if b in b" \t\r\n\f\v":
            i += 1
            continue
        if b == ord("/"):
            j = i + 1
            while j < n and data[j] not in b" \t\r\n\f\v[]<>()/":
                j += 1
            name = data[i + 1:j].decode("latin-1", "ignore")
            k = j
            while k < n and data[k] in b" \t\r\n\f\v":
                k += 1
            m2 = re.match(rb"(\d+(?:\.\d+)?)\s+([A-Za-z]+)", data[k:k + 24])
            if m2 and m2.group(2) == b"Tf":
                current_font = name
                i = k + m2.end()
                continue
            i = j
            continue
        if b == ord("("):
            s, j = _read_literal(data, i)
            i = j
            if _peek_op(data, i) in (b"Tj", b"'", b'"'):
                out.append(_decode_bytes(s, fonts.get(current_font)))
            continue
        if b == ord("<"):
            if data[i + 1:i + 2] == b"<":
                i += 2
                continue
            j = data.find(b">", i)
            if j == -1:
                break
            try:
                s = bytes.fromhex(data[i + 1:j].decode("latin-1"))
            except ValueError:
                s = b""
            i = j + 1
            if _peek_op(data, i) in (b"Tj", b"'", b'"'):
                out.append(_decode_bytes(s, fonts.get(current_font)))
            continue
        if b == ord("["):
            j = data.find(b"]", i)
            if j == -1:
                break
            arr = data[i + 1:j]
            i = j + 1
            if _peek_op(data, i) == b"TJ":
                parts = []
                for sm in re.finditer(rb"<([0-9A-Fa-f]+)>|\((?:[^()\\]|\\.)*\)", arr):
                    tok = sm.group(0)
                    if tok.startswith(b"<"):
                        try:
                            parts.append(_decode_bytes(bytes.fromhex(sm.group(1).decode("latin-1")),
                                                       fonts.get(current_font)))
                        except ValueError:
                            pass
                    else:
                        s, _ = _read_literal(tok, 0)
                        parts.append(_decode_bytes(s, fonts.get(current_font)))
                out.append("".join(parts))
            continue
        if b in b"0123456789+-.":
            # 数字令牌：判断是否 TD/Td/T*（换行或横向微调）
            j = i
            while j < n and data[j] not in b" \t\r\n\f\v":
                j += 1
            m3 = re.match(rb"-?\d+(?:\.\d+)?\s+(-?\d+(?:\.\d+)?)\s+(TD|Td|T\*)",
                          data[j:j + 40])
            if m3:
                ty = float(m3.group(1))
                if m3.group(2) == b"T*" or abs(ty) > 0.001:
                    if out and not out[-1].endswith("\n"):
                        out.append("\n")
                i = j + m3.end()
                continue
            i = j
            continue
        if b in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            j = i
            while j < n and data[j] not in b" \t\r\n\f\v[]<>()/":
                j += 1
            op = data[i:j]
            if op in (b"T*",):
                if out and not out[-1].endswith("\n"):
                    out.append("\n")
            i = j
            continue
        i += 1
    return "".join(out)


def _collect_pages(obj_num: int, objects: dict[int, bytes], seen: set, pages: list):
    if obj_num in seen:
        return
    seen.add(obj_num)
    raw = objects.get(obj_num, b"")
    if b"/Type/Pages" in raw or b"/Type /Pages" in raw:
        for kidlist in re.findall(rb"/(?:Kids|Child)\s*\[(.*?)\]", raw, re.S):
            for m in re.finditer(rb"(\d+)\s+0\s+R", kidlist):
                _collect_pages(int(m.group(1)), objects, seen, pages)
    elif b"/Type/Page" in raw or b"/Type /Page" in raw:
        pages.append(obj_num)


def _page_fonts(page_num: int, objects: dict[int, bytes]) -> dict[str, dict[int, str]]:
    raw = objects.get(page_num, b"")
    fonts: dict[str, dict[int, str]] = {}
    for fd in re.finditer(rb"/Font\s*<<(.*?)>>", raw, re.S):
        for m in re.finditer(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R", fd.group(1)):
            name = m.group(1).decode("latin-1", "ignore")
            fraw = objects.get(int(m.group(2)), b"")
            tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fraw)
            if tu:
                cmap = _parse_cmap(objects.get(int(tu.group(1)), b""))
                if cmap:
                    fonts[name] = cmap
    return fonts


def _form_fonts(raw: bytes, objects: dict[int, bytes]) -> dict[str, dict[int, str]]:
    fonts: dict[str, dict[int, str]] = {}
    for fd in re.finditer(rb"/Font\s*<<(.*?)>>", raw, re.S):
        for m in re.finditer(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R", fd.group(1)):
            name = m.group(1).decode("latin-1", "ignore")
            fraw = objects.get(int(m.group(2)), b"")
            tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fraw)
            if tu:
                cmap = _parse_cmap(objects.get(int(tu.group(1)), b""))
                if cmap:
                    fonts[name] = cmap
    return fonts


def _form_text(obj_num: int, objects: dict[int, bytes], depth: int = 0) -> str:
    """递归提取 Form XObject 内的文本（表单可能嵌套）。"""
    if depth > 6 or obj_num not in objects:
        return ""
    raw = objects[obj_num]
    if b"/Subtype/Form" not in raw and b"/Subtype /Form" not in raw:
        return ""
    data = _decode_stream(raw)
    if not data:
        return ""
    out = _extract_stream(data, _form_fonts(raw, objects))
    # 表单内部可能再引用图片/嵌套表单
    for ref in re.finditer(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R", raw):
        out += _form_text(int(ref.group(2)), objects, depth + 1)
    return out


def extract_pdf_text(data: bytes) -> str:
    """纯标准库提取 PDF 文本。扫描件返回空字符串。"""
    objects: dict[int, bytes] = {}
    for m in _OBJ_RE.finditer(data):
        num = int(m.group(1))
        start = m.end()
        end = data.find(b"endobj", start)
        objects[num] = data[start:end] if end != -1 else data[start:start + 200000]

    catalog = 1
    for num, raw in objects.items():
        if b"/Type/Catalog" in raw or b"/Type /Catalog" in raw:
            catalog = num
            break

    pages: list[int] = []
    m = re.search(rb"/Pages\s+(\d+)\s+0\s+R", objects.get(catalog, b""))
    if m:
        _collect_pages(int(m.group(1)), objects, set(), pages)
    if not pages:
        for num, raw in objects.items():
            if b"/Type/Page" in raw or b"/Type /Page" in raw:
                pages.append(num)

    texts: list[str] = []
    for pnum in pages:
        raw = objects.get(pnum, b"")
        fonts = _page_fonts(pnum, objects)
        for cm in re.finditer(rb"/Contents\s+(\d+)\s+0\s+R", raw):
            content = _decode_stream(objects.get(int(cm.group(1)), b""))
            texts.append(_extract_stream(content, fonts))
        for am in re.finditer(rb"/Contents\s*\[(.*?)\]", raw, re.S):
            for m2 in re.finditer(rb"(\d+)\s+0\s+R", am.group(1)):
                content = _decode_stream(objects.get(int(m2.group(1)), b""))
                texts.append(_extract_stream(content, fonts))
        # 页面资源里的 XObject（Form 表单内可能包含正文文本）
        for xm in re.finditer(rb"/XObject\s*<<(.*?)>>", raw, re.S):
            for ref in re.finditer(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R", xm.group(1)):
                texts.append(_form_text(int(ref.group(2)), objects))
    return "\n".join(t for t in texts if t.strip())
