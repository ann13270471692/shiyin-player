# -*- coding: utf-8 -*-
# 影视金曲配额核对（纯本地，不联网）：
#   have  = 已下载 ok 的影视文件 + 从流行库里认出来的影视（pop-movie.json）
#   pool  = 候选池里还没下的条目数
# 输出每年的缺口，以及候选池够不够补。
import json
import os

T = r'F:\Temp'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
Y0, Y1 = 1980, 2026
QUOTA = 200


def load(p, d):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d


def main():
    # 已下载的影视：state 文件里 ok 的条目
    have = {}
    for st in sorted(f for f in os.listdir(T)
                     if f.startswith('movie-state') and f.endswith('.json')):
        for k, v in load(os.path.join(T, st), {}).items():
            if v.get('state') == 'ok':
                y = k.split('-')[0]
                if y.isdigit():
                    have[int(y)] = have.get(int(y), 0) + 1
    # 从流行库里认出来的影视（不下载、不改名，只算配额）
    cred = {}
    for k, v in load(os.path.join(T, 'pop-movie.json'), {}).items():
        y = v.get('year')
        if isinstance(y, int):
            cred[y] = cred.get(y, 0) + 1
    # 候选池
    pool = {}
    for y in range(Y0, Y1 + 1):
        p = os.path.join(T, 'movie-pools', '%d.json' % y)
        if os.path.exists(p):
            pool[y] = len(load(p, []))

    tot_h = tot_c = tot_p = 0
    short = []
    print('%-6s %6s %6s %6s %6s %8s' % ('年', '已下', '认库', '合计', '缺口', '候选池'))
    for y in range(Y0, Y1 + 1):
        h = have.get(y, 0)
        c = cred.get(y, 0)
        t = h + c
        need = max(0, QUOTA - t)
        tot_h += h
        tot_c += c
        tot_p += pool.get(y, 0)
        if need:
            short.append((y, need, pool.get(y, 0)))
        print('%-6d %6d %6d %6d %6d %8d' % (y, h, c, t, need, pool.get(y, 0)))
    print('-' * 40)
    print('合计 已下 %d + 认库 %d = %d / %d' % (tot_h, tot_c, tot_h + tot_c, QUOTA * (Y1 - Y0 + 1)))
    print('缺 %d 首；未满年份 %d 个；候选池总量 %d'
          % (QUOTA * (Y1 - Y0 + 1) - (tot_h + tot_c), len(short), tot_p))
    thin = [x for x in short if x[2] < x[1]]
    print('候选池不够的年份 %d 个：%s'
          % (len(thin), ', '.join('%d(缺%d/池%d)' % x for x in thin[:20])))


if __name__ == '__main__':
    main()
