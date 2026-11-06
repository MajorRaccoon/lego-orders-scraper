"""Draws a simple original app icon (a red 2x4 brick on a rounded tile) to icon.png.
Not any LEGO(R) logo. Needs Pillow. build_mac.sh turns this into icon.icns."""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=(250, 244, 232, 255))

# brick body
bx0, by0, bx1, by1 = 170, 430, 854, 780
d.rounded_rectangle((bx0 + 14, by0 + 22, bx1 + 14, by1 + 22), radius=36, fill=(120, 20, 20, 255))  # shadow
d.rounded_rectangle((bx0, by0, bx1, by1), radius=36, fill=(214, 36, 36, 255))
d.rounded_rectangle((bx0, by0, bx1, by0 + 70), radius=36, fill=(232, 70, 70, 255))
# studs: cylinders rising from the top face (back row first, then front row)
for cy_top, cy_base in ((330, 400), (395, 470)):
    for i in range(4):
        cx = bx0 + 85 + i * 171
        d.rectangle((cx - 62, cy_top, cx + 62, cy_base), fill=(176, 24, 24, 255))        # side
        d.ellipse((cx - 62, cy_base - 30, cx + 62, cy_base + 30), fill=(176, 24, 24, 255))
        d.ellipse((cx - 62, cy_top - 30, cx + 62, cy_top + 30), fill=(232, 64, 64, 255))  # top
d.rounded_rectangle((bx0, by0 + 40, bx1, by1), radius=36, fill=(214, 36, 36, 255))   # redraw body over stud bases
d.rounded_rectangle((bx0, by0 + 30, bx1, by0 + 82), radius=30, fill=(232, 70, 70, 255))
img.save("icon.png")
print("wrote icon.png")
