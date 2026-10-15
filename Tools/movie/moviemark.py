# -*- coding: utf-8 -*-
r"""离线认库补配额：候选池里已经过了「影视闸门」的条目，如果同一首歌已经在流行库里
（歌名+歌手+年份对得上），就直接把库里那个文件认成影视金曲，不下载、不改名。
写 pop-movie.json（配额账）+ SyncServer/movie-meta.json（app 里的「影视」标记）。

用法：python moviemark.py            # 只看
      python moviemark.py --write    # 真写
"""
import glob
import importlib
import json
import os
import re
import sys

sys.path.insert(0, r'F:\Temp')
from acquire import LIB, norm
M = importlib.import_module('moviefill')
T = r'F:\Temp'
POOL = os.path.join(T, 'movie-pools')
REC = os.path.join(T, 'pop-movie.json')
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(?:【影视】)?\.mp3$')


def arts(s):
    out = set()
    for a in re.split(u'[/&、,，(（]', s or u''):
        a = norm(a)
        if len(a) >= 2:
            out.add(a)
    return out


def main(write):
    cred = json.load(open(REC, encoding='utf-8'))
    meta = json.load(open(META, encoding='utf-8'))
    lib = {}
    for f in os.listdir(LIB):
        if u'【影视】' in f:
            continue          # 已经是影视文件，再记一次就是重复计数
        m = NAME.match(f)
        if not m:
            continue
        y, ar, nm = int(m.group(1)), m.group(3), m.group(4)
        lib.setdefault(norm(nm), []).append((y, ar, f))
    done = set()
    for k, v in cred.items():
        if isinstance(v, dict) and v.get('id'):
            done.add(int(v['id']))
    # 已经下载过的影视（各 state 文件）也算「已处理」，不重复认库
    for p in glob.glob(os.path.join(T, 'movie-state*.json')) + [os.path.join(T, 'kg-state.json')]:
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for v in d.values():
            if isinstance(v, dict) and v.get('id'):
                done.add(int(v['id']))

    hits = []
    for y in M.YEARS:
        p = os.path.join(POOL, '%d.json' % y)
        if not os.path.exists(p):
            continue
        rows = json.load(open(p, encoding='utf-8'))
        det = {int(r['id']): r for r in rows if isinstance(r, dict) and r.get('id')}
        for r in rows:
            sid = int(r.get('id') or 0)
            if not sid or sid in done:
                continue
            drama, bad = M.gate(r, det, y)
            if bad:
                continue
            for (fy, far, fname) in lib.get(norm(r['name']), ()):
                if abs(fy - y) > 1:
                    continue
                if not (arts(r.get('artist')) & arts(far)):
                    continue
                stem = os.path.splitext(fname)[0]
                if stem in meta:
                    continue
                hits.append((fy, fname, r['name'], r.get('artist') or u'', drama, sid))
                done.add(sid)
                break

    stems = set(os.path.splitext(h[1])[0] for h in hits)
    # 第二路：pool5 在库里搜到同名歌（当时没下载），按剧名+年份+歌手把库里那首认成影视
    hf = os.path.join(T, 'pool5-libhits.json')
    if os.path.exists(hf):
        for e in json.load(open(hf, encoding='utf-8')).values():
            nn = norm(e.get('name') or u'')
            ey = int(e.get('year') or 0)
            if not nn or not ey:
                continue
            for (fy, far, fname) in lib.get(nn, ()):
                stem = os.path.splitext(fname)[0]
                if stem in meta or stem in stems:
                    continue
                if abs(fy - ey) > 6:
                    continue
                if not (arts(e.get('artist')) & arts(far)):
                    continue
                stems.add(stem)
                hits.append((fy, fname, e['name'], e.get('artist') or u'',
                             e.get('drama') or u'', 0))
                break

    print(u'可以认库 %d 首（不下载）' % len(hits))
    per = {}
    for fy, fname, nm, ar, drama, sid in hits:
        per[fy] = per.get(fy, 0) + 1
    print(u'按年：' + u' '.join(u'%d:%d' % (y, c) for y, c in sorted(per.items())))
    for row in hits[:12]:
        print(u'  %d %s - %s -> 《%s》' % (row[0], row[3][:12], row[2][:18], row[4][:16]))
    if not write:
        print(u'（dry run，加 --write 才写盘）')
        return
    for fy, fname, nm, ar, drama, sid in hits:
        stem = os.path.splitext(fname)[0]
        cred[stem] = {'id': sid, 'year': fy, 'name': nm, 'artist': ar, 'drama': drama,
                      'how': 'pool'}
        meta[stem] = drama
    for pth, obj in ((REC, cred), (META, meta)):
        json.dump(obj, open(pth + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(pth + '.tmp', pth)
    print(u'已写盘：%s / %s' % (REC, META))


if __name__ == '__main__':
    main('--write' in sys.argv[1:])
