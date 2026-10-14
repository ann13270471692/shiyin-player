# -*- coding: utf-8 -*-
r"""合并 movie-meta.json：旧条目（只保留文件还在的）+ 审计产出 + 各下载进程的 --meta 分片。
用法：python F:\Temp\mergemeta.py
"""
import json, os, glob

META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
PARTS = [r'F:\Temp\movie-meta-audit.json', r'F:\Temp\movie-meta-a.json',
         r'F:\Temp\movie-meta-b.json', r'F:\Temp\movie-meta-c.json'] + \
        glob.glob(r'F:\Temp\movie-meta-*.json')


def main():
    have = set()
    for n in os.listdir(LIB):
        if n.lower().endswith('.mp3'):
            have.add(os.path.splitext(n)[0])
    try:
        old = json.load(open(META, encoding='utf-8'))
    except Exception:
        old = {}
    kept = {k: v for k, v in old.items() if k in have and v}
    print('旧 %d -> 文件仍在 %d' % (len(old), len(kept)))

    merged = dict(kept)
    added = 0
    for p in sorted(set(PARTS)):
        if not os.path.exists(p) or p == META:
            continue
        try:
            d = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            print('跳过', p, e)
            continue
        n = 0
        for k, v in d.items():
            if not v or k not in have:
                continue
            if k not in merged:
                n += 1
            merged[k] = v
        added += n
        print('%s -> 新增 %d（共 %d 条）' % (os.path.basename(p), n, len(d)))

    tmp = META + '.tmp'
    json.dump(merged, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    os.replace(tmp, META)
    print('movie-meta.json 现在 %d 条（新增 %d）' % (len(merged), added))
    tagged = sum(1 for n in have if n.endswith('【影视】'))
    print('库里【影视】文件 %d 个，其中带剧名 %d 个'
          % (tagged, sum(1 for n in have if n.endswith('【影视】') and merged.get(n))))


main()
