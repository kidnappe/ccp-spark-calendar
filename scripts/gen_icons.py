# 生成「日历·星」图标的多尺寸 PNG（与 icons/icon-calendar.svg 几何一致）
# 用法: python scripts/gen_icons.py
from PIL import Image, ImageDraw
import os

STAR = [(64,50),(67.53,61.15),(79.22,61.06),(69.71,67.85),(73.4,78.94),
        (64,72),(54.6,78.94),(58.29,67.85),(48.78,61.06),(60.47,61.15)]

def draw(size):
    s = size / 128.0
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    def rr(x, y, w, h, r, fill):
        d.rounded_rectangle([x*s, y*s, (x+w)*s, (y+h)*s], radius=r*s, fill=fill)
    def cir(cx, cy, r, fill):
        d.ellipse([(cx-r)*s, (cy-r)*s, (cx+r)*s, (cy+r)*s], fill=fill)
    rr(8, 8, 112, 112, 24, (163, 45, 45, 255))      # 红底圆角方块
    rr(28, 30, 72, 74, 12, (255, 255, 255, 255))    # 白色日历卡
    rr(28, 30, 72, 20, 12, (178, 34, 34, 255))      # 红色标题条
    d.rectangle([28*s, 40*s, 100*s, 50*s], fill=(178, 34, 34, 255))
    cir(44, 40, 3.5, (255, 255, 255, 255))          # 装订孔
    cir(84, 40, 3.5, (255, 255, 255, 255))
    d.polygon([(x*s, y*s) for x, y in STAR], fill=(217, 164, 65, 255))  # 金星
    return img

out = os.path.join(os.path.dirname(__file__), '..', 'icons')
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)
for sz in (512, 256, 180, 64, 48, 32, 16):
    draw(sz).save(os.path.join(out, f'icon-calendar-{sz}.png'))
print('generated:', os.listdir(out))
