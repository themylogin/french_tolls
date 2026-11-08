# -*- coding=utf-8 -*-
"""Renders french_tolls/assets/gauges.png from the gauge images in this directory.

Run it with `make gauge-image`. The bot sends the result, and never renders it.
"""
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).parent
TILE = 400


def main():
    # In the order of the buttons 24, 16, 12.
    gauges = ["12.png", "8.jpg", "6.webp"]
    canvas = Image.new("RGB", (TILE * len(gauges), TILE), "black")
    for index, name in enumerate(gauges):
        source = ImageOps.contain(Image.open(HERE / name).convert("RGB"), (TILE, TILE), Image.LANCZOS)
        canvas.paste(source, (index * TILE + (TILE - source.width) // 2, (TILE - source.height) // 2))

    output = HERE.parent / "french_tolls" / "assets" / "gauges.png"
    output.parent.mkdir(exist_ok=True)
    canvas.save(output, optimize=True)


if __name__ == "__main__":
    main()
