# -*- coding: utf-8 -*-
"""影视金曲下载器：每年 20 首，池子不够就用候选充裕的年份超额补到总量 940。

用法：
  python F:\\Temp\\moviefill.py --plan          # 只看分配计划，不下载
  python F:\\Temp\\moviefill.py                # 按 20/年 下载
  python F:\\Temp\\moviefill.py --topup        # 先按 20/年，再把缺口摊给充裕年份
  python F:\\Temp\\moviefill.py 1990 1991      # 只做指定年份
"""
import json, os, re, sys, time
sys.path.insert(0, r'F:\Temp')
import acquire
from acquire import (LIB, norm, probe, ingest, lyric_netease, lyric_kugou,
                     clean_lrc, safe)
import fill6
from fill6 import cjk_ok, BADVER, ne_dl

acquire._host_min['music.163.com'] = 1.2          # 与流行池并发，双方都温和
acquire._host_min['api.qijieya.cn'] = 3.0
acquire._host_min['api.injahow.cn'] = 3.0

POOL = r'F:\Temp\movie-pools'
STATE = r'F:\Temp\movie-state.json'
REC = r'F:\Temp\pop-movie.json'      # 已下载流行歌里认出来的影视金曲（算额度，不重下）
ALSO = []                            # 只读的其他 state 文件：并行下载时用来看到全局已下载数
LOG = r'F:\Temp\movie.log'
YEARS = list(range(1980, 2027))
BASE = 200
TOTAL = 200 * len(YEARS)
TAG = '【影视】'
START_IDX = 900
META_OUT = r''      # --meta：本进程补出来的剧名，写这里给 movie-meta.json 用

BOOK = re.compile(u'[《]([^》]{1,30})[》]')
OST = re.compile(u'(电视连续剧|电视原声|电影原声|影视原声|原声大碟|原声带|原声音乐|原声专辑|'
                 u'原声唱片|原声|OST|主题曲|主题歌|片尾曲|片头曲|插曲|配乐|动漫|动画|剧场版)')
JUNK = set([u'两岸三地', u'原唱经典名曲珍藏', u'影视', u'电视', u'电影', u'经典', u'精选',
            u'原声带', u'原声大碟', u'原声', u'OST', u'单曲'])
JUNKART = re.compile(u'(群星|Various|V\\.A|Mole|Original Soundtrack|Original Cast|无名氏)')
JUNKNAME = re.compile(u'[（(]?(配乐|纯音乐|伴奏|片段|节选)[）)]?')


def clean_pre(s):
    s = (s or '').strip(u' \u3000-—_（）()[]')
    s = re.sub(u'^\\d{2,4}版', '', s)
    s = re.sub(u'(系列|版)$', '', s)
    s = s.strip(u' \u3000-—_')
    if len(s) < 2 or s in JUNK:
        return ''
    return s


def flush_meta(mm):
    """把本进程认出来的剧名并进 --meta 文件（供 movie-meta.json 合并）。"""
    if not META_OUT or not mm:
        return
    with acquire.lock:
        try:
            cur = json.load(open(META_OUT, encoding='utf-8'))
        except Exception:
            cur = {}
        cur.update(mm)
        json.dump(cur, open(META_OUT + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(META_OUT + '.tmp', META_OUT)


def pub_year(pt):
    """publishTime 常见是毫秒时间戳，也可能是秒/年份字符串。"""
    if isinstance(pt, str):
        pt = pt.strip()
        return int(pt[:4]) if pt[:4].isdigit() else 0
    if not isinstance(pt, (int, float)) or not pt:
        return 0
    a = abs(pt)
    try:
        if a > 1e11:
            return time.gmtime(pt / 1000.0).tm_year
        if a > 1e8:
            return time.gmtime(pt).tm_year
    except Exception:
        return 0
    if 1000 <= a <= 2100:
        return int(pt)
    return 0


def details(ids):
    """按 id 批量取网易云权威元数据（专辑名/发行年/alias），给闸门用。"""
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 80):
        u = ('https://music.163.com/api/song/detail?ids=['
             + ','.join(str(x) for x in ids[i:i + 80]) + ']')
        t = acquire.http(u, 'https://music.163.com/')
        try:
            d = json.loads(t)
        except Exception:
            continue
        for s in d.get('songs') or []:
            ab = s.get('album') or {}
            arts = s.get('artists') or []
            ar = u','.join(a.get('name') or u'' for a in arts if isinstance(a, dict))
            if not ar:
                a0 = s.get('artist')
                ar = (a0.get('name') or u'') if isinstance(a0, dict) else (a0 or u'')
            try:
                out[int(s['id'])] = {'name': s.get('name') or '',
                                     'alias': u','.join(s.get('alias') or []),
                                     'artist': ar,
                                     'album': ab.get('name') or '',
                                     'pub': pub_year(ab.get('publishTime'))}
            except Exception:
                continue
    return out


def lrc_cjk_lines(s):
    """数真正有字的歌词行（去掉时间标签），配乐 cue 通常没几行。"""
    n = 0
    for ln in (s or u'').splitlines():
        t = re.sub(u'\\[.*?\\]', u'', ln).strip()
        if len(re.findall(u'[\\u4e00-\\u9fff]', t)) >= 2:
            n += 1
    return n


def gate(c, det, year):
    """用候选 id 自己的资料把关：发行年 + 影视证据。返回 (剧名, 失败原因)。"""
    d = det.get(int(c['id']))
    if not d:
        return '', u'查不到该 id 的资料'
    y = d['pub']
    if not y:
        return '', u'资料里没有发行年'
    if abs(y - year) > 1:
        return '', u'发行年 %d 与目标 %d 不符' % (y, year)
    al, nm, ab = d['alias'], d['name'], d['album']
    if JUNKART.search(d.get('artist') or u''):
        return '', u'歌手是曲库/群星（%s）' % (d.get('artist') or u'')[:16]
    if JUNKNAME.search(nm):
        return '', u'标题像配乐/纯音乐（%s）' % nm[:18]
    m = BOOK.search(al) or BOOK.search(nm)
    if m:
        return m.group(1).strip(), ''
    mo = OST.search(al) or OST.search(ab)
    if mo:
        pre = clean_pre(ab[:OST.search(ab).start()]) if OST.search(ab) else clean_pre(ab)
        return (pre or clean_pre(ab)), ''
    if ab and (ab == nm or nm in ab):
        return clean_pre(ab), ''
    return '', u'无影视证据（专辑「%s」）' % ab[:24]


def rec_by_year():
    try:
        d = json.load(open(REC, encoding='utf-8'))
    except Exception:
        return {}
    out = {}
    for v in d.values():
        y = int(v.get('year') or 0)
        if y:
            out[y] = out.get(y, 0) + 1
    return out


def logline(s):
    with acquire.lock:
        open(LOG, 'a', encoding='utf-8').write(s + '\n')


def load_state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {}


def save_state(st):
    with acquire.lock:
        json.dump(st, open(STATE + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(STATE + '.tmp', STATE)


def pool_of(y):
    p = os.path.join(POOL, '%d.json' % y)
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding='utf-8'))


def plan(st, topup=False):
    """返回 {year: 目标总数}。topup 时把补不上的额度摊给候选充裕的年份。"""
    ok = {y: sum(1 for k, v in st.items() if k[:4] == str(y) and v.get('state') == 'ok') for y in YEARS}
    for f in ALSO:
        try:
            other = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for k, v in other.items():
            if v.get('state') == 'ok':
                y = int(k[:4])
                if y in ok:
                    ok[y] += 1
    rec = rec_by_year()
    cap = {y: ok[y] + rec.get(y, 0) + len(pool_of(y)) for y in YEARS}
    tgt = {y: min(BASE, cap[y]) for y in YEARS}
    if topup:
        gap = TOTAL - sum(tgt.values())
        rich = {y: cap[y] - BASE for y in YEARS if cap[y] > BASE}
        room = sum(rich.values())
        while gap > 0 and room > 0:
            for y, r in sorted(rich.items()):
                if gap <= 0 or r <= 0:
                    continue
                add = max(1, int(gap * r / room))
                add = min(add, r, gap)
                tgt[y] += add
                rich[y] -= add
                gap -= add
                room -= add
            rich = {y: r for y, r in rich.items() if r > 0}
    return tgt, ok, cap


def owned():
    own = set()
    for f in os.listdir(LIB):
        if f.endswith('.mp3'):
            own.add(norm(f.split(' - ', 2)[-1][:-4]))
    return own


def main(years, topup=False):
    st = load_state()
    tgt, ok, cap = plan(st, topup)
    rec = rec_by_year()
    own = owned()
    tmp = r'F:\Temp\dl-tmp-movie-%d.bin' % os.getpid()   # 每个进程自己的临时文件，避免并发互踩
    meta_new = {}
    for year in years:
        rows = pool_of(year)
        need = max(0, tgt[year] - ok[year] - rec.get(year, 0))
        print('%d: ok=%d rec=%d target=%d pool=%d need=%d'
              % (year, ok[year], rec.get(year, 0), tgt[year], len(rows), need), flush=True)
        if need <= 0 or not rows:
            continue
        det = details([c['id'] for c in rows])   # 闸门用：候选 id 的权威资料
        idxs = [int(k.split('-')[1]) for k in st
                if k[:4] == str(year) and len(k.split('-')) > 1 and k.split('-')[1].isdigit()]
        for f in ALSO:                       # 并行时也要接着其他 state 里同一年已用的序号
            try:
                for k in json.load(open(f, encoding='utf-8')):
                    if k[:4] == str(year) and len(k.split('-')) > 1 and k.split('-')[1].isdigit():
                        idxs.append(int(k.split('-')[1]))
            except Exception:
                pass
        used = max(idxs or [START_IDX - 1])
        got = 0
        for c in rows:
            if got >= need:
                break
            if norm(c['name']) in own:
                continue
            drama, bad = gate(c, det, year)      # 闸门：发行年 + 影视证据
            if bad:
                logline('%d SKIP   %-22s %-14s 闸门：%s'
                        % (year, c['name'][:22], c['artist'][:14], bad[:70]))
                continue
            # 先取歌词：影视金曲要求有词（顺带挡掉 OST 专辑里的纯音乐配乐），也省一次下载
            lrc = lyric_netease(c['id']) or lyric_kugou(c['name'], c['artist'], c.get('dur', 0))
            if not lrc:
                logline('%d SKIP   %-22s %-14s 无歌词（纯音乐/无词，跳过）'
                        % (year, c['name'][:22], c['artist'][:14]))
                continue
            if lrc_cjk_lines(lrc) < 5:
                logline('%d SKIP   %-22s %-14s 歌词只有 %d 行有字，像配乐'
                        % (year, c['name'][:22], c['artist'][:14], lrc_cjk_lines(lrc)))
                continue
            used += 1
            k = '%d-%03d' % (year, used)
            src, why = ne_dl(c['id'], c.get('dur', 0), tmp)
            if not src:
                st[k] = {'state': 'fail', 'why': why[:120], 'name': c['name'], 'artist': c['artist']}
                logline('%s MISS %-22s %-14s %s' % (k, c['name'][:22], c['artist'][:14], why[:110]))
                continue
            base, res = ingest(src, year, used, c['artist'], c['name'], '%d年影视金曲' % year)
            if res != 'ok':
                st[k] = {'state': 'fail', 'why': res, 'name': c['name'], 'artist': c['artist']}
                logline('%s FAIL %-22s %-14s %s' % (k, c['name'][:22], c['artist'][:14], res[:110]))
                try:
                    os.remove(src)
                except Exception:
                    pass
                continue
            nb = base + TAG
            os.rename(os.path.join(LIB, base + '.mp3'), os.path.join(LIB, nb + '.mp3'))
            got += 1
            own.add(norm(c['name']))
            open(os.path.join(LIB, nb + '.lrc'), 'w', encoding='utf-8').write(
                clean_lrc(lrc, c['artist'], c['name']))
            st[k] = {'state': 'ok', 'src': 'mt', 'file': nb, 'why': why[:90],
                     'id': c['id'], 'drama': drama}
            meta_new[nb] = drama
            logline('%s OK   %-22s %-14s %s' % (k, c['name'][:22], c['artist'][:14], why[:110]))
            try:
                os.remove(src)
            except Exception:
                pass
            if got % 10 == 0:
                print('  %d %d/%d' % (year, got, need), flush=True)
                save_state(st)
        save_state(st)
        flush_meta(meta_new)
        print('  %d done +%d (ok now %d)' % (year, got, ok[year] + got), flush=True)
    save_state(st)
    flush_meta(meta_new)


if __name__ == '__main__':
    args = [x for x in sys.argv[1:]]
    topup = '--topup' in args
    args = [a for a in args if a != '--topup']
    for flag, var in (('--state', 'STATE'), ('--log', 'LOG'), ('--meta', 'META_OUT')):
        if flag in args:
            i = args.index(flag)
            globals()[var] = args[i + 1]
            del args[i:i + 2]
    while '--also' in args:
        i = args.index('--also')
        ALSO.append(args[i + 1])
        del args[i:i + 2]
    for flag, host in (('--meting', 'api.qijieya.cn'), ('--meting2', 'api.injahow.cn'),
                       ('--ne', 'music.163.com')):
        if flag in args:
            i = args.index(flag)
            acquire._host_min[host] = float(args[i + 1])
            if flag == '--meting':
                acquire._host_min['api.injahow.cn'] = float(args[i + 1])
            del args[i:i + 2]
    st = load_state()
    if '--plan' in args:
        tgt, ok, cap = plan(st, True)
        print('year  ok  pool  target')
        for y in YEARS:
            print('%d  %3d  %4d  %3d' % (y, ok[y], cap[y] - ok[y], tgt[y]))
        print('total target=%d ok=%d' % (sum(tgt.values()), sum(ok.values())))
        raise SystemExit
    main([int(x) for x in args] or YEARS, topup)
