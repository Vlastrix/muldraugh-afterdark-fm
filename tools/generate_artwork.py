"""Generate the project's geometric radio artwork; no external images needed."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def font(size, bold=False):
    filename = "segoeuib.ttf" if bold else "segoeui.ttf"
    for path in (Path("C:/Windows/Fonts") / filename, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def generate():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    image = Image.new("RGB", (512, 512), "#10271f")
    draw = ImageDraw.Draw(image)
    mint, pale = "#9bf4bd", "#ecf0df"
    for y in range(0, 512, 8):
        draw.line((0, y, 512, y), fill="#142e25")
    draw.rectangle((20, 20, 491, 491), outline="#42684f", width=2)
    draw.text((36, 34), "RADIO FOR THE END OF THE WORLD", font=font(15), fill=mint)
    draw.text((34, 74), "MULDRAUGH", font=font(49, True), fill=pale)
    draw.text((34, 128), "AFTERDARK", font=font(55, True), fill=pale)
    draw.text((36, 193), "94.6 MHz  /  FM", font=font(31, True), fill=mint)
    draw.rounded_rectangle((36, 259, 476, 426), radius=18, outline=mint, width=4, fill="#0c1d17")
    for radius in (48, 36, 24):
        draw.ellipse((112-radius, 342-radius, 112+radius, 342+radius), outline="#638970", width=2)
    draw.line((112, 342, 139, 315), fill=pale, width=5)
    points = []
    for x in range(190, 451):
        strength = math.sin((x-190)/260*math.pi) ** 2
        points.append((x, 342 + 48*strength*math.sin((x-190)/13)))
    draw.line(points, fill=mint, width=3)
    draw.text((37, 455), "PROJECT ZOMBOID / SINGLEPLAYER", font=font(16, True), fill=mint)
    image.save(assets / "workshop-preview.png", optimize=True)
    icon = image.resize((256, 256), Image.Resampling.LANCZOS)
    icon.save(assets / "app.ico", sizes=[(16,16), (32,32), (48,48), (128,128), (256,256)])
    poster = ROOT / "mod" / "PearCarRadio" / "42" / "poster.png"
    image.save(poster, optimize=True)


if __name__ == "__main__":
    generate()
