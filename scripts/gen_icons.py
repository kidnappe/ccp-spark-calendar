# 生成「朱砂印·日历·星火」图标的多尺寸 PNG（与 icons/icon-calendar.svg 几何一致）
# 用法: python scripts/gen_icons.py
from PIL import Image, ImageDraw
import os

# 星火四角星顶点（128 坐标，中心 64,69，外径 10）
STAR = [(64,59),(66.9,66.1),(74,69),(66.9,71.9),
        (64,79),(61.1,71.9),(54,69),(61.1,66.1)]

def draw(size):
    s = size / 128.0
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    def rr(x, y, w, h, r, fill=None, outline=None, width=1):
        d.rounded_rectangle([x*s, y*s, (x+w)*s, (y+h)*s], radius=r*s, fill=fill,
                            outline=outline, width=max(1, round(width*s)))
    def cir(cx, cy, r, fill):
        d.ellipse([(cx-r)*s, (cy-r)*s, (cx+r)*s, (cy+r)*s], fill=fill)
    rr(8, 8, 112, 112, 22, (139, 26, 26, 255))                  # 朱砂印身
    rr(20, 20, 88, 88, 12, (240, 233, 216, 255))                # 宣纸印芯
    rr(26, 26, 76, 76, 9, None, (139, 26, 26, 255), 1.5)        # 印内框（细线）
    rr(30, 32, 68, 58, 5, (240, 233, 216, 255), (201, 169, 98, 255), 2.5)  # 日历页（档案金线框，主角）
    rr(30, 32, 68, 16, 4, (139, 26, 26, 255))                   # 朱砂表头条
    cir(43, 44, 3, (240, 233, 216, 255))                        # 装订孔
    cir(85, 44, 3, (240, 233, 216, 255))
    d.polygon([(x*s, y*s) for x, y in STAR], fill=(139, 26, 26, 255))  # 星火（朱砂）
    rr(38, 84, 16, 3, 1.5, (201, 169, 98, 255))                 # 日期短线（档案金）
    rr(60, 84, 28, 3, 1.5, (201, 169, 98, 255))
    return img

out = os.path.join(os.path.dirname(__file__), '..', 'icons')
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)
for sz in (512, 256, 180, 64, 48, 32, 16):
    draw(sz).save(os.path.join(out, f'icon-calendar-{sz}.png'))
print('generated:', os.listdir(out))
