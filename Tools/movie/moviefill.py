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
                     clean_lrc, safe, get_kugou)
import fill6
from fill6 import cjk_ok, BADVER, ne_dl

acquire._host_min['music.163.com'] = 1.2          # 与流行池并发，双方都温和
acquire._host_min['api.qijieya.cn'] = 3.0
acquire._host_min['api.injahow.cn'] = 3.0
acquire._host_min['mobiles.kugou.com'] = 2.0      # 酷狗搜索会被限流，慢一点
acquire._host_min['trackercdn.kugou.com'] = 1.0

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
        t = u''
        for _try in range(5):
            t = acquire.http(u, 'https://music.163.com/') or u''
            if u'操作频繁' in t or u'"code":405' in t:
                time.sleep(90 + 60 * _try)          # IP 级限流：退避要够长，别把限流当无资料
                continue
            break
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


# 离线闸门：候选池里已存了权威资料（pub/alias/album），网易云限流时不再回查
LOCAL_GATE = False
# 只用酷狗取词：网易云被限流时，回查网易歌词会白白卡住几十秒
NO_NE_LYRIC = False
# 以前下载失败过的候选（两台源都没音源）不再重试
SKIP_FAILED = False
# 候选热度下限（网易云 pop 0-100）：在线扩池捞进大量影视原声专辑里的纯音乐配乐，
# 一首要白跑一次酷狗+网易云取词才被判掉，先用热度挡在门外。0=不卡。
MIN_POP = 0.0
# 配乐专业户（电影原声带里纯音乐配乐的作曲/演奏者）名单：这些人在日志里
# 累计几千次「无歌词」，一首要白跑十几秒取词，直接在闸门离线拒掉。
CUE_ARTISTS = set()
# 跑内学习：同一歌手两次取不到歌词，就当成配乐专业户，后面的候选离线拒掉，
# 不再白跑取词。学到的名单写进 CUE_LEARN，下次跑直接加载。
NO_LRC = set()
LRC_MISS = {}
CUE_LEARN = r'F:\Temp\cue-learned.json'
# 时长下限（秒）：原声带里的配乐片段普遍很短，取词前离线判掉。0=不卡。
MIN_DUR = 0.0
# 跳过每年池子排序后的前 N 条：让多进程错开工作，不去抢同一批候选。
SKIP_TOP = 0
# 两台 meting 都没音源时，退到酷狗下载（约一半 MISS 属于这种）
KG_FALLBACK = False


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
    if CUE_ARTISTS and (d.get('artist') or u'').strip() in CUE_ARTISTS:
        return '', u'配乐专业户（%s）' % (d.get('artist') or u'')[:16]
    if (d.get('artist') or u'').strip() in NO_LRC:
        return '', u'同歌手已两次无歌词，判为配乐（%s）' % (d.get('artist') or u'')[:16]
    if MIN_DUR > 0:
        dv = c.get('dur') or d.get('dur') or 0
        try:
            if dv and float(dv) < MIN_DUR:
                return '', u'时长仅 %d 秒（配乐/片段）' % int(dv)
        except (TypeError, ValueError):
            pass
    if not cjk_ok(nm, d.get('artist') or u''):
        return '', u'日文/非华语（%s）' % (d.get('artist') or u'')[:16]
    if MIN_POP > 0:
        pv = c.get('pop', d.get('pop', None))
        if pv is not None:
            try:
                if float(pv) < MIN_POP:
                    return '', u'热度太低（pop=%s，多为配乐/冷门）' % pv
            except (TypeError, ValueError):
                pass
    m = BOOK.search(al) or BOOK.search(nm)
    dn = (d.get('drama') or u'').strip()
    if dn and (norm(dn) in norm(nm) or norm(dn) in norm(al) or norm(dn) in norm(ab)
               or str(c.get('src') or u'').startswith(u'da')):
        # 按剧名搜出来的候选（src=ds…）或同张原声专辑展开的（src=da…）
        return dn, ''
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
    # Windows：别的进程（监控、或别的 fill 读 --also）可能正占着目标文件，重试几次
    for _ in range(10):
        try:
            os.replace(STATE + '.tmp', STATE)
            return True
        except PermissionError:
            time.sleep(0.5)
    logline('状态文件被占用，这次没存上：%s' % STATE)
    return False


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


def failed_names():
    """以前试过但失败（多半是两台 meting 源都没音源）的候选歌名，
    不再重复浪费酷狗/网易云/metings 请求。"""
    out = set()
    for f in [STATE] + list(ALSO):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for v in d.values():
            if v.get('state') == 'fail' and v.get('name'):
                out.add(norm(v['name']))
    return out


def main(years, topup=False):
    st = load_state()
    tgt, ok, cap = plan(st, topup)
    rec = rec_by_year()
    own = owned()
    failed = failed_names() if SKIP_FAILED else set()
    print('跳过历史失败候选 %d 个歌名' % len(failed), flush=True)
    tmp = r'F:\Temp\dl-tmp-movie-%d.bin' % os.getpid()   # 每个进程自己的临时文件，避免并发互踩
    meta_new = {}
    for year in years:
        rows = pool_of(year)
        if SKIP_TOP:
            rows = rows[SKIP_TOP:]
        need = max(0, tgt[year] - ok[year] - rec.get(year, 0))
        print('%d: ok=%d rec=%d target=%d pool=%d need=%d'
              % (year, ok[year], rec.get(year, 0), tgt[year], len(rows), need), flush=True)
        if need <= 0 or not rows:
            continue
        if LOCAL_GATE:
            # 限流期间用池子里已有的资料把关；seed 行的年份是占位的，本轮不碰
            det = {int(c['id']): c for c in rows
                   if not str(c.get('src', u'')).startswith('seed')}
        else:
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
            if norm(c['name']) in failed:
                continue
            drama, bad = gate(c, det, year)      # 闸门：发行年 + 影视证据
            if bad:
                logline('%d SKIP   %-22s %-14s 闸门：%s'
                        % (year, c['name'][:22], c['artist'][:14], bad[:70]))
                continue
            # 先取歌词：影视金曲要求有词（顺带挡掉 OST 专辑里的纯音乐配乐），也省一次下载
            if LOCAL_GATE:
                lrc = lyric_kugou(c['name'], c['artist'], c.get('dur', 0))
                if not lrc and not NO_NE_LYRIC:
                    lrc = lyric_netease(c['id'])
            else:
                lrc = lyric_netease(c['id']) or lyric_kugou(c['name'], c['artist'], c.get('dur', 0))
            if not lrc or lrc_cjk_lines(lrc) < 5:
                a = (c.get('artist') or u'').strip()
                why = (u'无歌词（纯音乐/无词，跳过）' if not lrc
                       else u'歌词只有 %d 行有字，像配乐' % lrc_cjk_lines(lrc))
                if a:
                    LRC_MISS[a] = LRC_MISS.get(a, 0) + 1
                    if LRC_MISS[a] >= 2 and a not in NO_LRC:
                        NO_LRC.add(a)
                        try:
                            json.dump(sorted(NO_LRC), open(CUE_LEARN + '.tmp', 'w',
                                                           encoding='utf-8'), ensure_ascii=False)
                            os.replace(CUE_LEARN + '.tmp', CUE_LEARN)
                        except Exception:
                            pass
                logline('%d SKIP   %-22s %-14s %s' % (year, c['name'][:22], c['artist'][:14], why))
                continue
            used += 1
            k = '%d-%03d' % (year, used)
            src, why = ne_dl(c['id'], c.get('dur', 0), tmp)
            via = 'mt'
            if not src and KG_FALLBACK:
                # 网易云两台 meting 都没音源时，退到酷狗（只取它有的最高码率，不做升样）
                src, why = get_kugou(c['name'], c['artist'], c.get('dur', 0))
                via = 'kg'
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
            st[k] = {'state': 'ok', 'src': via, 'file': nb, 'why': why[:90],
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
    if '--local-gate' in args:
        globals()['LOCAL_GATE'] = True
        args = [a for a in args if a != '--local-gate']
    if '--no-ne-lyric' in args:
        globals()['NO_NE_LYRIC'] = True
        args = [a for a in args if a != '--no-ne-lyric']
    if '--skip-failed' in args:
        globals()['SKIP_FAILED'] = True
        args = [a for a in args if a != '--skip-failed']
    if '--min-pop' in args:
        i = args.index('--min-pop')
        globals()['MIN_POP'] = float(args[i + 1])
        del args[i:i + 2]
    if '--min-dur' in args:
        i = args.index('--min-dur')
        globals()['MIN_DUR'] = float(args[i + 1])
        del args[i:i + 2]
    if '--skip-top' in args:
        i = args.index('--skip-top')
        globals()['SKIP_TOP'] = int(args[i + 1])
        del args[i:i + 2]
    if '--kg' in args:
        globals()['KG_FALLBACK'] = True
        args = [a for a in args if a != '--kg']
    if '--cue-artists' in args:
        i = args.index('--cue-artists')
        try:
            globals()['CUE_ARTISTS'] = set(json.load(open(args[i + 1], encoding='utf-8')))
        except Exception as e:
            print('读配乐名单失败：%s' % e, flush=True)
        del args[i:i + 2]
    if os.path.exists(CUE_LEARN):
        try:
            globals()['NO_LRC'] = set(json.load(open(CUE_LEARN, encoding='utf-8')))
            print('载入已学到的配乐歌手 %d 个' % len(NO_LRC), flush=True)
        except Exception:
            pass
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
