# -*- coding: utf-8 -*-
"""酷狗影视金曲直补（kgfill）。

网易云侧的影视候选池已经见底（2000-2017 每年只剩个位数可用），但酷狗上还有大量
影视歌——尤其是 1980-1990 的港剧/内地剧主题曲（搜「射雕英雄传 主题曲」直接出
铁血丹心/世间始终你好）。这里按剧名搜酷狗，命中就下载入库并打【影视】标记。

证据 = 酷狗对「《剧名》 主题曲/插曲」这条查询返回的结果；年份取该剧在网易云资料里
的最早发行年。全程只碰酷狗，不碰网易云，可以和下载进程并行。

用法：python kgfill.py [--write] 1980 1999
"""
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, r'F:\Temp')
import acquire
from acquire import (LIB, norm, probe, ingest, lyric_kugou, clean_lrc, kg_search, http)
import fill6
from fill6 import cjk_ok, BADVER

T = r'F:\Temp'
RAW = os.path.join(T, 'movie-raw.json')
STATE = os.path.join(T, 'kg-state.json')
META = os.path.join(T, 'movie-meta-kg.json')
LOGF = os.path.join(T, 'movie.log')
TAG = u'【影视】'
acquire._host_min['mobiles.kugou.com'] = 0.6
acquire._host_min['trackercdn.kugou.com'] = 0.6

JUNK = re.compile(u'纯音乐|伴奏|翻唱|cover|dj|remix|版|现场|live|片段|花絮', re.I)
BOOK = re.compile(u'《(.{1,40}?)》')
MIN_DUR = 110
MIN_LRC = 5
CJK = re.compile(u'[\u4e00-\u9fff]')


def lrc_cjk_lines(txt):
    n = 0
    for ln in (txt or u'').splitlines():
        body = re.sub(r'\[\d+:\d+\.\d+\]', u'', ln)
        if len(CJK.findall(body)) >= 2:
            n += 1
    return n


def logline(s):
    with open(LOGF, 'a', encoding='utf-8') as f:
        f.write(s.rstrip() + u'\n')


def drama_years():
    """剧名 -> 最早发行年（来自网易云资料里的《》别名/标题）。"""
    raw = json.load(open(RAW, encoding='utf-8'))
    out = {}
    for k, row in raw.items():
        if not k.isdigit():
            continue
        y = row.get('pub') or 0
        if not (1980 <= y <= 2026):
            continue
        ev = u'%s %s' % (row.get('album') or u'', row.get('alias') or u'')
        for m in BOOK.finditer(ev):
            nm = m.group(1).strip()
            if len(nm) >= 2:
                cur = out.get(nm)
                if cur is None or y < cur:
                    out[nm] = y
    return out


def kg_get(h, want_dur):
    """按酷狗 hash 直接下载（免费曲目 status=1；VIP 曲目 status=2 直接跳过）。"""
    h = h.lower()
    key = hashlib.md5((h + 'kgcloudv2').encode()).hexdigest()
    j = http(u'http://trackercdn.kugou.com/i/v2/?key=%s&hash=%s&appid=1005&pid=2'
             u'&cmd=25&bitrate=320&behavior=download' % (key, h), u'http://www.kugou.com/')
    try:
        d = json.loads(j)
    except Exception:
        return None, u'kg badjson'
    if d.get('status') != 1 or not d.get('url'):
        return None, u'kg status=%s' % d.get('status')
    data = http(d['url'][0], u'http://www.kugou.com/', binary=True)
    if not data or len(data) < 150000:
        return None, u'kg tiny'
    p = r'F:\Temp\dl\kg_%s.bin' % h
    os.makedirs(r'F:\Temp\dl', exist_ok=True)
    open(p, 'wb').write(data)
    dur, br = probe(p)
    if want_dur and dur and dur < want_dur * 0.8:
        os.remove(p)
        return None, u'kg short %.0fs/%.0fs' % (dur, want_dur)
    return p, u'kg %dbps %.0fs' % (br, dur)


def artist_years():
    """歌手名 -> 网易云资料里出现过的发行年集合（离线判断年代用）。"""
    raw = json.load(open(RAW, encoding='utf-8'))
    out = {}
    for k, row in raw.items():
        if not k.isdigit():
            continue
        y = row.get('pub') or 0
        if not (1960 <= y <= 2026):
            continue
        for a in re.split(u'[、,，/&+（(]', row.get('artist') or u''):
            a = norm(a)
            if len(a) >= 2:
                out.setdefault(a, set()).add(y)
    return out


ART_YEARS = artist_years()


def era_ok(artist, y):
    """歌手在网易云资料里的发行年离这部剧 ±6 年内，就算年代对得上。"""
    for a in re.split(u'[、,，/&+（(]', artist or u''):
        a = norm(a)
        if len(a) >= 2:
            for yy in ART_YEARS.get(a, ()):
                if abs(yy - y) <= 6:
                    return True
    return False


def tag_year(path):
    """读文件里的年份标签（酷狗很多曲目带 date/year），读不到返回 0。"""
    import subprocess
    try:
        out = subprocess.run([acquire.FFPROBE, '-v', 'error',
                              '-show_entries', 'format_tags=date,year,original_year',
                              '-of', 'default=noprint_wrappers=1', path],
                             capture_output=True, text=True,
                             encoding='utf-8', errors='ignore').stdout
    except Exception:
        return 0
    for ln in out.splitlines():
        v = ln.split(':')[-1].strip()
        m = re.search(r'(19|20)\d{2}', v)
        if m:
            return int(m.group(0))
    return 0


def next_slot(year, used):
    """该年已有的 9NN 序号接着排，避免和 moviefill 撞号。"""
    if used is not None:
        return used
    mx = 899
    pre = u'%d-9' % year
    for f in os.listdir(LIB):
        if f.startswith(pre) and f.endswith('.mp3'):
            try:
                n = int(f[5:8])
                if n > mx:
                    mx = n
            except ValueError:
                pass
    return mx


def main(years, write=False):
    dy = drama_years()
    sel = sorted([(y, n) for n, y in dy.items() if y in years])
    print(u'目标年份 %s，剧名 %d 个' % (years, len(sel)), flush=True)
    try:
        st = json.load(open(STATE, encoding='utf-8'))
    except Exception:
        st = {}
    try:
        meta = json.load(open(META, encoding='utf-8'))
    except Exception:
        meta = {}
    own = set()
    for f in os.listdir(LIB):
        if f.endswith('.mp3'):
            own.add(norm(f.split(' - ', 2)[-1][:-4]))
    slots = {}
    got = 0
    for y, drama in sel:
        tried = 0
        for kw in (u'《%s》 主题曲' % drama, u'%s 插曲' % drama):
            rows = kg_search(kw, n=20)
            for r in rows:
                nm = (r.get('songname') or u'').strip()
                ar = (r.get('singername') or u'').strip()
                dur = r.get('duration') or 0
                h = r.get('hash')
                if not nm or not h or dur < MIN_DUR:
                    continue
                if JUNK.search(nm) or BADVER.search(nm) or not cjk_ok(nm, ar):
                    continue
                key = norm(nm)
                if key in own or st.get(key, {}).get('state') in ('ok', 'fail'):
                    continue
                if len(nm) < 2:
                    continue
                lrc = lyric_kugou(nm, ar, dur)
                if not lrc or lrc_cjk_lines(lrc) < MIN_LRC:
                    logline(u'%d KGSKIP %-22s %-14s 无歌词' % (y, nm[:22], ar[:14]))
                    st[key] = {'state': 'fail', 'why': u'no-lrc', 'name': nm, 'artist': ar}
                    continue
                if not write:
                    logline(u'%d KGDRY  %-22s %-14s 《%s》' % (y, nm[:22], ar[:14], drama))
                    st[key] = {'state': 'dry', 'name': nm, 'artist': ar, 'drama': drama}
                    continue
                p, why = kg_get(h, dur)
                if not p:
                    st[key] = {'state': 'fail', 'why': why, 'name': nm, 'artist': ar}
                    logline(u'%d KGMISS %-22s %-14s %s' % (y, nm[:22], ar[:14], why))
                    continue
                # 年份以曲目自带年份为准（剧名年份只是兜底）；落在别的年份区间就跳过，
                # 免得和网易云下载进程在同一年抢序号、也把现代翻唱塞进老剧年份。
                ty = tag_year(p)
                if not ty and y < 2000 and not era_ok(ar, y):
                    st[key] = {'state': 'fail', 'why': u'no-year-tag',
                               'name': nm, 'artist': ar}
                    logline(u'%d KGSKIP %-22s %-14s 老剧且曲目无年份、歌手年代也对不上'
                            % (y, nm[:22], ar[:14]))
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                    continue
                yy = ty or y
                if yy not in years:
                    st[key] = {'state': 'fail', 'why': u'year-out %d' % yy,
                               'name': nm, 'artist': ar}
                    logline(u'%d KGSKIP %-22s %-14s 自带年份 %d 不在本轮区间'
                            % (y, nm[:22], ar[:14], yy))
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                    continue
                slots[yy] = next_slot(yy, slots.get(yy)) + 1
                k = '%d-%03d' % (yy, slots[yy])
                base, res = ingest(p, yy, slots[yy], ar, nm, u'%d年影视金曲' % yy)
                if res != 'ok':
                    st[key] = {'state': 'fail', 'why': res, 'name': nm, 'artist': ar}
                    logline(u'%s KGFAIL %-22s %-14s %s' % (k, nm[:22], ar[:14], res[:100]))
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                    continue
                nb = base + TAG
                os.rename(os.path.join(LIB, base + '.mp3'), os.path.join(LIB, nb + '.mp3'))
                open(os.path.join(LIB, nb + '.lrc'), 'w', encoding='utf-8').write(
                    clean_lrc(lrc, ar, nm))
                try:
                    os.remove(p)
                except Exception:
                    pass
                own.add(key)
                st[key] = {'state': 'ok', 'file': nb, 'drama': drama, 'why': why, 'year': yy}
                meta[nb] = drama
                got += 1
                logline(u'%s KGOK   %-22s %-14s %s 《%s》' % (k, nm[:22], ar[:14], why, drama))
                tried += 1
                if got % 10 == 0:
                    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)
                    json.dump(meta, open(META, 'w', encoding='utf-8'), ensure_ascii=False)
                    print(u'  %d +%d' % (y, got), flush=True)
            if tried >= 6:
                break
        time.sleep(0.2)
    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(meta, open(META, 'w', encoding='utf-8'), ensure_ascii=False)
    print(u'完成 +%d（%s）' % (got, u'写入' if write else u'试运行'), flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    w = '--write' in args
    retry = '--retry' in args
    args = [a for a in args if a not in ('--write', '--retry')]
    ys = set(int(a) for a in args if a.isdigit()) or set(range(1980, 2000))
    if retry:
        try:
            st = json.load(open(STATE, encoding='utf-8'))
            keep = {k: v for k, v in st.items()
                    if v.get('state') == 'ok' or v.get('why') not in
                    (u'no-year-tag', u'year-out')}
            if len(keep) != len(st):
                json.dump(keep, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)
                print(u'重试：清掉 %d 条年份相关的失败记录' % (len(st) - len(keep)), flush=True)
        except Exception:
            pass
    main(ys, w)
