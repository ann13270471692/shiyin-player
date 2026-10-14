# -*- coding: utf-8 -*-
"""第三轮认库：歌名 == 剧名（剧名来自候选池 alias 里的《…》）。
例：库里 1992-002 高胜美 - 青青河边草，候选池里别的歌 alias 写着「电视剧《青青河边草》…」
→ 这首就是该剧主题曲，算影视金曲（不重命名、不重下）。
要求：剧名在 >=2 条不同候选记录的 alias 里出现（证明是真实剧名），年份 ±3。
默认 dry-run，--write 才写。
"""
import os
import re
import sys
import json
import collections

sys.path.insert(0, r'F:\Temp')
import moviefill as M                                    # noqa: E402

LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
RAW = r'F:\Temp\movie-raw.json'
POOLDIR = r'F:\Temp\movie-pools'
META = (r'F:\DeepSeek Workspace\时事分析\shiyin-player'
        r'\SyncServer\movie-meta.json')
POP = r'F:\Temp\pop-movie.json'

NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(?:【影视】)?\.mp3$')
PUNCT = u'()（）·.、,，!！?？“”"\' \t-_\\/＆&'


def norm(s):
    s = M.norm(s)
    for ch in PUNCT:
        s = s.replace(ch, u'')
    return s


def drama_years():
    """剧名 -> {出现过的年份集合, 出现次数}"""
    cnt = collections.Counter()
    yrs = collections.defaultdict(set)
    src = {}
    rows = []
    raw = json.load(open(RAW, encoding='utf-8'))
    for _, v in raw.items():
        if isinstance(v, dict):
            rows.append(v)
    for fn in os.listdir(POOLDIR):
        if not fn.endswith('.json'):
            continue
        try:
            for v in json.load(open(os.path.join(POOLDIR, fn), encoding='utf-8')):
                if isinstance(v, dict):
                    rows.append(v)
        except Exception:
            pass
    for v in rows:
        al = v.get('alias') or u''
        m = M.BOOK.search(al)
        if not m:
            continue
        d = m.group(1).strip()
        if len(d) < 2 or len(d) > 14:
            continue
        cnt[d] += 1
        try:
            y = int(v.get('pub') or 0)
        except (TypeError, ValueError):
            y = 0
        if y:
            yrs[d].add(y)
        src.setdefault(d, al)
    return cnt, yrs, src


def main():
    write = '--write' in sys.argv
    meta = json.load(open(META, encoding='utf-8'))
    pop = json.load(open(POP, encoding='utf-8')) if os.path.exists(POP) else {}
    cnt, yrs, src = drama_years()
    strong = set(d for d, c in cnt.items() if c >= 2)
    print('剧名候选：%d（其中出现>=2次 %d）' % (len(cnt), len(strong)))

    hits = []
    byname = {}
    for d in strong:
        byname.setdefault(norm(d), d)
    for f in os.listdir(LIB):
        if not f.endswith('.mp3'):
            continue
        stem = f[:-4]
        if stem in meta or u'【影视】' in stem:
            continue
        m = NAME.match(stem)
        if not m:
            continue
        py, artist, title = int(m.group(1)), m.group(3), m.group(4)
        nt = norm(title)
        if len(nt) < 2:
            continue
        d = byname.get(nt)
        if d:
            ys = yrs.get(d) or set()
            if not ys or min(abs(py - y) for y in ys) <= 3:
                hits.append((stem, d, artist, py, src[d][:30]))

    print('歌名==剧名 命中：%d（现有 meta %d）' % (len(hits), len(meta)))
    for h in hits[:70]:
        print('   %-50s -> %-12s %s | %s' % (h[0][:50], h[1][:12], h[3], h[4]))
    if not write:
        print('（dry-run，加 --write 才写）')
        return

    for stem, drama, _a, py, _s in hits:
        meta[stem] = drama
        pop[stem] = {'alias': drama, 'drama': drama, 'id': '', 'year': py}
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
