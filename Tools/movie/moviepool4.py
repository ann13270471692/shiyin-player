# -*- coding: utf-8 -*-
"""第四轮影视扩池：搜网易云「影视歌单」再抓曲目。

前面已经抓过 300 多个歌单（movie-raw.json 里的 pl_ 键），但都是人工挑的；
这里按关键词搜歌单，把没抓过的、名字像影视金曲的补进来。
只联网搜歌单 + 取详情，不下载音频。单进程跑，music.163.com 间隔 12 秒。
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'F:\Temp')
import acquire
import moviepool as MP

acquire._host_min['music.163.com'] = 12.0

KEYWORDS = [
    u'影视金曲 主题曲', u'经典电视剧主题曲', u'电影插曲 华语',
    u'古装剧 主题曲', u'武侠 影视歌曲', u'电视剧 片尾曲',
    u'影视原声 华语 歌曲', u'OST 华语 主题曲', u'年代剧 主题曲',
    u'偶像剧 主题曲 华语', u'动画 主题曲 中文', u'影视金曲 粤语',
]
GOOD = re.compile(u'影视|电视|电影|主题曲|插曲|片尾|片头|原声|OST|金曲|剧情', re.I)
BAD = re.compile(u'纯音乐|bgm|配乐|钢琴|吉他|翻唱|dj|remix|车载|抖音版', re.I)
MAX_NEW = 45          # 最多新抓多少个歌单
MIN_TRACKS = 25       # 曲目太少的歌单不要


def search_playlists(kw, pages=3):
    out = []
    for p in range(pages):
        j = MP.jget(u'https://music.163.com/api/search/get?s=%s&type=1000&limit=50&offset=%d'
                    % (urllib.parse.quote(kw), p * 50)) or {}
        res = j.get('result') or {}
        lst = res.get('playlists') or []
        for pl in lst:
            pid = pl.get('id')
            nm = pl.get('name') or u''
            n = pl.get('trackCount') or 0
            if not pid or n < MIN_TRACKS:
                continue
            if not GOOD.search(nm) or BAD.search(nm):
                continue
            out.append((pid, nm, n))
        if not lst:
            break
    return out


def main():
    raw = MP.load_raw()
    have = {k[3:] for k in raw if k.startswith('pl_')}
    seen = set(have)
    added_pl = 0
    new_ids = []
    for kw in KEYWORDS:
        hits = search_playlists(kw)
        fresh = [h for h in hits if str(h[0]) not in seen]
        print(u'关键词「%s」命中 %d，未抓过 %d' % (kw, len(hits), len(fresh)), flush=True)
        for pid, nm, n in fresh[:6]:
            seen.add(str(pid))
            new_ids.append((pid, nm, n))
        if len(new_ids) >= MAX_NEW:
            break
    print(u'计划新增歌单 %d 个' % len(new_ids), flush=True)
    tot = 0
    for pid, nm, n in new_ids:
        j = MP.jget(u'https://music.163.com/api/v3/playlist/detail?id=%d&n=1000' % pid)
        pl = (j or {}).get('playlist') or {}
        tids = [t['id'] for t in (pl.get('trackIds') or []) if t.get('id')]
        if not tids:
            print(u'  %d %s -> 空' % (pid, nm[:20]), flush=True)
            raw['pl_%d' % pid] = {'name': pl.get('name'), 'n': 0}
            MP.save_raw(raw)
            continue
        det = MP.batch_detail(tids)
        before = len(raw)
        for sid, row in det.items():
            row['src'] = 'pl%d' % pid
            raw.setdefault(str(sid), row)
        added = len(raw) - before
        tot += added
        added_pl += 1
        raw['pl_%d' % pid] = {'name': pl.get('name'), 'n': len(tids)}
        MP.save_raw(raw)
        print(u'  %d %s -> %d 首，新增 %d 条（累计 %d）'
              % (pid, (pl.get('name') or nm)[:20], len(tids), added, tot), flush=True)
    print(u'完成：新歌单 %d 个，新曲目 %d 条' % (added_pl, tot), flush=True)


if __name__ == '__main__':
    main()
