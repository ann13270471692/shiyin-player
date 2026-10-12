# -*- coding: utf-8 -*-
"""生成拾音 App 图标：深色渐变底 + 金色声波条，无 alpha 通道。"""
import math
from PIL import Image, ImageDraw, ImageFilter

S = 1024
img = Image.new("RGB", (S, S))
dr = ImageDraw.Draw(img)

# 垂直渐变：深紫 -> 深夜蓝
top = (26, 16, 51)
bottom = (10, 22, 40)
for y in range(S):
    t = y / (S - 1)
    r = int(top[0] + (bottom[0] - top[0]) * t)
    g = int(top[1] + (bottom[1] - top[1]) * t)
    b = int(top[2] + (bottom[2] - top[2]) * t)
    dr.line([(0, y), (S, y)], fill=(r, g, b))

# 柔光圆斑（左上暖光）
glow = Image.new("RGB", (S, S), (0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([S*0.15, S*0.1, S*0.85, S*0.8], fill=(60, 40, 10))
glow = glow.filter(ImageFilter.GaussianBlur(220))
img = Image.blend(img, Image.blend(img, glow, 0.0), 1.0)
# 叠加柔光（加法近似）
from PIL import ImageChops
img = ImageChops.add(img, glow)

dr = ImageDraw.Draw(img)

# 声波条：13 根，正弦包络，圆角端
gold = (245, 197, 66)
gold_dim = (200, 150, 40)
cx = S / 2
bar_w = 44
gap = 26
n = 13
total = n * bar_w + (n - 1) * gap
x0 = cx - total / 2
max_h = 430
min_h = 90

for i in range(n):
    x = x0 + i * (bar_w + gap)
    env = math.sin(math.pi * (i + 0.5) / n)
    h = min_h + (max_h - min_h) * (0.35 + 0.65 * env)
    y0 = cx - h / 2
    y1 = cx + h / 2
    # 中间几根更亮
    c = gold if 4 <= i <= 8 else gold_dim
    dr.rounded_rectangle([x, y0, x + bar_w, y1], radius=bar_w / 2, fill=c)

# 底部细线 + 顶部留白平衡：加一条播放进度线
dr.rounded_rectangle([x0, cx + max_h / 2 + 70, x0 + total, cx + max_h / 2 + 78],
                     radius=4, fill=(120, 100, 60))

img.save(r"F:\DeepSeek Workspace\时事分析\shiyin-player\Resources\Assets.xcassets\AppIcon.appiconset\icon-1024.png")
print("saved icon-1024.png", img.size, img.mode)
