# -*- coding: utf-8 -*-
r"""第五轮影视扩池：按「剧名」直接搜网易云曲库，把命中且能过影视闸门的补进 movie-pools。

1980-1991 这些年份在影视歌单里根本没有曲目（歌单都是 2000 年后的华语影视金曲），
但歌名/专辑里带剧名的老歌在曲库里是有的——所以按剧名搜。
剧名表 = 网易云《》证据 + drama-seed.json 人工清单（kgfill.drama_years）。
闸门用 moviefill.gate 同一套代码，过不了的不进池，保证下载进程不会白跑。

用法：python moviepool5.py [--write] 1980 1991
"""
import importlib
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r'F:\Temp')
import acquire
import kgfill
import moviepool as MP
M = importlib.import_module('moviefill')
POOL = r'F:\Temp\movie-pools'
REC = r'F:\Temp\pop-movie.json'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
acquire._host_min['music.163.com'] = 6.0
COVER = re.compile(u'精选|best|重唱|翻唱|致敬|纪念|合集|系列|翻自|新唱| remake', re.I)
OSTKW = re.compile(u'主题曲|片尾曲|片头曲|插曲|原声|OST|电视|电影|动画|剧集|无线', re.I)
http = acquire.http


def song_ok(r):
    """自己把关：华语、不是配乐/纯音乐、不是曲库群星、时长够。
    影视证据 = 剧名命中歌名/别名（或专辑里带原声字样），不靠专辑名猜。"""
    if not M.cjk_ok(r['name'], r['artist']):
        return False
    if M.JUNKART.search(r['artist'] or u'') or M.JUNKNAME.search(r['name'] or u''):
        return False
    if (r['dur'] or 0) < 100:
        return False
    return True


def year_of(pt):
    if not pt:
        return 0
    try:
        return int(time.strftime('%Y', time.gmtime(int(pt) / 1000.0)))
    except Exception:
        return 0


def search(q, limit=30):
    u = ('https://music.163.com/api/search/get?s=%s&type=1&limit=%d'
         % (urllib.parse.quote(q), limit))
    j = MP.jget(u) or {}
    return ((j.get('result') or {}).get('songs')) or []


def main(y0, y1, write):
    dy = {n: y for n, y in kgfill.drama_years().items() if y0 <= y <= y1}
    print(u'目标年份 %d-%d，剧名 %d 个' % (y0, y1, len(dy)), flush=True)

    cred = json.load(open(REC, encoding='utf-8'))
    done_ids = set(int(v.get('id') or 0) for v in cred.values() if isinstance(v, dict))
    for st in ('movie-state.json', 'movie-state-a.json', 'movie-state-b.json',
               'movie-state-c.json', 'movie-state-d.json', 'movie-state-e.json',
               'movie-state-f.json', 'movie-state-g.json'):
        try:
            d = json.load(open(os.path.join(r'F:\Temp', st), encoding='utf-8'))
        except Exception:
            continue
        for v in d.values():
            if isinstance(v, dict) and v.get('id'):
                done_ids.add(int(v['id']))
    own = set()
    for f in os.listdir(LIB):
        if f.endswith('.mp3'):
            own.add(M.norm(f.split(' - ', 2)[-1][:-4]))

    pools, have_ids = {}, set()
    for y in M.YEARS:
        p = os.path.join(POOL, '%d.json' % y)
        rows = []
        if os.path.exists(p):
            try:
                rows = json.load(open(p, encoding='utf-8'))
            except Exception:
                rows = []
        pools[y] = rows
        for r in rows:
            have_ids.add(int(r.get('id') or 0))

    add = {y: 0 for y in M.YEARS}
    added_names = set()
    skip = {'dup': 0, 'lib': 0, 'done': 0, 'junk': 0, 'year': 0,
            'weak': 0, 'cover': 0, 'era': 0}
    for drama, dy0 in sorted(dy.items(), key=lambda kv: kv[1]):
        tn = M.norm(drama)
        got = 0
        for q in (u'《%s》' % drama, u'%s 主题曲' % drama):
            for s in search(q):
                sid = int(s.get('id') or 0)
                if not sid or sid in have_ids or sid in done_ids:
                    skip['dup' if sid in have_ids else 'done'] += 1
                    continue
                nm = (s.get('name') or u'').strip()
                al = u' '.join(s.get('alias') or [])
                ab = ((s.get('album') or {}).get('name') or u'').strip()
                ar = u'/'.join((a.get('name') or u'') for a in (s.get('artists') or []))
                nn = M.norm(nm)
                # 剧名要「独立」命中：歌名就是这部剧（或以它开头），或别名/《》里是这部剧，
                # 或专辑里带原声字样又提到这部剧。「天下过客」这种嵌字不算。
                if not (nn == tn or nn.startswith(tn) or tn in M.norm(al)
                        or (tn in M.norm(ab) and OSTKW.search(ab or u''))):
                    skip['weak'] += 1   # 剧名没落在歌名/别名上，专辑里也没有原声字样
                    continue
                if nn in own or nn in added_names:
                    skip['lib'] += 1
                    continue
                if not kgfill.era_ok(ar, dy0):
                    skip['era'] += 1    # 歌手活跃年代跟这部剧对不上（现代翻唱/同名歌）
                    continue
                ay = year_of((s.get('album') or {}).get('publishTime'))
                if ay and ay - dy0 > 8 and COVER.search(ab or u''):
                    skip['cover'] += 1          # 现代翻唱/致敬精选，不算这部剧的原唱
                    continue
                y = dy0
                if ay and abs(ay - dy0) <= 4:
                    y = ay
                if not (1980 <= y <= 2026) or y not in add:
                    skip['year'] += 1
                    continue
                row = {'id': sid, 'name': nm, 'artist': ar,
                       'dur': int((s.get('duration') or 0) / 1000),
                       'album': ab, 'pub': y, 'alias': al, 'drama': drama,
                       'src': u'ds%s' % M.norm(drama)[:12], 'pop': 0}
                if not song_ok(row):
                    skip['junk'] += 1
                    continue
                pools[y].append(row)
                have_ids.add(sid)
                added_names.add(M.norm(nm))
                add[y] += 1
                got += 1
                print(u'  %d +%s - %s 《%s》' % (y, ar[:12], nm[:20], drama[:16]), flush=True)
            if got >= 8:
                break
    print(u'跳过：已在池 %d / 已下过 %d / 库里同名 %d / 剧名没命中 %d / 年代不合 %d / 现代翻唱 %d / 年份不合 %d / 像配乐纯音乐 %d'
          % (skip['dup'], skip['done'], skip['lib'], skip['weak'], skip['era'],
             skip['cover'], skip['year'], skip['junk']))
    print(u'新增 %d 条' % sum(add.values()), flush=True)
    for y in M.YEARS:
        if add[y]:
            print(u'  %d +%d -> %d' % (y, add[y], len(pools[y])), flush=True)
    if not write:
        print(u'（dry run，加 --write 才写盘）', flush=True)
        return
    for y in M.YEARS:
        if not add[y]:
            continue
        p = os.path.join(POOL, '%d.json' % y)
        json.dump(pools[y], open(p + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(p + '.tmp', p)
    print(u'已写盘', flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    w = '--write' in args
    ys = [int(a) for a in args if a.isdigit()]
    main(ys[0] if ys else 1980, ys[-1] if ys else 1991, w)
