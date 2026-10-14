# -*- coding: utf-8 -*-
r"""扩充影视候选池：把流行候选池（F:\Temp\pools，45157 条带 id）里有影视证据、
库里还没有、发行年对得上的候选，追加进 F:\Temp\movie-pools\<年>.json。
用法：python F:\Temp\moviepool2.py 1980 1995        # 指定年份区间（含端点）
      python F:\Temp\moviepool2.py                 # 全部年份
"""
import json, os, re, sys, glob
sys.path.insert(0, r'F:\Temp')
import acquire
import moviefill as M

acquire._host_min['music.163.com'] = 3.0
POPPOOL = r'F:\Temp\pools'
MOVPOOL = r'F:\Temp\movie-pools'
LIB = M.LIB
LOG = r'F:\Temp\moviepool2.log'


def log(s):
    with acquire.lock:
        open(LOG, 'a', encoding='utf-8').write(s + '\n')
        print(s, flush=True)


def lib_norm():
    s = set()
    for n in os.listdir(LIB):
        if n.lower().endswith('.mp3'):
            s.add(acquire.norm(n))
    return s


def evidence(d):
    """返回剧名；没有影视证据返回 ''。"""
    al, nm, ab = d['alias'], d['name'], d['album']
    m = M.BOOK.search(al) or M.BOOK.search(nm)
    if m:
        return m.group(1).strip()
    mo = M.OST.search(al) or M.OST.search(ab)
    if mo:
        pre = M.clean_pre(ab[:M.OST.search(ab).start()]) if M.OST.search(ab) else M.clean_pre(ab)
        return pre or M.clean_pre(ab)
    if ab and (ab == nm or nm in ab):
        return M.clean_pre(ab)
    return ''


def main():
    args = [int(x) for x in sys.argv[1:] if x.isdigit()]
    lo, hi = (args[0], args[-1]) if len(args) >= 2 else (1980, 2026)
    have = lib_norm()
    grand = 0
    for p in sorted(glob.glob(os.path.join(POPPOOL, '*.json'))):
        y = int(os.path.splitext(os.path.basename(p))[0])
        if not (lo <= y <= hi):
            continue
        try:
            rows = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        cand = [r for r in rows if isinstance(r, dict) and r.get('id')
                and acquire.norm(r.get('name', '')) not in have]
        if not cand:
            continue
        det = M.details([r['id'] for r in cand])
        if not det:
            log('%d 资料全空（疑似被限流），本轮跳过' % y)
            continue
        keep = []
        for r in cand:
            d = det.get(int(r['id']))
            if not d:
                continue
            if M.JUNKART.search(d.get('artist') or '') or M.JUNKNAME.search(d['name']):
                continue
            dr = evidence(d)
            if not dr:
                continue
            pub = d.get('pub') or 0
            if pub and abs(pub - y) > 1:
                continue
            keep.append({'id': int(r['id']), 'name': d['name'], 'artist': d.get('artist') or r.get('artist'),
                         'dur': r.get('dur', 0), 'album': d['album'], 'pub': pub or y,
                         'alias': d['alias'], 'src': 'pop%d' % y, 'pop': 0, 'drama': dr})
        outp = os.path.join(MOVPOOL, '%d.json' % y)
        try:
            cur = json.load(open(outp, encoding='utf-8'))
        except Exception:
            cur = []
        ids = {int(x['id']) for x in cur if isinstance(x, dict) and x.get('id')}
        add = [k for k in keep if k['id'] not in ids]
        cur.extend(add)
        tmp = outp + '.tmp'
        json.dump(cur, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, outp)
        grand += len(add)
        log('%d 流行候选 %d -> 新增影视候选 %d（池共 %d）' % (y, len(cand), len(add), len(cur)))
    log('合计新增 %d（年份区间 %d-%d）' % (grand, lo, hi))


if __name__ == '__main__':
    main()
