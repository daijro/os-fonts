# Convert emoji fonts to silhouettes to shrink file size

from fontTools.ttLib import TTCollection
from PIL import Image
from tqdm import tqdm
import io
import sys

ttc = TTCollection(sys.argv[1])
converted = 0
errors = 0

glyphs = [
    (font, ppem, strike, glyph_name)
    for font in ttc.fonts
    if "sbix" in font
    for ppem, strike in font["sbix"].strikes.items()
    for glyph_name in strike.glyphs
]

for font, ppem, strike, glyph_name in tqdm(glyphs, desc="Processing", unit="glyph"):
    glyph = strike.glyphs[glyph_name]
    if glyph.graphicType == "png " and glyph.imageData and len(glyph.imageData) > 100:
        try:
            img = Image.open(io.BytesIO(glyph.imageData))
            w, h = img.size
            img = img.convert("RGBA")
            r, g, b, a = img.split()
            a = a.point(lambda x: 255 if x > 0 else 0)
            out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            out.paste(black, mask=a)
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            glyph.imageData = buf.getvalue()
            converted += 1
        except Exception as e:
            errors += 1

print(f"\nDone: {converted} converted, {errors} errors")
ttc.save(sys.argv[2])
