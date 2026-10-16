"""Build original app icons and wrap an official Classroom PNG in a Windows ICO.

Developer-only dependency: Pillow. Run from the repository root.
Pass the official Google archive path as the optional first argument.
"""
import io
import sys
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'src/classroom_publisher/assets'
ASSETS.mkdir(parents=True, exist_ok=True)
SCALE = 4
SIZES = [(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)]


def icon(style):
    im = Image.new('RGBA', (256 * SCALE, 256 * SCALE))
    d = ImageDraw.Draw(im)
    def rect(box, fill, radius=0):
        d.rounded_rectangle(tuple(int(x*SCALE) for x in box), radius=radius*SCALE, fill=fill)
    def line(points, fill, width):
        d.line([(x*SCALE, y*SCALE) for x, y in points], fill=fill, width=width*SCALE, joint='curve')
    def poly(points, fill):
        d.polygon([(x*SCALE, y*SCALE) for x,y in points], fill=fill)
    board = {'check': '#175849', 'book': '#253e60', 'pencil': '#195d69'}[style]
    rect((20, 32, 236, 211), '#213c3d', 18)
    rect((16, 24, 240, 203), '#d6ae78', 18)
    rect((27, 35, 229, 191), board, 10)
    rect((12, 195, 244, 210), '#b7834c', 5)
    rect((173, 185, 211, 191), '#f5ecd9', 2)
    rect((49, 210, 62, 232), '#8f603d', 3)
    rect((194, 210, 207, 232), '#8f603d', 3)
    if style == 'check':
        line([(67,111),(108,150),(184,77)], '#f8f5e9', 15)
    elif style == 'book':
        poly([(59,75),(111,80),(128,91),(128,163),(108,153),(59,149)], '#f8f5e9')
        poly([(197,75),(145,80),(128,91),(128,163),(148,153),(197,149)], '#f8f5e9')
        line([(128,91),(128,159)], board, 5)
        line([(74,100),(108,105)], '#a4b4be', 4)
        line([(74,119),(108,124)], '#a4b4be', 4)
        line([(148,105),(182,100)], '#a4b4be', 4)
        line([(148,124),(182,119)], '#a4b4be', 4)
    else:
        line([(61,158),(153,158)], '#82aaa9', 6)
        poly([(78,146),(88,116),(164,57),(188,85),(111,144)], '#f5d37a')
        poly([(78,146),(88,116),(111,144)], '#f5ecd9')
        poly([(78,146),(82,133),(91,145)], '#243d45')
        line([(100,121),(173,66)], '#f8efc9', 5)
    return im.resize((256,256), Image.Resampling.LANCZOS)


for name in ('check','book','pencil'):
    image = icon(name)
    image.save(ASSETS / f'chalkboard-{name}.png')
    image.save(ASSETS / f'chalkboard-{name}.ico', sizes=SIZES)

if len(sys.argv) > 1:
    with zipfile.ZipFile(sys.argv[1]) as z:
        raw = z.read('square_logo/96x96_yellow_stroke_icon@2x.png')
        official = Image.open(io.BytesIO(raw)).convert('RGBA')
    official.save(ASSETS / 'google-classroom.png')
    official.save(ASSETS / 'google-classroom.ico', sizes=[(n,n) for n in (16,20,24,32,40,48,64,96,128)])

preview = Image.new('RGB', (900, 280), '#f3f5f6')
d = ImageDraw.Draw(preview)
font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20) if Path('/System/Library/Fonts/Supplemental/Arial.ttf').exists() else ImageFont.load_default()
for i, (name, label) in enumerate([('check','1. Chalkboard check'),('book','2. Chalkboard book'),('pencil','3. Chalkboard pencil')]):
    image = icon(name).resize((180,180), Image.Resampling.LANCZOS)
    preview.paste(image, (i*300+60, 25), image)
    d.text((i*300+150, 240), label, font=font, anchor='mm', fill='#243440')
(ROOT/'docs').mkdir(exist_ok=True)
preview.save(ROOT/'docs/icon-options.png')
