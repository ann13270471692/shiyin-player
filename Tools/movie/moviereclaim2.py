# -*- coding: utf-8 -*-
"""第二轮认库：把库里「其实就是影视金曲」的流行歌认出来（不重命名、不重下）。
比 moviereclaim 松：歌手允许「部分匹配」（合唱/精选辑署名常不同），但要求
歌名完全一致 + 发行年 ±2 + 离线闸门（含日文过滤）通过。默认只打印，--write 才写。
"""
import os
import re
import sys
import json

sys.path.insert(0, r'F:\Temp')
import moviefill as M                                    # noqa: E402

LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
RAW = r'F:\Temp\movie-raw.json'
META = (r'F:\DeepSeek Workspace\时事分析\shiyin-player'
        r'\SyncServer\movie-meta.json')
POP = r'F:\Temp\pop-movie.json'

NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(?:【影视】)?\.mp3$')
PUNCT = u'()（）·.、,，!！?？“”"\' \t-_\\/＆&'

# 人工核对过的：文件名里带《》但不在 movie-raw 里的
MANUAL = {
    u'2009-048 - 小时姑娘 - 爱殇 (《东宫》插曲)': u'东宫',
    u'2015-704 - 广东雨神许华升 - 陪你到底 (《东斜西独》主题曲)': u'东斜西独',
}


def norm(s):
    s = M.norm(s)
    for ch in PUNCT:
        s = s.replace(ch, u'')
    return s


def arts(s):
    parts = re.split(u'[&/、,，&＋+]|feat|ft\\.', M.norm(s or u''))
    return [p for p in (x.strip() for x in parts) if len(p) >= 2]


def art_ok(a, b):
    """歌手宽松匹配：完全相同 / 一方包含另一方 / 有共同歌手 token。"""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    A, B = arts(a), arts(b)
    for x in A:
        for y in B:
            if x == y or (len(x) >= 3 and x in y) or (len(y) >= 3 and y in x):
                return True
    return False


def main():
    write = '--write' in sys.argv
    raw = json.load(open(RAW, encoding='utf-8'))
    meta = json.load(open(META, encoding='utf-8'))
    pop = json.load(open(POP, encoding='utf-8')) if os.path.exists(POP) else {}

    files = {}
    for f in os.listdir(LIB):
        if not f.endswith('.mp3'):
            continue
        stem = f[:-4]
        if stem in meta or u'【影视】' in stem:
            continue
        m = NAME.match(stem)
        if not m:
            continue
        files.setdefault(norm(m.group(4)), []).append(
            (stem, int(m.group(1)), m.group(3)))

    hits = []
    seen = set()
    for _, v in raw.items():
        if not isinstance(v, dict):
            continue
        nm = v.get('name') or u''
        if not nm or not v.get('id'):
            continue
        try:
            y = int(v.get('pub') or 0)
            sid = int(v['id'])
        except (TypeError, ValueError):
            continue
        if y < 1980 or y > 2026:
            continue
        drama, bad = M.gate(v, {sid: v}, y)
        if bad:
            continue
        for stem, py, part in files.get(norm(nm), []):
            if stem in seen or abs(py - y) > 2:
                continue
            if not art_ok(part, v.get('artist')):
                continue
            seen.add(stem)
            hits.append((stem, drama, part, v.get('artist') or u'', py, y))

    for stem, drama in MANUAL.items():
        if stem not in seen and stem not in meta:
            seen.add(stem)
            hits.append((stem, drama, u'(文件名《》)', u'', 0, 0))

    print('宽松认库命中：%d（现有 meta %d）' % (len(hits), len(meta)))
    for h in hits[:60]:
        print('   %-52s -> %-14s | %s || %s' % (h[0][:52], h[1][:14],
                                                h[2][:14], h[3][:14]))
    if not write:
        print('（dry-run，加 --write 才写）')
        return

    for stem, drama, _a, _b, _py, y in hits:
        meta[stem] = drama
        pop[stem] = {'alias': drama, 'drama': drama, 'id': '', 'year': y}
    tmp = META + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, META)
    tmp = POP + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(pop, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, POP)
    print('已写：meta %d，pop-movie %d' % (len(meta), len(pop)))


if __name__ == '__main__':
    main()
