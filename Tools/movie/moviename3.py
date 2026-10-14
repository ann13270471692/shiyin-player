# -*- coding: utf-8 -*-
"""给影视金曲补剧名：alias《》 -> 文件名标题《》 -> 原声带专辑名 -> 补查 netease v3 aliases。
输出 SyncServer/movie-meta.json：{ "<mp3 基础名>": "<剧名>" }
"""
import json, os, re, sys, time, urllib.request, urllib.parse

sys.path.insert(0, r'F:\Temp')
import acquire  # 复用它的 cookie / 限速
acquire._host_min['music.163.com'] = 1.1

ST = json.load(open(r'F:\Temp\movie-state.json', encoding='utf-8'))
RAW = json.load(open(r'F:\Temp\movie-raw.json', encoding='utf-8'))

BOOK = re.compile(r'[《]([^》]{1,30})[》]')
OST = re.compile(r'(电视连续剧歌曲集|电视连续剧|电视原声带|电视原声|电影原声大碟|电影原声带|电影原声|影视原声带|影视原声大碟|影视原声|原声大碟|原声带|原声音乐|原声专辑|原声唱片|原声|OST)')
OST2 = re.compile(r'(电视剧主题曲|电视剧主题歌|电视剧歌曲|电视剧插曲|电视连续剧歌曲|电影主题曲)')
JUNK = {'两岸三地', '原唱经典名曲珍藏', '影视', '电视', '电影', '经典', '精选'}


def clean_pre(s):
    s = s.strip(' ·-—_（）()[]')
    s = re.sub(r'^\d{2,4}版', '', s)          # 87版红楼梦 -> 红楼梦
    s = re.sub(r'(系列|版)$', '', s)
    s = s.strip(' ·-—_')
    if len(s) < 2 or s in JUNK:
        return ''
    return s


def from_alias(text):
    m = BOOK.search(text or '')
    return m.group(1).strip() if m else ''


def from_album(album):
    m = OST.search(album or '') or OST2.search(album or '')
    if not m:
        return ''
    return clean_pre(album[:m.start()])


def title_of(fname):
    # "1987-905 - 陈志新 - 潜海姑娘(电影纪录片《潜海姑娘》选曲)【影视】"
    parts = fname.split(' - ')
    return parts[2] if len(parts) >= 3 else fname


meta = {}
need = []
OVR = {'1988-901 - 金铭 - 世上只有妈妈好【影视】': '小婉君'}
for slot, v in ST.items():
    if v.get('state') != 'ok':
        continue
    base = v['file']
    r = RAW.get(str(v.get('id'))) or {}
    name = OVR.get(base) or from_alias(r.get('alias') or '') or from_alias(title_of(base)) or from_album(r.get('album') or '')
    if name:
        meta[base] = name[:16]
    else:
        need.append((base, v.get('id'), r.get('album') or ''))

print('accepted ok:', len(meta) + len(need), '| 已解析剧名:', len(meta), '| 待补查:', len(need))

# 补查 v3 detail（每批 100 个 id）
ids = [i for _, i, _ in need if i]
got = {}
for k in range(0, len(ids), 100):
    batch = ids[k:k + 100]
    qs = urllib.parse.urlencode({'ids': ','.join(str(i) for i in batch),
                                 'c': json.dumps([{'id': i, 'v': 0} for i in batch], separators=(',', ':'))})
    for attempt in range(3):
        try:
            txt = acquire.http('https://music.163.com/api/v3/song/detail?' + qs)
            if not txt:
                raise RuntimeError('empty response')
            d = json.loads(txt)
            for s in d.get('songs', []):
                al = ' '.join(s.get('aliases') or [])
                nm = from_alias(al) or from_alias(s.get('name') or '') or from_album((s.get('album') or {}).get('name') or '')
                if nm:
                    got[s['id']] = nm
            break
        except Exception as e:
            print('  detail retry', k, attempt, e)
            time.sleep(2)
    time.sleep(1.2)

still = []
for base, i, alb in need:
    nm = got.get(i, '')
    if nm:
        meta[base] = nm[:16]
    else:
        still.append((base, alb))
print('补查后仍无剧名:', len(still))

# 已下载流行歌里认出来的影视金曲：直接进剧名表（App 据此把它们归到影视类，不重命名不重下）
try:
    pm = json.load(open(r'F:\Temp\pop-movie.json', encoding='utf-8'))
except Exception:
    pm = {}
add = 0
for base, v in pm.items():
    if base not in meta and v.get('drama'):
        meta[base] = str(v['drama'])[:16]
        add += 1
print('并入已下载的影视向流行歌:', add)

out = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
json.dump(meta, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)
print('wrote', out, len(meta), 'entries')

with open(r'F:\Temp\moviename-report.txt', 'w', encoding='utf-8') as f:
    f.write('有剧名 %d / 无剧名 %d\n\n== 样例 ==\n' % (len(meta), len(still)))
    for k in sorted(meta)[:40]:
        f.write('%s => %s\n' % (k, meta[k]))
    f.write('\n== 仍无剧名（前 60）==\n')
    for b, a in still[:60]:
        f.write('%s || album=%s\n' % (b, a))
print(open(r'F:\Temp\moviename-report.txt', encoding='utf-8').read()[:1500])
