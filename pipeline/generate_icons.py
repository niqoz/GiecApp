#!/usr/bin/env python3
"""Generate PWA icons for the climate app."""

from pathlib import Path

from PIL import Image, ImageDraw


TOP = (253, 176, 88)
BOT = (214, 73, 51)
INK = (255, 255, 255, 255)
SS = 4


def render(size: int) -> Image.Image:
    scale = size * SS
    img = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    px = img.load()
    for y in range(scale):
        t = y / (scale - 1)
        r = int(TOP[0] + (BOT[0] - TOP[0]) * t)
        g = int(TOP[1] + (BOT[1] - TOP[1]) * t)
        b = int(TOP[2] + (BOT[2] - TOP[2]) * t)
        for x in range(scale):
            px[x, y] = (r, g, b, 255)

    d = ImageDraw.Draw(img)
    cx = scale / 2
    tube_w = scale * 0.16
    tube_top = scale * 0.18
    tube_bottom = scale * 0.62
    bulb_r = scale * 0.19
    radius = tube_w / 2

    d.rounded_rectangle(
        [cx - tube_w / 2, tube_top, cx + tube_w / 2, tube_bottom],
        radius=radius,
        fill=INK,
    )
    d.ellipse([cx - bulb_r, tube_bottom - bulb_r * 0.35, cx + bulb_r, tube_bottom + bulb_r * 1.65], fill=INK)

    tick_x = cx + tube_w * 0.8
    for i in range(4):
        y = tube_top + i * (tube_bottom - tube_top) / 3
        d.rounded_rectangle([tick_x, y - scale * 0.012, tick_x + scale * 0.14, y + scale * 0.012], radius=scale * 0.01, fill=INK)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    out = Path("docs")
    out.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        path = out / f"icon-{size}.png"
        render(size).save(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
