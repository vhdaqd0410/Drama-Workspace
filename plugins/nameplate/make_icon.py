# -*- coding: utf-8 -*-
"""生成软件图标：剧本 + 人物 + 表格元素，输出 icon.ico"""
from PIL import Image, ImageDraw, ImageFont
import os

SIZE = 256


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_icon():
    # 透明背景
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ---- 背景：深红圆角方块 + 底部渐变效果 ----
    bg = (122, 31, 31, 255)          # 深红
    bg_light = (200, 70, 40, 255)    # 略亮
    rounded_rect(draw, (16, 16, SIZE-16, SIZE-16), 48, bg)
    # 顶部高光
    rounded_rect(draw, (24, 24, SIZE-24, int(SIZE*0.42)), 40, (180, 55, 40, 120))

    # ---- 白色剧本文档卡片（居中偏上）----
    doc_x0, doc_y0 = int(SIZE*0.28), int(SIZE*0.12)
    doc_x1, doc_y1 = int(SIZE*0.72), int(SIZE*0.92)
    rounded_rect(draw, (doc_x0, doc_y0, doc_x1, doc_y1), 20, (255, 255, 255, 255))

    # 文档标题横条（顶部）
    draw.rounded_rectangle((doc_x0+14, doc_y0+14, doc_x1-14, doc_y0+34), 8, (227, 108, 10, 255))

    # 文档内的文字行（模拟人物/场景列表）
    text_color = (180, 180, 185, 255)
    line_y = doc_y0 + 52
    # 人物行（带小圆点）
    for i in range(3):
        # 小圆点
        cx = doc_x0 + 24
        draw.ellipse((cx-5, line_y-5, cx+5, line_y+5), fill=(122, 31, 31, 255))
        # 文字条
        draw.rounded_rectangle((doc_x0+36, line_y-6, doc_x0+36+int((doc_x1-doc_x0)*0.55), line_y+6), 4, text_color)
        line_y += 34
    # 分隔线
    draw.line((doc_x0+14, line_y-4, doc_x1-14, line_y-4), fill=(220, 220, 225, 255), width=2)
    line_y += 18
    # 场景行
    draw.rounded_rectangle((doc_x0+24, line_y-6, doc_x0+24+int((doc_x1-doc_x0)*0.7), line_y+6), 4, (200, 200, 205, 255))
    line_y += 30
    draw.rounded_rectangle((doc_x0+24, line_y-6, doc_x0+24+int((doc_x1-doc_x0)*0.5), line_y+6), 4, (210, 210, 215, 255))

    # ---- 放大镜（象征"识别/解析"）----
    lens_cx, lens_cy = int(SIZE*0.72), int(SIZE*0.86)
    lens_r = 30
    draw.ellipse((lens_cx-lens_r, lens_cy-lens_r, lens_cx+lens_r, lens_cy+lens_r),
                 outline=(255, 255, 255, 255), width=10)
    draw.line((lens_cx+lens_r*0.7, lens_cy+lens_r*0.7, lens_cx+lens_r*1.5, lens_cy+lens_r*1.5),
              fill=(255, 255, 255, 255), width=12)

    # ---- 底部装饰：金色小圆点(代表"时间字幕") ----
    dot_y = SIZE - 28
    for i, dx in enumerate([-36, -18, 0, 18, 36]):
        cx = SIZE//2 + dx
        draw.ellipse((cx-4, dot_y-4, cx+4, dot_y+4), fill=(227, 108, 10, 255))

    return img


def main():
    img = make_icon()
    # 保存 png（预览用）
    img.save(os.path.join(os.path.dirname(__file__), 'icon_preview.png'))
    # 生成多尺寸 ico（Windows 需要 16/32/48/256）
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    # ico 需要 RGBA
    img.save(os.path.join(os.path.dirname(__file__), 'icon.ico'),
             format='ICO', sizes=sizes)
    print('图标已生成: icon.ico + icon_preview.png')


if __name__ == '__main__':
    main()
