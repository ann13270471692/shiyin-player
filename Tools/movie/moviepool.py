# -*- coding: utf-8 -*-
"""影视金曲候选池 · 第一阶段：收歌单曲目，按专辑发行年分桶。

用法：python F:\\Temp\\moviepool.py            # 收歌单 + 出覆盖报告
      python F:\\Temp\\moviepool.py albums    # 只翻 OST 专辑（补缺口年份）
"""
import json, os, re, sys, time, urllib.parse
sys.path.insert(0, r'F:\Temp')
import acquire
from acquire import http, norm
import fill6                                    # 复用 cjk_ok / BADVER / norm 判定
from fill6 import cjk_ok, BADVER

acquire._host_min['music.163.com'] = 12.0        # 与下载进程并发，温和限速

OUT = r'F:\Temp\movie-pools'
RAW = r'F:\Temp\movie-raw.json'
REPORT = r'F:\Temp\movie-coverage.txt'
YEARS = list(range(1980, 2027))

# 影视证据：歌名/专辑/别名里出现这些才算影视金曲（人工种子除外）
OST_EV = re.compile(r'(原声|主题曲|片尾|插曲|片头|配乐|电视|电视剧|电影|影视|动漫|动画|剧场|音乐专辑|'
                    r'音乐剧|ost|soundtrack|bgm|《|》)', re.I)

PLAYLISTS = [
    14042914402,   # 忍不住跟唱的电视剧主题曲，全是童年回忆
    14382097717,   # 经典古装剧：前奏一响，宿命感拉满
    2887714563,    # 80年代影视歌曲
    7971224692,    # 70.80.90年代经典电视剧主题曲插曲
    317762614,     # 华语 老歌 经典影视金曲
    8776272148,    # 华语 | 90后回忆杀 经典电视剧主题曲
    8224332029,    # 【影视金曲】经典电视剧主题曲OST
    12315564197,   # 【影视金曲】经典影视剧主题曲
    1790595972,    # 『武侠』倚楼听风雨
    13062318670,   # 影视中封神的那些BGM（多为纯音乐，靠闸门过滤）
]

OST_KWS = ['电视原声带', '电影原声带', '影视原声带', '电视原声', '电影原声',
           '原声大碟', '电视剧 主题曲 插曲']


def yr_of(pt):
    if not pt:
        return 0
    try:
        return int(time.strftime('%Y', time.gmtime((pt or 0) / 1000.0)))
    except (OSError, ValueError, OverflowError):
        # 网易云偶有脏 publishTime：按毫秒算术推年份，离谱就当作未知
        try:
            y = 1970 + int((pt / 1000.0) // 31557600)
            return y if 1900 <= y <= 2035 else 0
        except (OSError, ValueError, OverflowError, TypeError):
            return 0


def jget(u, ref='https://music.163.com/'):
    t = http(u, ref)
    if not t:
        return None
    s = t.strip()
    if not s or s[0] not in '{[':
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def batch_detail(ids):
    """api/song/detail?ids=[..] —— 带 album.publishTime，一次 80 首。"""
    out = {}
    ids = [int(i) for i in ids]
    for i in range(0, len(ids), 80):
        chunk = ids[i:i + 80]
        u = 'https://music.163.com/api/song/detail?ids=%s' % urllib.parse.quote(
            json.dumps(chunk, separators=(',', ':')))
        j = jget(u) or {}
        for s in j.get('songs') or []:
            al = s.get('album') or {}
            out[int(s['id'])] = {
                'id': int(s['id']),
                'name': s.get('name') or '',
                'artist': '/'.join(a.get('name', '') for a in (s.get('artists') or [])),
                'dur': int(s.get('duration') or 0) // 1000,
                'album': al.get('name') or '',
                'pub': yr_of(al.get('publishTime')),
                'alias': ' '.join(s.get('alias') or []),
            }
        print('   detail %d/%d' % (min(i + 80, len(ids)), len(ids)), flush=True)
    return out


def load_raw():
    if os.path.exists(RAW):
        try:
            return json.load(open(RAW, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_raw(raw):
    tmp = RAW + '.tmp'
    json.dump(raw, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, RAW)


def phase_playlists():
    raw = load_raw()
    for pid in PLAYLISTS:
        if 'pl_%d' % pid in raw:
            print('playlist %d cached' % pid, flush=True)
            continue
        j = jget('https://music.163.com/api/v3/playlist/detail?id=%d&n=1000' % pid)
        pl = (j or {}).get('playlist') or {}
        tids = [t['id'] for t in (pl.get('trackIds') or []) if t.get('id')]
        print('playlist %d %s -> %d tracks' % (pid, (pl.get('name') or '')[:22], len(tids)), flush=True)
        det = batch_detail(tids)
        for sid, row in det.items():
            row['src'] = 'pl%d' % pid
            raw.setdefault(str(sid), row)
        raw['pl_%d' % pid] = {'name': pl.get('name'), 'n': len(tids)}
        save_raw(raw)
    return raw


def coverage(raw):
    own = set()
    for f in os.listdir(acquire.LIB):
        if f.endswith('.mp3'):
            own.add(norm(f.split(' - ', 2)[-1][:-4]))
    pop_ids = set()
    try:
        for k, v in json.load(open(acquire.STATE, encoding='utf-8')).items():
            if v.get('id'):
                pop_ids.add(int(v['id']))
    except Exception:
        pass
    buckets = {}
    for k, row in raw.items():
        if not k.isdigit():
            continue
        y = row.get('pub') or 0
        if not (1980 <= y <= 2026):
            continue
        if not cjk_ok(row['name'], row['artist']) or BADVER.search(row['name']):
            continue
        if norm(row['name']) in own or row['id'] in pop_ids:
            continue
        # 影视证据：专辑来源要求专辑名里有原声/主题曲/《剧名》；歌单与人工种子本身已是影视向
        ev = '%s %s %s' % (row.get('name', ''), row.get('album', ''), row.get('alias', ''))
        src = str(row.get('src', ''))
        if not (OST_EV.search(ev) or src.startswith('seed') or src.startswith('pl')):
            continue
        buckets.setdefault(y, []).append(row)
    lines = []
    tot = 0
    for y in YEARS:
        rows = sorted(buckets.get(y, []), key=lambda r: -r['id'])
        tot += len(rows)
        lines.append('%d\t%d' % (y, len(rows)))
    head = ['候选总数 %d（去重后，已排除曲库已有/流行池已排/非华语/伴奏）' % tot,
            '年份\t候选', *lines]
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(head) + '\n')
    print('\n'.join(head[:4]))
    print('... 详见 %s' % REPORT, flush=True)
    return buckets


def batch_pop(ids):
    """v3 详情带 pop（0-100 热度），用来在一年内挑最火的。"""
    ids = [int(i) for i in ids]
    out = {}
    for i in range(0, len(ids), 80):
        chunk = ids[i:i + 80]
        c = json.dumps([{'id': x} for x in chunk], separators=(',', ':'))
        j = jget('https://music.163.com/api/v3/song/detail?c=' + urllib.parse.quote(c)) or {}
        for s in j.get('songs') or []:
            out[int(s['id'])] = float(s.get('pop') or 0)
        print('   pop %d/%d' % (min(i + 80, len(ids)), len(ids)), flush=True)
    return out


def phase_albums(raw, deficit, per_year=12):
    """翻 OST 专辑：按关键词搜专辑 -> 按发行年筛 -> 取专辑曲目（只补不够 20 首的年份）。

    注意：1999 年前的原声专辑在网易云基本都是再版，publishTime 不可信，
    所以这里只处理 1999 年及以后；更早的年份靠人工种子列表。
    """
    deficit = {y for y in deficit if y >= 1999}
    if not deficit:
        print('no deficit years', flush=True)
        return raw
    filled = {y: 0 for y in deficit}
    for kw in OST_KWS:
        off, total = 0, None
        while total is None or off < min(total, 300):
            j = jget('https://music.163.com/api/search/get?s=%s&type=10&limit=50&offset=%d'
                     % (urllib.parse.quote(kw), off))
            res = (j or {}).get('result') or {}
            als = res.get('albums') or []
            total = int(res.get('albumCount') or 0)
            print('albums %-12s off=%-4d total=%d got=%d' % (kw, off, total, len(als)), flush=True)
            if not als:
                break
            for a in als:
                y = yr_of(a.get('publishTime'))
                if y not in deficit or filled[y] >= per_year:
                    continue
                aid = a.get('id')
                key = 'al_%d' % aid
                if key in raw:
                    continue
                ja = jget('https://music.163.com/api/album/%d' % aid) or {}
                al = ja.get('album') or {}
                ay = yr_of(al.get('publishTime'))
                filled[ay] = filled.get(ay, 0) + 1
                raw[key] = {'skip': True, 'name': al.get('name'), 'y': ay}
                for s in (al.get('songs') or []):
                    sid = int(s['id'])
                    row = {'id': sid, 'name': s.get('name') or '',
                           'artist': '/'.join(x.get('name', '') for x in (s.get('artists') or [])),
                           'dur': int(s.get('duration') or 0) // 1000,
                           'album': al.get('name') or '', 'pub': ay,
                           'alias': ' '.join(s.get('alias') or []), 'src': 'al%d' % aid}
                    raw.setdefault(str(sid), row)
                save_raw(raw)
            off += 50
        save_raw(raw)
    return raw


def phase_rank(raw):
    """给候选打热度，按年写池子（pop 降序）。"""
    b = coverage(raw)
    ids = [r['id'] for rows in b.values() for r in rows]
    print('rank: %d candidates' % len(ids), flush=True)
    pop = batch_pop(ids)
    for rows in b.values():
        for r in rows:
            r['pop'] = pop.get(r['id'], 0)
    for y in YEARS:
        rows = sorted(b.get(y, []), key=lambda r: (-r.get('pop', 0), r['name']))
        seen, keep = set(), []
        for r in rows:                        # 同名只留热度最高的一条
            k = norm(r['name'])
            if k in seen:
                continue
            seen.add(k)
            keep.append(r)
        b[y] = keep
        json.dump(keep, open(os.path.join(OUT, '%d.json' % y), 'w', encoding='utf-8'),
                  ensure_ascii=False)
    print('pools written to %s' % OUT, flush=True)
    return b


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pl'
    raw = load_raw()
    if mode == 'pl':
        raw = phase_playlists()
        coverage(raw)
    elif mode == 'albums':
        need = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        b = coverage(raw)
        deficit = [y for y in YEARS if len(b.get(y, [])) < need]
        print('deficit years: %s' % deficit, flush=True)
        raw = phase_albums(raw, deficit)
        coverage(raw)
    elif mode == 'rank':
        phase_rank(raw)
