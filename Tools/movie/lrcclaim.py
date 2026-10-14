# -*- coding: utf-8 -*-
# 离线认库②：歌词文件里写着「电视剧《X》片尾曲」这类注释的，直接认成影视金曲。
#   只看前 12 行、或 [xx:] 注释行，避免把歌词正文里提到的书名当证据。
#   python lrcclaim.py          # 只看
#   python lrcclaim.py --write  # 写盘
import json
import os
import re

LIB = r'F:\DeepSeek Workspace\时事分析\音乐集合'
REC = r'F:\Temp\pop-movie.json'
META = r'F:\DeepSeek Workspace\时事分析\shiyin-player\SyncServer\movie-meta.json'
PAT = re.compile(u'(电影|电视剧|网络剧|偶像剧|动画电影|动画片|TVB剧集|剧集|片头曲|片尾曲|插曲|主题曲|片头|片尾|推广曲|彩蛋曲|预热曲|ED|OP)'
                 u'.{0,14}《(.{2,20})》')


def main(write):
    rec = json.load(open(REC, encoding='utf-8'))
    try:
        meta = json.load(open(META, encoding='utf-8'))
    except Exception:
        meta = {}
    hits = []
    for f in sorted(os.listdir(LIB)):
        if not f.endswith('.lrc'):
            continue
        stem = f[:-4]
        if stem in meta or u'【影视】' in stem:
            continue
        try:
            txt = open(os.path.join(LIB, f), encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        lines = txt.splitlines()
        cand = lines[:12] + [x for x in lines if x.strip().startswith('[')]
        drama = None
        for ln in cand:
            m = PAT.search(ln)
            if m:
                drama = m.group(2).strip()
                break
        if not drama:
            continue
        y = stem[:4]
        hits.append((stem, drama, int(y) if y.isdigit() else 0))

    print('歌词里写明影视出处的：%d 首' % len(hits))
    for stem, drama, y in hits:
        print('  %s  ← %s（%d）' % (stem, drama, y))
    if not write:
        print('（dry run，加 --write 才写盘）')
        return
    for stem, drama, y in hits:
        rec[stem] = {'alias': u'歌词注释', 'drama': drama, 'id': 0, 'year': y}
        meta[stem] = drama
    json.dump(rec, open(REC + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(REC + '.tmp', REC)
    json.dump(meta, open(META + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(META + '.tmp', META)
    print('已写入：pop-movie.json %d 条，movie-meta.json %d 条' % (len(rec), len(meta)))


if __name__ == '__main__':
    main('--write' in __import__('sys').argv[1:])
