"""Replace the old teaching-metric panel with a sourced A–E study summary.

Requires Pillow and imageio-ffmpeg. The original MP4 stays untouched.
"""

from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "sanhe-roadshow-opening.mp4"
PANEL = ASSETS / "roadshow-study-results.png"
OUTPUT = ASSETS / "sanhe-roadshow-opening-v2.mp4"
FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def draw_panel() -> None:
    im = Image.new("RGB", (3840, 2160), "#f6f1eb")
    d = ImageDraw.Draw(im)
    ink, muted, accent = "#241e1c", "#665e58", "#ae513e"
    d.text((230, 135), "三合医.", font=font(58, True), fill=ink)
    d.text((235, 310), "RESEARCH RESULTS  /  第五次大跑数", font=font(42, True), fill=accent)
    d.text((225, 410), "五套算法架构 · 两批队列", font=font(142, True), fill=ink)
    d.text((235, 605), "A/B/C 公开队列基准  ·  D/E 温州队列探索", font=font(59), fill=muted)

    cards = [
        ("21,459", "公开队列记录", "A/B/C · 936 个一年内事件"),
        ("167", "温州队列患者", "D/E · 49 个晚期 PSE 事件"),
        ("500 → 8,000", "达到预设 AUROC 容差门槛", "全队列 B/C · TabPFN 对 LightGBM"),
        ("0.9988", "最高内部测试 AUROC", "去重队列 C · TabPFN"),
    ]
    x_positions, y_positions = (225, 1955), (815, 1305)
    width, height = 1655, 420
    for i, (value, label, detail) in enumerate(cards):
        x, y = x_positions[i % 2], y_positions[i // 2]
        d.rounded_rectangle((x, y, x + width, y + height), radius=35, fill="#fffdfa", outline="#e5d9cf", width=3)
        d.rounded_rectangle((x + 58, y + 56, x + 69, y + 160), radius=5, fill=accent)
        d.text((x + 98, y + 46), value, font=font(102 if i == 2 else 125, True), fill=ink)
        d.text((x + 100, y + 205), label, font=font(51, True), fill=ink)
        d.text((x + 100, y + 296), detail, font=font(39), fill=muted)

    d.text((235, 1875), "来源：《卒中后癫痫五套算法架构_跑数结果汇编》", font=font(43), fill=ink)
    d.text((235, 1950), "不同任务的指标不可横比 · 公开队列为内部测试 · 尚无独立外部验证", font=font(41), fill=muted)
    im.save(PANEL, optimize=True)


def build_video() -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    graph = (
        "[1:v]format=rgba,"
        "fade=t=in:st=9.35:d=0.35:alpha=1,"
        "fade=t=out:st=15.95:d=0.30:alpha=1[panel];"
        "[0:v][panel]overlay=shortest=1:enable='between(t,9.35,16.25)'[v]"
    )
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(SOURCE),
         "-loop", "1", "-framerate", "30", "-i", str(PANEL),
         "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-t", "37.2", str(OUTPUT)],
        check=True,
    )


if __name__ == "__main__":
    draw_panel()
    build_video()
    print(OUTPUT)
