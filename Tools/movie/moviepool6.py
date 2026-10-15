# -*- coding: utf-8 -*-
r"""第六轮歌单扩池：跟 moviepool4 一样，但关键词从命令行给，专门挖 1980-1991 的老影视歌单
（无线/佳艺/邵氏/嘉禾/金庸古龙/粤语影视金曲这些方向，pool4 的通用词挖不到）。
用法：python moviepool6.py [--max 40] 关键词1 关键词2 ...
"""
import json
import os
import sys

sys.path.insert(0, r'F:\Temp')
import moviepool as MP
import moviepool4 as P4
import acquire
# pool5 也在跑网易云（按剧名搜），这边放慢到 14 秒一次，两边合起来不至于踩限流
acquire._host_min['music.163.com'] = 14.0

MAX_NEW = 40


def main(kws, max_new):
    raw = MP.load_raw()
    have = {k[3:] for k in raw if k.startswith('pl_')}
    seen = set(have)
    plan = []
    for kw in kws:
        hits = P4.search_playlists(kw)
        fresh = [h for h in hits if str(h[0]) not in seen]
        print(u'关键词「%s」命中 %d，未抓过 %d' % (kw, len(hits), len(fresh)), flush=True)
        for pid, nm, n in fresh[:5]:
            seen.add(str(pid))
            plan.append((pid, nm, n))
        if len(plan) >= max_new:
            break
    print(u'计划新增歌单 %d 个' % len(plan), flush=True)
    tot = 0
    got = 0
    for pid, nm, n in plan:
        j = MP.jget(u'https://music.163.com/api/v3/playlist/detail?id=%d&n=1000' % pid)
        pl = (j or {}).get('playlist') or {}
        tids = [t['id'] for t in (pl.get('trackIds') or []) if t.get('id')]
        if not tids:
            raw['pl_%d' % pid] = {'name': pl.get('name'), 'n': 0}
            MP.save_raw(raw)
            continue
        det = MP.batch_detail(tids)
        before = len(raw)
        for sid, row in det.items():
            row['src'] = u'pl%d' % pid
            raw.setdefault(str(sid), row)
        added = len(raw) - before
        tot += added
        got += 1
        raw['pl_%d' % pid] = {'name': pl.get('name'), 'n': len(tids)}
        MP.save_raw(raw)
        print(u'  %d %s -> %d 首，新增 %d 条（累计 %d）'
              % (pid, (pl.get('name') or nm)[:22], len(tids), added, tot), flush=True)
    print(u'完成：新歌单 %d 个，新曲目 %d 条' % (got, tot), flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    mx = 40
    if '--max' in args:
        i = args.index('--max')
        mx = int(args[i + 1])
        del args[i:i + 2]
    main(args, mx)
