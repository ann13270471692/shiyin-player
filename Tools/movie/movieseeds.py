# -*- coding: utf-8 -*-
"""人工种子解析 v2：歌名必须完全一致；用 v3 热度 + 歌手匹配 + 垃圾标记剔除翻唱/AI/纯音乐。

会顺带删掉上一版误加的 seed 行（未被本轮重新选中的）。
"""
import importlib.util, json, os, re, sys, time, urllib.parse
sys.path.insert(0, r'F:\Temp')
import acquire
from acquire import http, norm
from fill6 import cjk_ok, BADVER

acquire._host_min['music.163.com'] = 1.1

spec = importlib.util.spec_from_file_location('movie_seeds', r'F:\Temp\movie-seeds.py')
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)

RAW = r'F:\Temp\movie-raw.json'
raw = json.load(open(RAW, encoding='utf-8')) if os.path.exists(RAW) else {}
old_seed = {k for k, v in raw.items()
            if k.isdigit() and str(v.get('src', '')).startswith('seed')}

JUNK = re.compile(r'(cover|翻唱|翻自|翻自|dj|remix|live|男声|女声|港版|版$|伴奏|纯音乐|纯音|'
                  r'疗愈|儿歌|唢呐|葫芦丝|洞箫|二胡|古筝|钢琴|交响|轻音乐|乐团|群星|抖音|铃声|'
                  r'彩铃|片段|片段|和声|钢琴版|吉他|music|beat|纯|指弹|演奏)', re.I)


def jget(u):
    t = http(u, 'https://music.163.com/')
    if not t:
        return None
    s = t.strip()
    if not s or s[0] not in '{[':
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def batch_pop(ids):
    ids = [int(i) for i in ids]
    out = {}
    for i in range(0, len(ids), 80):
        c = json.dumps([{'id': x} for x in ids[i:i + 80]], separators=(',', ':'))
        j = jget('https://music.163.com/api/v3/song/detail?c=' + urllib.parse.quote(c)) or {}
        for s in j.get('songs') or []:
            out[int(s['id'])] = float(s.get('pop') or 0)
    return out


# ---- 1. 收集每个种子的「歌名完全一致」候选 ----
cands = {}          # seedkey -> [(id, name, artist, album, dur, alias, artist_hit)]
for year in sorted(ms.SEEDS):
    for it in ms.SEEDS[year]:
        title, artist = (it.split('|', 1) + [''])[:2]
        artist = artist.strip()
        sk = 'seed:%d:%s' % (year, title)
        want = norm(title)
        arts = [norm(a) for a in artist.split('/') if a.strip()]
        j = jget('https://music.163.com/api/search/get?s=%s&type=1&limit=15' % urllib.parse.quote(
            title + (' ' + artist.split('/')[0] if artist else '')))
        got = []
        for s in ((j or {}).get('result') or {}).get('songs') or []:
            nm = norm(s.get('name') or '')
            if nm != want:
                continue
            sa = norm('/'.join(a.get('name', '') for a in (s.get('artists') or [])))
            hit = bool(arts) and any(a in sa or sa in a for a in arts)
            if arts and not hit:
                continue
            got.append((int(s['id']), s.get('name') or title,
                        '/'.join(a.get('name', '') for a in (s.get('artists') or [])),
                        (s.get('album') or {}).get('name') or '',
                        int(s.get('duration') or 0) // 1000,
                        ' '.join(s.get('alias') or []), hit))
        cands[sk] = got
        print('%d %-14s -> %d 候选' % (year, title[:14], len(got)), flush=True)

# ---- 2. 批量取热度，择优 ----
allids = sorted({c[0] for v in cands.values() for c in v})
print('pop for %d ids' % len(allids), flush=True)
pop = batch_pop(allids)

picked, new_ids, bad = {}, set(), 0
for sk, got in cands.items():
    best, bestkey = None, None
    for c in got:
        sid, name, ar, al = c[0], c[1], c[2], c[3]
        p = pop.get(sid, 0)
        junk = bool(JUNK.search(name or '')) or bool(JUNK.search(al or '')) or BADVER.search(name or '')
        if junk or not cjk_ok(name, ar):
            bad += 1
            continue
        if p < 15:
            continue
        if not c[6] and p < 40:          # 没指定歌手时要求更热，避免冷门翻唱
            continue
        key = (1 if c[6] else 0, p)
        if bestkey is None or key > bestkey:
            best, bestkey = c, key
    if best:
        picked[sk] = best
        new_ids.add(best[0])

# ---- 3. 写回：删掉旧的、未被重新选中的 seed 行 ----
for k in old_seed - new_ids:
    raw.pop(k, None)
for sk, c in picked.items():
    year = int(sk.split(':')[1])
    raw[str(c[0])] = {'id': c[0], 'name': c[1], 'artist': c[2], 'dur': c[4],
                      'album': c[3], 'pub': year, 'alias': c[5], 'src': 'seed%d' % year}
    raw[sk] = 'done'
json.dump(raw, open(RAW, 'w', encoding='utf-8'), ensure_ascii=False)

print('picked=%d dropped-old=%d junk-skipped=%d' % (len(picked), len(old_seed - new_ids), bad), flush=True)
for sk, got in cands.items():
    if sk not in picked:
        print('  NO-PICK %s  (%d 候选, pop=%s)' % (
            sk, len(got), [round(pop.get(c[0], 0)) for c in got[:5]]), flush=True)
