# -*- coding: utf-8 -*-
"""逐行移植 ID3Parser.swift 的算法，对 19 个真实 MP3 验证；另查 .lrc 编码与文件名模式。"""
import os, re, sys

MUSIC = r"F:\DeepSeek Workspace\时事分析\音乐集合"

def synchsafe(b, at):
    if at + 4 > len(b): return 0
    return (b[at] & 0x7f) << 21 | (b[at+1] & 0x7f) << 14 | (b[at+2] & 0x7f) << 7 | (b[at+3] & 0x7f)

def decode_string(bs, enc):
    try:
        if enc == 0: return bs.decode("latin-1")
        if enc == 1:
            s = bs.decode("utf-16")   # 带 BOM
            return s
        if enc == 2: return bs.decode("utf-16-be")
        return bs.decode("utf-8", errors="replace")
    except Exception:
        return None

def decode_uslt(f):
    if len(f) <= 5: return None
    enc = f[0]
    i = 1
    while i < len(f) and f[i] != 0: i += 1
    i += 1
    if i >= len(f): return None
    return decode_string(f[i:], enc)

def lyrics_from(path):
    with open(path, "rb") as fh:
        h = fh.read(10)
        if len(h) != 10 or h[0:3] != b"ID3": return None
        version = h[3]
        if version < 3: return None
        tag_size = synchsafe(h, 6)
        if tag_size <= 0: return None
        b = fh.read(tag_size)
        if len(b) < 10: return None
        pos = 0
        if h[5] & 0x40:
            if version >= 4:
                pos = synchsafe(b, 0)
            else:
                pos = 4 + (b[0] << 24 | b[1] << 16 | b[2] << 8 | b[3])
        while pos + 10 <= len(b):
            idb = b[pos:pos+4]
            try: id_ = idb.decode("ascii")
            except Exception: id_ = ""
            if not any(c.isalpha() for c in id_): break
            if version >= 4:
                fsize = synchsafe(b, pos+4)
            else:
                fsize = b[pos+4] << 24 | b[pos+5] << 16 | b[pos+6] << 8 | b[pos+7]
            start = pos + 10
            if fsize <= 0 or start + fsize > len(b): break
            if id_ == "USLT":
                return decode_uslt(b[start:start+fsize])
            pos = start + fsize
        return None

ok = fail = 0
lrc_bad_enc = []
name_bad = []
LRC_TAG = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")

for name in sorted(os.listdir(MUSIC)):
    p = os.path.join(MUSIC, name)
    if not os.path.isfile(p): continue
    ext = os.path.splitext(name)[1].lower()
    if ext == ".mp3":
        stem = os.path.splitext(name)[0]
        parts = stem.split(" - ")
        if len(parts) < 3: name_bad.append(name)
        r = lyrics_from(p)
        if r and r.strip():
            ok += 1
        else:
            fail += 1
            print("USLT-FAIL:", name)
        lp = p[:-4] + ".lrc"
        if os.path.exists(lp):
            raw = open(lp, "rb").read()
            try:
                txt = raw.decode("utf-8")
                if txt.startswith("\ufeff"): lrc_bad_enc.append((name, "utf8-BOM"))
            except UnicodeDecodeError:
                lrc_bad_enc.append((name, "not-utf8"))
                continue
            tagged = sum(1 for ln in txt.splitlines() if LRC_TAG.search(ln))
            if tagged == 0: lrc_bad_enc.append((name, "no-timestamps"))
    elif ext == ".lrc":
        pass

print(f"\nUSLT embedded: {ok} ok / {fail} fail")
print("filename pattern issues:", name_bad or "none")
print("lrc issues:", lrc_bad_enc or "none")
