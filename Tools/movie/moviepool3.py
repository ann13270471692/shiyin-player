# -*- coding: utf-8 -*-
# 离线扩池：把 movie-raw.json（1.8 万条，带 pub/alias/album 权威资料）里
# 还没进池、也没下过的候选，按发行年补进 movie-pools。不联网。
#   python moviepool3.py            # 只看会加多少
#   python moviepool3.py --write    # 真写盘（原子替换，fill 进程可并发读）
import importlib
import json
import os
import sys

sys.path.insert(0, r'F:\Temp')
M = importlib.import_module('moviefill')
RAW = r'F:\Temp\movie-raw.json'
POOL = r'F:\Temp\movie-pools'
REC = r'F:\Temp\pop-movie.json'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'


def main(write):
    raw = json.load(open(RAW, encoding='utf-8'))
    cred = json.load(open(REC, encoding='utf-8'))
    cred_ids = set(int(v.get('id') or 0) for v in cred.values() if isinstance(v, dict))
    own = set()
    for f in os.listdir(LIB):
        if f.endswith('.mp3'):
            own.add(M.norm(f.split(' - ', 2)[-1][:-4]))

    pools = {}
    have_ids = set()
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

    # 已下载/已认库的 id 也跳过（state 里存了 id）
    done_ids = set(cred_ids)
    for st in ('movie-state.json', 'movie-state-a.json', 'movie-state-b.json',
               'movie-state-c.json'):
        try:
            d = json.load(open(os.path.join(r'F:\Temp', st), encoding='utf-8'))
        except Exception:
            continue
        for v in d.values():
            if isinstance(v, dict) and v.get('id'):
                done_ids.add(int(v['id']))

    add = {y: 0 for y in M.YEARS}
    skip = {'dup': 0, 'lib': 0, 'done': 0, 'gate': 0, 'year': 0}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        sid = int(v.get('id') or 0)
        if not sid or sid in have_ids:
            skip['dup'] += 1
            continue
        if sid in done_ids:
            skip['done'] += 1
            continue
        if M.norm(v.get('name') or u'') in own:
            skip['lib'] += 1
            continue
        y = v.get('pub')
        if not isinstance(y, int) or y not in add:
            skip['year'] += 1
            continue
        drama, bad = M.gate(v, {sid: v}, y)     # 离线闸门（含日文过滤）
        if bad:
            skip['gate'] += 1
            continue
        row = dict(v)
        row['pop'] = row.get('pop') or 60.0
        pools[y].append(row)
        have_ids.add(sid)
        add[y] += 1

    print('跳过：已在池 %d / 已下过 %d / 库里同名 %d / 年份不合 %d / 闸门 %d'
          % (skip['dup'], skip['done'], skip['lib'], skip['year'], skip['gate']))
    thin = [y for y in M.YEARS if add[y]]
    print('新增 %d 条，覆盖 %d 个年份' % (sum(add.values()), len(thin)))
    for y in M.YEARS:
        if add[y]:
            print('  %d +%d -> %d' % (y, add[y], len(pools[y])))
    if not write:
        print('（dry run，加 --write 才写盘）')
        return
    for y in M.YEARS:
        if not add[y]:
            continue
        p = os.path.join(POOL, '%d.json' % y)
        json.dump(pools[y], open(p + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(p + '.tmp', p)
    print('已写盘')


if __name__ == '__main__':
    main('--write' in sys.argv[1:])
