# -*- coding: utf-8 -*-
# 离线认库：movie-raw.json 里带影视证据（alias/专辑《》）的候选，
# 如果同名+同歌手的歌已经在流行库里（且还没认过），就直接归入影视类：
#   不下载、不改名，只写 pop-movie.json + movie-meta.json（算配额）。
#   python moviereclaim.py          # 只看
#   python moviereclaim.py --write  # 写盘
import importlib
import json
import os
import re
import sys

sys.path.insert(0, r'F:\Temp')
M = importlib.import_module('moviefill')
RAW = r'F:\Temp\movie-raw.json'
REC = r'F:\Temp\pop-movie.json'
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
NAME = re.compile(r'^(\d{4})-(\d+) - (.+) - (.+?)(【影视】)?$')


def normart(s):
    return re.sub(r'\s+', u'', (s or u'')).lower()


def main(write):
    raw = json.load(open(RAW, encoding='utf-8'))
    rec = json.load(open(REC, encoding='utf-8'))
    try:
        meta = json.load(open(META, encoding='utf-8'))
    except Exception:
        meta = {}
    rec_ids = set(int(v.get('id') or 0) for v in rec.values() if isinstance(v, dict))

    # 库索引：norm(歌名) -> [(stem, artist, year, is_movie)]
    idx = {}
    for f in os.listdir(LIB):
        if not f.endswith('.mp3'):
            continue
        m = NAME.match(f[:-4])
        if not m:
            continue
        stem, year, artist, title = f[:-4], int(m.group(1)), m.group(3), m.group(4)
        idx.setdefault(M.norm(title), []).append((stem, artist, year, bool(m.group(5))))

    hits = []
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        sid = int(v.get('id') or 0)
        if not sid or sid in rec_ids:
            continue
        y = v.get('pub')
        if not isinstance(y, int) or y not in M.YEARS:
            continue
        drama, bad = M.gate(v, {sid: v}, y)     # 离线闸门（含日文过滤）
        if bad:
            continue
        for stem, artist, ly, ismv in idx.get(M.norm(v.get('name') or u''), []):
            if ismv or stem in meta:
                continue
            if normart(artist) != normart(v.get('artist')):
                continue
            if abs(ly - y) > 2:
                continue
            hits.append((stem, drama, v, ly))
            break

    print('可离线认库 %d 首（不下载、不改名）' % len(hits))
    for stem, drama, v, ly in hits[:25]:
        print('  %s  ← %s（%s，%d年）' % (stem, drama, (v.get('alias') or v.get('album') or u'')[:22], ly))
    if not write:
        print('（dry run，加 --write 才写盘）')
        return
    for stem, drama, v, ly in hits:
        rec[stem] = {'alias': v.get('alias') or u'', 'drama': drama,
                     'id': int(v['id']), 'year': ly}
        meta[stem] = drama
    json.dump(rec, open(REC + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(REC + '.tmp', REC)
    json.dump(meta, open(META + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(META + '.tmp', META)
    print('已写入：pop-movie.json %d 条，movie-meta.json %d 条' % (len(rec), len(meta)))


if __name__ == '__main__':
    main('--write' in sys.argv[1:])
