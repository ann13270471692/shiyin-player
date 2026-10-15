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
LIBHIT = r'F:\Temp\pool5-libhits.json'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
acquire._host_min['music.163.com'] = 6.0
COVER = re.compile(u'精选|best|重唱|翻唱|致敬|纪念|合集|系列|翻自|新唱| remake', re.I)
OSTKW = re.compile(u'主题曲|片尾曲|片头曲|插曲|原声|OST|电视|电影|动画|剧集|无线', re.I)
http = acquire.http


NONCJK = re.compile(u'[\uac00-\ud7af\u1100-\u11ff'
                    u'\u0e00-\u0e7f\u0400-\u04ff\u0600-\u06ff]')


def song_ok(r):
    """自己把关：华语、不是配乐/纯音乐、不是曲库群星、时长够。
    影视证据 = 剧名命中歌名/别名（或专辑里带原声字样），不靠专辑名猜。"""
    if not M.cjk_ok(r['name'], r['artist']):
        return False
    if NONCJK.search(r['name'] or u'') or NONCJK.search(r['artist'] or u''):
        return False        # 韩文/泰文/俄文等，不是华语
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


def album_tracks(aid):
    """整张专辑的曲目：确认过主题曲所在的 OST 专辑，整张都算这部剧的歌。"""
    j = MP.jget(u'https://music.163.com/api/album/%s' % aid) or {}
    return (j.get('album') or {}).get('songs') or []


MAX_EXP = 2          # 每部剧最多展开几张专辑
MAX_TR = 40          # 每张专辑最多取几首


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
    libhit = {}
    skip = {'dup': 0, 'lib': 0, 'done': 0, 'junk': 0, 'year': 0,
            'weak': 0, 'cover': 0, 'era': 0}
    for drama, dy0 in sorted(dy.items(), key=lambda kv: kv[1]):
        tn = M.norm(drama)
        got = 0
        seen_al, exp = set(), 0

        def expand(s):
            """展开这张确认过的原声专辑：整张都算这部剧的歌（证据=同张 OST）。
            库里已有同名歌也要展开——80 年代的主题曲多半已经在流行库里。"""
            nonlocal exp, got
            ab0 = ((s.get('album') or {}).get('name') or u'').strip()
            aid = int(((s.get('album') or {}).get('id') or 0) or 0)
            if not aid or aid in seen_al or exp >= MAX_EXP or COVER.search(ab0 or u''):
                return
            seen_al.add(aid)
            exp += 1
            alpub = year_of((s.get('album') or {}).get('publishTime'))
            for t in album_tracks(aid)[:MAX_TR]:
                tid = int(t.get('id') or 0)
                if not tid or tid in have_ids or tid in done_ids:
                    continue
                tnm = (t.get('name') or u'').strip()
                tar = u'/'.join((a.get('name') or u'') for a in (t.get('artists') or []))
                tab = ((t.get('album') or {}).get('name') or ab0 or u'').strip()
                tr = {'name': tnm, 'artist': tar, 'album': tab,
                      'dur': int((t.get('duration') or 0) / 1000)}
                if not song_ok(tr):
                    continue
                tn2 = M.norm(tnm)
                if tn2 in own or tn2 in added_names:
                    libhit.setdefault(tn2, {'name': tnm, 'artist': tar, 'album': tab,
                                            'drama': drama, 'year': dy0, 'dur': tr['dur']})
                    continue
                y2 = dy0
                if alpub and abs(alpub - dy0) <= 6:
                    y2 = alpub
                if not (1980 <= y2 <= 2026) or y2 not in add:
                    continue
                row2 = dict(tr)
                row2.update({'id': tid, 'pub': y2,
                             'alias': u' '.join(t.get('alias') or []),
                             'drama': drama,
                             'src': u'da%s' % M.norm(drama)[:12], 'pop': 0})
                pools[y2].append(row2)
                have_ids.add(tid)
                added_names.add(tn2)
                add[y2] += 1
                got += 1
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
                    # 库里已经有同名歌：不下载，但记进「库里命中」清单，
                    # 让 moviemark 把流行库里那首认成影视金曲（配额算账，不重复下载）。
                    ay0 = year_of((s.get('album') or {}).get('publishTime'))
                    cand = {'name': nm, 'artist': ar, 'album': ab,
                            'dur': int((s.get('duration') or 0) / 1000)}
                    if (kgfill.era_ok(ar, dy0)
                            and not (ay0 and ay0 - dy0 > 8 and COVER.search(ab or u''))
                            and song_ok(cand)):
                        libhit[nn] = {'name': nm, 'artist': ar, 'album': ab,
                                      'drama': drama, 'year': dy0,
                                      'dur': cand['dur']}
                        expand(s)     # 主题曲已在库里，照样展开它那张原声专辑
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
                expand(s)
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
    old = {}
    if os.path.exists(LIBHIT):
        try:
            old = json.load(open(LIBHIT, encoding='utf-8'))
        except Exception:
            old = {}
    old.update(libhit)
    json.dump(old, open(LIBHIT + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(LIBHIT + '.tmp', LIBHIT)
    print(u'库里命中清单共 %d 条（本次 %d）-> %s' % (len(old), len(libhit), LIBHIT), flush=True)
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
