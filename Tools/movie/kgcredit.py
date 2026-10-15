# -*- coding: utf-8 -*-
r"""酷狗认库：库里 1980-1999 的流行歌，去酷狗查专辑名，
专辑名（或曲名里的《》）命中「已知剧名表」就认成影视金曲——不下载、不重命名，
只往 pop-movie.json / movie-meta.json 记一笔，配额立刻多一首。

已知剧名表 = 网易云资料里带《》的剧名 + drama-seed.json 人工清单（kgfill.drama_years）。
只碰酷狗，不碰网易云，可以和下载进程并行。

用法：python kgcredit.py [--write] 1980 1999
"""
import json
import os
import re
import sys

sys.path.insert(0, r'F:\Temp')
import acquire
import kgfill
from acquire import LIB, norm, kg_search
from fill6 import cjk_ok, BADVER

T = r'F:\Temp'
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
REC = os.path.join(T, 'pop-movie.json')
LOGF = os.path.join(T, 'movie.log')
BOOK = re.compile(u'《(.{2,20})》')
CJK = re.compile(u'[\u4e00-\u9fff]')
NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(?:【影视】)?\.mp3$')
JUNKAL = re.compile(u'精选|best|新歌|加浓|remix|纯音乐|伴奏|卡拉ok|karaoke'
                    u'|原声大碟|电影原声|电视原声|ost|合辑|专辑|EP|现场版', re.I)
acquire._host_min['mobiles.kugou.com'] = 3.5   # kgfill 也在打酷狗，这里放慢


def logline(s):
    with open(LOGF, 'a', encoding='utf-8') as f:
        f.write(s.rstrip() + u'\n')


def dramas():
    """归一化剧名 -> 年份。"""
    out = {}
    for nm, y in kgfill.drama_years().items():
        k = norm(nm)
        if k and len(k) >= 2:
            out.setdefault(k, y)
    return out


def pick(rows, nm, ar):
    """酷狗结果里挑同名同歌手的那条，返回 (专辑名, 曲名里的《》)。"""
    tn, ta = norm(nm), norm(ar)
    for r in rows:
        rn = norm(r.get('songname') or u'')
        ra = norm(r.get('singername') or u'')
        if rn != tn:
            continue
        if ta and ta not in ra and ra not in ta:
            continue
        al = (r.get('album_name') or u'').strip()
        inside = BOOK.search(r.get('songname') or u'')
        return al, (inside.group(1).strip() if inside else u'')
    return u'', u''


def evidence(al, inside, dy, year):
    """专辑名/曲名《》 -> 剧名。专辑名里「包含」已知剧名就算证据
    （酷狗专辑名常写成「神雕侠侣(金装电视剧歌曲经典)」这种带后缀的形式）。"""
    cands = []
    m = BOOK.search(al or u'')
    if m:
        cands.append(m.group(1).strip())
    if al:
        cands.append(al)
    if inside:
        cands.append(inside)
    for c in cands:
        if len(c) < 2 or len(c) > 24 or JUNKAL.search(c) or not CJK.search(c):
            continue
        base = re.sub(u'[（(\\[【].{0,24}[)）\\]】]$', u'', c).strip()
        for cand in (c, base):
            k = norm(cand)
            if not k or len(k) < 2:
                continue
            hit = dy.get(k)
            if hit is None and len(k) >= 3:
                # 包含匹配：专辑名里嵌着剧名
                for dk, dv in dy.items():
                    if len(dk) >= 3 and dk in k:
                        hit, k = dv, dk
                        break
            if hit is None or abs(hit - year) > 4:
                continue
            nm = re.sub(u'[（(\\[【].{0,24}[)）\\]】]$', u'', cand).strip()
            # 「西游记 电视剧原声带」这种写成专辑名的，剧名只留「西游记」
            nm = re.sub(u'\s*(电视剧|电视原声带?|电影原声带?|原声大碟|原声带|原声|主题曲|插曲|片尾曲|片头曲|ost|专辑)\s*$',
                        u'', nm, flags=re.I).strip()
            return nm if len(nm) >= 2 else cand
    return u''


def main(y0, y1, write):
    dy = dramas()
    print(u'已知剧名 %d 个' % len(dy), flush=True)
    try:
        meta = json.load(open(META, encoding='utf-8'))
    except Exception:
        meta = {}
    try:
        rec = json.load(open(REC, encoding='utf-8'))
    except Exception:
        rec = {}
    done = set(norm(k) for k in rec)
    hit = 0
    seen = 0
    for f in sorted(os.listdir(LIB)):
        m = NAME.match(f)
        if not m:
            continue
        y = int(m.group(1))
        if not (y0 <= y <= y1):
            continue
        stem = f[:-4]
        if stem.endswith(u'【影视】') or stem in meta:
            continue
        ar, nm = m.group(3), m.group(4)
        if not cjk_ok(nm, ar) or BADVER.search(nm):
            continue
        rows = kg_search(u'%s %s' % (nm, ar), n=10)
        seen += 1
        al, inside = pick(rows, nm, ar)
        drama = evidence(al, inside, dy, y)
        if not drama:
            if seen % 50 == 0:
                print(u'  %d 查过 / %d 命中' % (seen, hit), flush=True)
            continue
        rec[stem] = {'id': 0, 'year': y, 'name': nm, 'artist': ar,
                     'drama': drama, 'how': 'kg'}
        meta[stem] = drama
        hit += 1
        logline(u'%d KGCREDIT %-24s %-14s -> 《%s》 [%s]' % (y, nm[:24], ar[:14], drama, al[:20]))
        print(u'%d %s - %s -> 《%s》' % (y, ar[:14], nm[:22], drama), flush=True)
        if hit % 25 == 0 and write:
            json.dump(rec, open(REC, 'w', encoding='utf-8'), ensure_ascii=False)
            json.dump(meta, open(META + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            os.replace(META + '.tmp', META)
    if write:
        json.dump(rec, open(REC, 'w', encoding='utf-8'), ensure_ascii=False)
        json.dump(meta, open(META + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        os.replace(META + '.tmp', META)
    print(u'认库 %d 首（查了 %d 首，%s）' % (hit, seen, u'写入' if write else u'试运行'), flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    w = '--write' in args
    args = [a for a in args if a != '--write']
    ys = [int(a) for a in args if a.isdigit()]
    main(ys[0] if ys else 1980, ys[-1] if ys else 1999, w)
