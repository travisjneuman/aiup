#!/usr/bin/env python3
"""Render aiup's 32 second launch video from real aiup output and Terminal screenshots.

Usage:
  film.py WORK MODE [--fonts DIR] [--ffmpeg PATH]

WORK must hold assets/ with lockup.png, aiup-list-collapsed.png,
aiup-list-search.png and aiup-list-adopt.png. MODE is one of:
  stills  review sheets in WORK/stills (2x2 frames per JPEG)
  audio   WORK/mix.wav only
  full    WORK/mix.wav, WORK/brag.mp4 and WORK/brag.jpg

The run scene draws a Terminal window with the exact lines aiup printed for a
real update run on 2026-10-06 (RUN_* below). The list scenes use the real
screenshots. Every frame is a pure function of time. Frames go straight into ffmpeg's stdin,
so no frame folder is written. Frame 0 is the poster frame, so every player
shows it as the idle thumbnail. The score and sound effects are synthesized
here with numpy, in A minor at 120 BPM, timed from the same constants as the
picture.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import subprocess
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


W, H, FPS = 1920, 1080, 30
DURATION = 32.0
FRAMES = round(DURATION * FPS)
POSTER_T = 12.6
OUTRO_T = 28.0
SR = 48000
BEAT = 0.5
DROP_T = 4.5

NAVY = (11, 12, 35)
NAVY_HIGH = (22, 24, 62)
MIST = (232, 233, 255)
MUTED = (154, 160, 212)
CYAN = (77, 224, 255)
MINT = (78, 240, 196)
PURPLE = (192, 132, 252)
PINK = (255, 107, 169)
AMBER = (255, 189, 74)

SCENES = (
    ("hook", 0.0, 3.5),
    ("reveal", 3.5, 6.5),
    ("run", 6.5, 13.5),
    ("list", 13.5, 16.0),
    ("browse", 16.0, 20.0),
    ("search", 20.0, 24.0),
    ("ask", 24.0, OUTRO_T),
    ("outro", OUTRO_T, DURATION),
)
CUTS = (6.5, 13.5, 16.0, 20.0, 24.0, OUTRO_T)

HOOK_LINES = (
    ("brew upgrade", CYAN),
    ("npm install -g @openai/codex@latest", MINT),
    ("uv tool upgrade gptme", PURPLE),
    ("claude update", PINK),
    ("opencode upgrade", AMBER),
)
HOOK_START, HOOK_STEP, HOOK_CPS = 0.45, 0.42, 38.0
REVEAL_WORD, REVEAL_TYPE_START, REVEAL_CPS = "aiup", 3.62, 11.0
LIST_WORD, LIST_TYPE_START, LIST_CPS = "aiup list", 13.65, 12.0

# The run scene: aiup's real output for my update run of 2026-10-06 (122 tools,
# 149 seconds), at 100 columns. RUN_TOOLS are the first 25 tools in run order
# with the elapsed seconds summed from each tool's logged duration; the progress
# line then cuts to the report. Only the run log path is shortened to ~.
RUN_TOTAL = 122
RUN_TOOLS = (
    ("fzf", 0), ("brew", 6), ("npm", 7), ("uv", 8), ("gh", 9), ("wrangler", 9), ("deno", 11),
    ("pnpm", 11), ("jq", 12), ("ripgrep", 12), ("fd", 12), ("claude", 12), ("codex", 16),
    ("antigravity", 23), ("grok", 24), ("pi", 26), ("pi-acp", 33), ("chatgpt", 35),
    ("claude-app", 72), ("grokbot", 74), ("cmux", 95), ("remotion", 122), ("macwhisper", 124),
    ("ffmpeg", 124), ("yt-dlp", 124),
)
RUN_UPDATED = (
    ("brew", "7.0.8-5-gef90f72", "7.0.8-32-g8304895", 1, False),
    ("claude", "2.1.289", "2.1.291", 4, False),
    ("codex", "0.160.0", "0.160.1", 7, False),
    ("pi", "1.0.3", "1.0.4", 7, True),
    ("chatgpt", "26.930.51102", "26.930.61225", 37, False),
    ("grokbot", "0.66.0", "0.68.1", 21, False),
    ("cmux", "0.64.25", "0.65.0", 27, False),
)
RUN_NOTE = (
    "npm held back install scripts for esbuild, @google/genai, protobufjs (its default protection);",
    "if pi misbehaves, aiup logs pi shows how to allow them.",
)
RUN_TYPE_START, RUN_CPS = 6.85, 11.0
RUN_HEAD_T, RUN_TICK_START, RUN_TICK_STEP = 7.35, 7.6, 0.075
RUN_REPORT_T, RUN_LINE_STEP = 9.6, 0.03
# Highlight boxes: (time, first row, last row, first column, last column, color).
RUN_MARKS = ((10.5, 7, 7, 2, 50, (78, 240, 196)), (11.3, 11, 19, 2, 99, (77, 224, 255)))
TERM_COLS, TERM_ROWS, TERM_FONT, TERM_LINE = 100, 26, 23, 29
TERM_BG, TERM_BAR = (19, 20, 19), (36, 36, 40)
TERM_FG = (40, 254, 20)  # the Homebrew profile's text color
XTERM = {
    39: (0, 175, 255), 51: (0, 255, 255), 60: (95, 95, 135), 81: (95, 215, 255), 141: (175, 135, 255),
    171: (215, 95, 255), 184: (215, 215, 0), 220: (255, 215, 0), 245: (138, 138, 138),
}
TERM_GREEN = (57, 255, 20)
# Category colors from catalog_ansi: infra, coding-agents, chat, automation, terminals.
RUN_SHADES = {"brew": 39, "claude": 171, "codex": 171, "pi": 171, "chatgpt": 51, "grokbot": 184, "cmux": 81}

# Feature scenes: screenshot, headline lines, subline, push-in focus (screenshot px),
# start and end scale, and highlight boxes (time, screenshot rect, color).
FEATURES = {
    "browse": {
        "shot": "aiup-list-collapsed.png",
        "head": ("260+ tools.", "20+ categories."),
        "sub": "See what you have and what needs an update.",
        "focus": (300, 120), "scale": (1.04, 1.10),
        "marks": ((17.0, (38, 112, 988, 137), MINT),),
    },
    "search": {
        "shot": "aiup-list-search.png",
        "head": ("Type to find", "any tool."),
        "sub": "Each one has its own keys to update or remove it.",
        "focus": (420, 300), "scale": (1.04, 1.10),
        "marks": ((20.6, (22, 54, 248, 81), CYAN), (21.8, (40, 550, 838, 574), PURPLE)),
    },
    "ask": {
        "shot": "aiup-list-adopt.png",
        "head": ("It asks first.",),
        "sub": "Switching an app you already have waits for your yes.",
        "focus": (330, 124), "scale": (1.04, 1.14), "crop": 215,
        "marks": ((25.0, (4, 113, 648, 137), PINK),),
    },
}
CAPTION_X, CAPTION_WIDTH = 120, 590
WINDOW_X = 760


# ---------------------------------------------------------------- easing


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def prog(t: float, start: float, end: float) -> float:
    return clamp((t - start) / (end - start))


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def ease_in_out(p: float) -> float:
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def appear(t: float, start: float, length: float = 0.4) -> float:
    return ease_out(prog(t, start, start + length))


def leave(t: float, end: float, length: float = 0.3) -> float:
    return 1 - ease_in_out(prog(t, end - length, end))


# ---------------------------------------------------------------- drawing kit


class Kit:
    def __init__(self, assets: pathlib.Path, fonts: pathlib.Path) -> None:
        self.paths = {
            "bold": fonts / "segoeuib.ttf",
            "regular": fonts / "segoeui.ttf",
            "mono": fonts / "CascadiaMono.ttf",
        }
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._text: dict[tuple[str, str, int, tuple[int, int, int]], Image.Image] = {}
        lockup = Image.open(assets / "lockup.png").convert("RGBA")
        self.lockup = lockup.crop(lockup.getchannel("A").getbbox())
        self.background = make_background()
        self.glow = make_glow()
        self.windows = {
            name: Window(Image.open(assets / spec["shot"]), spec["marks"], spec.get("crop")) for name, spec in FEATURES.items()
        }
        self.terminal = Terminal(self)

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        key = (kind, size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(str(self.paths[kind]), size)
        return self._fonts[key]

    def text(self, value: str, kind: str, size: int, color: tuple[int, int, int]) -> Image.Image:
        key = (value, kind, size, color)
        if key not in self._text:
            font = self.font(kind, size)
            ascent, descent = font.getmetrics()
            width = max(1, math.ceil(font.getlength(value)) + 4)
            image = Image.new("RGBA", (width, ascent + descent), (0, 0, 0, 0))
            ImageDraw.Draw(image).text((0, 0), value, font=font, fill=color + (255,))
            self._text[key] = image
        return self._text[key]

    def wrap(self, value: str, kind: str, size: int, width: int) -> list[str]:
        font = self.font(kind, size)
        lines: list[str] = []
        for word in value.split():
            if lines and font.getlength(f"{lines[-1]} {word}") <= width:
                lines[-1] = f"{lines[-1]} {word}"
            else:
                lines.append(word)
        return lines


class Window:
    """A real screenshot with its drop shadow and pre-drawn highlight boxes."""

    def __init__(self, shot: Image.Image, marks: tuple, crop: int | None = None) -> None:
        self.shot = shot.convert("RGBA")
        if crop:
            # Keep only the top of the window, with rounded bottom corners like the real frame.
            self.shot = self.shot.crop((0, 0, self.shot.width, crop))
            corners = Image.new("L", self.shot.size, 0)
            ImageDraw.Draw(corners).rounded_rectangle((0, 0, self.shot.width - 1, crop - 1), radius=12, fill=255)
            self.shot.putalpha(ImageChops.darker(self.shot.getchannel("A"), corners))
        blur, offset = 22, 18
        self.pad = blur * 3
        size = (self.shot.width + self.pad * 2, self.shot.height + self.pad * 2)
        mask = Image.new("L", size, 0)
        mask.paste(self.shot.getchannel("A").point(lambda v: v * 170 // 255), (self.pad, self.pad + offset))
        self.shadow = Image.new("RGBA", size, (0, 0, 0, 0))
        self.shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
        self.marks = [(when, highlight(self.shot.size, rect, color)) for when, rect, color in marks]

    def draw(self, t: float) -> Image.Image:
        return self.shot.copy()

    def render(self, t: float) -> Image.Image:
        shot = self.draw(t)
        for when, overlay in self.marks:
            strength = appear(t, when, 0.35)
            if strength > 0:
                shot.alpha_composite(fade(overlay, strength))
        framed = self.shadow.copy()
        framed.alpha_composite(shot, (self.pad, self.pad))
        return framed


class Terminal(Window):
    """A Terminal window, styled like the screenshots, that prints the real run output over time."""

    def __init__(self, kit: Kit) -> None:
        self.kit = kit
        self.cell = kit.font("mono", TERM_FONT).getlength("M")
        self.left, self.top, bar = 16, 44, 34
        width = round(TERM_COLS * self.cell) + self.left * 2
        height = self.top + TERM_ROWS * TERM_LINE + 10
        chrome = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(chrome)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=12, fill=TERM_BG + (255,))
        draw.rounded_rectangle((0, 0, width - 1, bar + 12), radius=12, fill=TERM_BAR + (255,))
        draw.rectangle((0, bar, width - 1, bar + 12), fill=TERM_BG + (255,))
        for index, color in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            x = 20 + index * 22
            draw.ellipse((x - 7, bar / 2 - 7, x + 7, bar / 2 + 7), fill=color + (255,))
        title = kit.text("aiup", "regular", 17, (170, 170, 176))
        chrome.alpha_composite(title, (round((width - title.width) / 2), round(bar / 2 - title.height / 2)))
        marks = tuple((when, self.cells(r0, r1, c0, c1), color) for when, r0, r1, c0, c1, color in RUN_MARKS)
        super().__init__(chrome, marks)
        self.report = run_report()

    def cells(self, r0: int, r1: int, c0: int, c1: int) -> tuple[int, int, int, int]:
        return (
            round(self.left + c0 * self.cell) - 8, self.top + r0 * TERM_LINE - 3,
            round(self.left + (c1 + 1) * self.cell) + 8, self.top + (r1 + 1) * TERM_LINE + 1,
        )

    def line(self, image: Image.Image, row: int, segments: list[tuple[str, tuple[int, int, int]]]) -> None:
        column = 0
        for value, color in segments:
            if value.strip():
                image.alpha_composite(self.kit.text(value, "mono", TERM_FONT, color), (round(self.left + column * self.cell), self.top + row * TERM_LINE))
            column += len(value)

    def draw(self, t: float) -> Image.Image:
        image = self.shot.copy()
        typed = int(clamp((t - RUN_TYPE_START) * RUN_CPS, 0, 4))
        self.line(image, 0, [("$ ", TERM_FG), ("aiup"[:typed], TERM_FG)])
        if t < RUN_HEAD_T:
            if typed < 4 or int(t * 4) % 2 == 0:
                self.block(image, 0, 2 + typed)
            return image
        self.line(image, 2, [("  aiup", XTERM[141]), (" \u00b7 tool operations", XTERM[81])])
        self.line(image, 4, [("  Reading installed versions\u2026", TERM_FG)])
        if t < RUN_REPORT_T:
            index = min(len(RUN_TOOLS) - 1, int(max(0.0, t - RUN_TICK_START) / RUN_TICK_STEP))
            if t >= RUN_TICK_START:
                tool, elapsed = RUN_TOOLS[index]
                text = f"  [{index + 1}/{RUN_TOTAL}] {tool} \u00b7 {elapsed}s elapsed"
                self.line(image, 5, [(text, TERM_FG)])
                self.block(image, 5, len(text))
            return image
        shown = int((t - RUN_REPORT_T) / RUN_LINE_STEP) + 1
        for offset, segments in enumerate(self.report[:shown]):
            self.line(image, 6 + offset, segments)
        if shown > len(self.report):
            row = 6 + len(self.report)
            self.line(image, row, [("$ ", TERM_FG)])
            if int(t * 4) % 2 == 0:
                self.block(image, row, 2)
        return image

    def block(self, image: Image.Image, row: int, column: int) -> None:
        x = round(self.left + column * self.cell)
        y = self.top + row * TERM_LINE + 3
        ImageDraw.Draw(image).rectangle((x, y, x + round(self.cell) - 1, y + TERM_LINE - 5), fill=TERM_FG + (230,))


def run_report() -> list[list[tuple[str, tuple[int, int, int]]]]:
    """The report lines print_update_report wrote for the 2026-10-06 run, with their colors."""
    width = 32
    rule = [("  " + "\u2500" * (TERM_COLS - 4), XTERM[60])]
    lines = [
        [("  aiup \u00b7 results", XTERM[141])],
        [("  7 updated \u00b7 1 self-updated \u00b7 114 unchanged \u00b7 149s", XTERM[245])],
        [("  1 tool needs a look (marked !)", XTERM[220])],
        rule,
        [("  " + "TOOL".ljust(width) + "RESULT".ljust(13) + "VERSION", XTERM[81])],
    ]
    for tool, before, after, took, warning in RUN_UPDATED:
        status = "updated !" if warning else "updated"
        lines.append([
            ("  ", TERM_FG), (tool.ljust(width), XTERM[RUN_SHADES[tool]]),
            (status.ljust(13), TERM_GREEN), (f"{before} \u2192 {after} \u00b7 {took}s", TERM_FG),
        ])
        if warning:
            lines += [[("      " + part, XTERM[220])] for part in RUN_NOTE]
    lines += [
        rule,
        [("  115 current tools hidden \u00b7 --show-unchanged lists them", XTERM[245])],
        [("  Next: aiup attention", XTERM[81])],
        [("  Run log: ~/.local/share/aiup/logs/update-20261006-082734.jKqdmy", XTERM[245])],
    ]
    return lines


def highlight(size: tuple[int, int], rect: tuple[int, int, int, int], color: tuple[int, int, int]) -> Image.Image:
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(rect, radius=6, outline=color + (200,), width=8)
    glow = glow.filter(ImageFilter.GaussianBlur(7))
    ring = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(rect, radius=6, fill=color + (26,), outline=color + (255,), width=3)
    glow.alpha_composite(ring)
    return glow


def fade(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image
    faded = image.copy()
    faded.putalpha(image.getchannel("A").point(lambda v: round(v * alpha)))
    return faded


def put(canvas: Image.Image, image: Image.Image, x: float, y: float, alpha: float = 1.0, scale: float = 1.0) -> None:
    if alpha <= 0.003:
        return
    if abs(scale - 1.0) > 1e-4:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.BICUBIC)
    image = fade(image, alpha)
    x, y = round(x), round(y)
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(image.width, W - x), min(image.height, H - y)
    if right <= left or bottom <= top:
        return
    if (left, top, right, bottom) != (0, 0, image.width, image.height):
        image = image.crop((left, top, right, bottom))
    canvas.alpha_composite(image, (x + left, y + top))


def make_background() -> Image.Image:
    bw, bh = W + 320, H + 240
    yy = np.linspace(0, 1, bh)[:, None]
    xx = np.linspace(0, 1, bw)[None, :]
    navy = np.array(NAVY, float)
    base = navy + (np.array(NAVY_HIGH, float) - navy) * (0.6 * yy)[..., None] + 0 * xx[..., None]

    def blob(cx: float, cy: float, radius: float, color: tuple[int, int, int], strength: float) -> np.ndarray:
        distance = ((xx - cx) * bw / bh) ** 2 + (yy - cy) ** 2
        return np.exp(-distance / radius ** 2)[..., None] * np.array(color, float) * strength

    base = base + blob(0.80, 0.28, 0.42, CYAN, 0.13) + blob(0.18, 0.82, 0.45, PURPLE, 0.12) + blob(0.55, 1.0, 0.30, PINK, 0.04)
    base += np.random.default_rng(7).uniform(-0.7, 0.7, base.shape)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def make_glow() -> Image.Image:
    glow = Image.new("RGBA", (1400, 700), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((250, 180, 1150, 520), fill=CYAN + (90,))
    return glow.filter(ImageFilter.GaussianBlur(110))


# ---------------------------------------------------------------- scenes


def text_center(kit: Kit, canvas: Image.Image, value: str, kind: str, size: int, color, y: float, alpha: float, rise: float = 0) -> None:
    image = kit.text(value, kind, size, color)
    put(canvas, image, (W - image.width) / 2, y + rise, alpha)


def scene_hook(kit: Kit, canvas: Image.Image, t: float) -> None:
    out = leave(t, 3.5, 0.32)
    p = appear(t, 0.15, 0.45)
    text_center(kit, canvas, "Every AI tool updates a different way.", "bold", 74, MIST, 170, p * out, (1 - p) * 26)
    size = 44
    cell = kit.font("mono", size).getlength("M")
    longest = max(len(command) for command, _ in HOOK_LINES) + 2
    x0 = (W - longest * cell) / 2
    for index, (command, color) in enumerate(HOOK_LINES):
        start = HOOK_START + index * HOOK_STEP
        if t < start:
            break
        typed = min(len(command), int((t - start) * HOOK_CPS))
        y = 360 + index * 82
        alpha = appear(t, start, 0.12) * out
        put(canvas, kit.text("$", "mono", size, MUTED), x0, y, alpha)
        if typed:
            put(canvas, kit.text(command[:typed], "mono", size, color), x0 + 2 * cell, y, alpha)
        if typed < len(command):
            cursor(canvas, x0 + (2 + typed) * cell, y, cell, size, alpha)
    last_done = HOOK_START + (len(HOOK_LINES) - 1) * HOOK_STEP + len(HOOK_LINES[-1][0]) / HOOK_CPS
    if t >= last_done:
        y = 360 + len(HOOK_LINES) * 82
        put(canvas, kit.text("$", "mono", size, MUTED), x0, y, out)
        if int((t - last_done) * 4) % 2 == 0:
            cursor(canvas, x0 + 2 * cell, y, cell, size, out)


def cursor(canvas: Image.Image, x: float, y: float, cell: float, size: int, alpha: float) -> None:
    block = Image.new("RGBA", (max(2, round(cell * 0.6)), round(size * 1.12)), MIST + (220,))
    put(canvas, block, x, y + size * 0.12, alpha)


def scene_reveal(kit: Kit, canvas: Image.Image, t: float) -> None:
    out = leave(t, 6.5, 0.32)
    size = 96
    gone = ease_in_out(prog(t, 4.18, 4.45))
    if gone < 1:
        typed = int(clamp((t - REVEAL_TYPE_START) * REVEAL_CPS, 0, len(REVEAL_WORD)))
        cell = kit.font("mono", size).getlength("M")
        x0 = (W - (2 + len(REVEAL_WORD)) * cell) / 2
        y = 450 - gone * 40
        alpha = appear(t, 3.5, 0.2) * (1 - gone)
        put(canvas, kit.text("$", "mono", size, MUTED), x0, y, alpha)
        if typed:
            put(canvas, kit.text(REVEAL_WORD[:typed], "mono", size, MIST), x0 + 2 * cell, y, alpha)
        if typed < len(REVEAL_WORD) or int(t * 4) % 2 == 0:
            cursor(canvas, x0 + (2 + typed) * cell, y, cell, size, alpha)
    p = appear(t, DROP_T, 0.55)
    if p > 0:
        pulse = 0.55 + 0.9 * math.exp(-max(0.0, t - DROP_T) / 0.45)
        put(canvas, kit.glow, (W - kit.glow.width) / 2, 470 - kit.glow.height / 2, clamp(p * pulse * 0.6) * out)
        width = 900
        scale = (width / kit.lockup.width) * (0.92 + 0.08 * p)
        put(canvas, kit.lockup, W / 2 - kit.lockup.width * scale / 2, 450 - kit.lockup.height * scale / 2, p * out, scale)
    q = appear(t, DROP_T + 0.3, 0.45)
    text_center(kit, canvas, "One command for all of them.", "bold", 68, MIST, 730, q * out, (1 - q) * 24)


def scene_run(kit: Kit, canvas: Image.Image, t: float, start: float, end: float) -> None:
    out = leave(t, end, 0.3)
    window = kit.terminal
    width = window.shot.width
    x0, y0 = (W - width) / 2, 182
    scale = 1.0 + 0.03 * ease_in_out(prog(t, start, end))
    p = appear(t, start + 0.05, 0.5)
    left = x0 + width * (1 - scale) / 2 - window.pad * scale
    top = y0 - window.pad * scale + (1 - p) * 70
    put(canvas, window.render(t), left, top, p * out, scale)

    a = appear(t, start + 0.15, 0.45)
    b = appear(t, start + 0.45, 0.45)
    head = kit.text("Run aiup.", "bold", 64, MIST)
    sub = kit.text("It updates your tools and Homebrew packages.", "regular", 40, MUTED)
    ascent_head, ascent_sub = kit.font("bold", 64).getmetrics()[0], kit.font("regular", 40).getmetrics()[0]
    put(canvas, head, x0, 64 + (1 - a) * 24, a * out)
    put(canvas, sub, x0 + head.width + 26, 64 + ascent_head - ascent_sub + (1 - b) * 20, b * out)


def scene_list(kit: Kit, canvas: Image.Image, t: float, start: float, end: float) -> None:
    out = leave(t, end, 0.3)
    size = 96
    typed = int(clamp((t - LIST_TYPE_START) * LIST_CPS, 0, len(LIST_WORD)))
    cell = kit.font("mono", size).getlength("M")
    x0 = (W - (2 + len(LIST_WORD)) * cell) / 2
    alpha = appear(t, start, 0.25) * out
    put(canvas, kit.text("$", "mono", size, MUTED), x0, 360, alpha)
    if typed:
        put(canvas, kit.text(LIST_WORD[:typed], "mono", size, MIST), x0 + 2 * cell, 360, alpha)
    if typed < len(LIST_WORD) or int(t * 4) % 2 == 0:
        cursor(canvas, x0 + (2 + typed) * cell, 360, cell, size, alpha)
    done = LIST_TYPE_START + len(LIST_WORD) / LIST_CPS
    q = appear(t, done + 0.1, 0.45)
    text_center(kit, canvas, "Opens the full catalog in one list.", "bold", 68, MIST, 600, q * out, (1 - q) * 24)


def scene_feature(kit: Kit, canvas: Image.Image, t: float, name: str, start: float, end: float) -> None:
    spec = FEATURES[name]
    out = leave(t, end, 0.3)
    window = kit.windows[name]
    s0, s1 = spec["scale"]
    scale = s0 + (s1 - s0) * ease_in_out(prog(t, start, end))
    fx, fy = spec["focus"]
    shot_h = window.shot.height
    x_base, y_base = WINDOW_X, (H - shot_h * s0) / 2
    anchor_x, anchor_y = x_base + fx * s0, y_base + fy * s0
    p = appear(t, start + 0.05, 0.5)
    left = anchor_x - fx * scale - window.pad * scale
    top = anchor_y - fy * scale - window.pad * scale + (1 - p) * 70
    put(canvas, window.render(t), left, top, p * out, scale)

    head = spec["head"]
    widest = max(kit.font("bold", 84).getlength(line) for line in head)
    head_size, sub_size = min(84, int(84 * CAPTION_WIDTH / widest)), 38
    sub = kit.wrap(spec["sub"], "regular", sub_size, CAPTION_WIDTH)
    head_step, sub_step = 100, 52
    block = len(head) * head_step + 28 + len(sub) * sub_step
    y = (H - block) / 2
    a = appear(t, start + 0.15, 0.45)
    for line in head:
        put(canvas, kit.text(line, "bold", head_size, MIST), CAPTION_X, y + (1 - a) * 26, a * out)
        y += head_step
    y += 28
    b = appear(t, start + 0.45, 0.45)
    for line in sub:
        put(canvas, kit.text(line, "regular", sub_size, MUTED), CAPTION_X, y + (1 - b) * 20, b * out)
        y += sub_step


def scene_outro(kit: Kit, canvas: Image.Image, t: float) -> None:
    out = leave(t, DURATION, 0.5)
    p = appear(t, OUTRO_T + 0.1, 0.55)
    put(canvas, kit.glow, (W - kit.glow.width) / 2, 330 - kit.glow.height / 2, p * 0.35 * out)
    scale = (760 / kit.lockup.width) * (0.94 + 0.06 * p)
    put(canvas, kit.lockup, W / 2 - kit.lockup.width * scale / 2, 330 - kit.lockup.height * scale / 2, p * out, scale)
    lines = (
        ("Free and open source, for macOS.", "bold", 58, MIST, 560, OUTRO_T + 0.45),
        ("aiup.neuman.dev", "bold", 64, CYAN, 670, OUTRO_T + 0.75),
        ("github.com/travisjneuman/aiup", "regular", 38, MUTED, 770, OUTRO_T + 0.95),
    )
    for value, kind, size, color, y, when in lines:
        q = appear(t, when, 0.45)
        text_center(kit, canvas, value, kind, size, color, y, q * out, (1 - q) * 22)


def render(kit: Kit, t: float) -> Image.Image:
    ox = 160 + 120 * math.sin(2 * math.pi * t / 14)
    oy = 120 + 90 * math.sin(2 * math.pi * t / 11 + 1)
    canvas = kit.background.crop((round(ox), round(oy), round(ox) + W, round(oy) + H)).convert("RGBA")
    for name, start, end in SCENES:
        if start <= t < end or name == "outro" and t >= start:
            if name == "hook":
                scene_hook(kit, canvas, t)
            elif name == "reveal":
                scene_reveal(kit, canvas, t)
            elif name == "run":
                scene_run(kit, canvas, t, start, end)
            elif name == "list":
                scene_list(kit, canvas, t, start, end)
            elif name == "outro":
                scene_outro(kit, canvas, t)
            else:
                scene_feature(kit, canvas, t, name, start, end)
            break
    return canvas.convert("RGB")


# ---------------------------------------------------------------- audio


def midi(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


CHORDS = ((45, (57, 60, 64)), (41, (53, 57, 60)), (48, (55, 60, 64)), (43, (55, 59, 62)))  # Am F C G


def chord_at(t: float) -> tuple[int, tuple[int, int, int]]:
    return CHORDS[0] if t >= OUTRO_T else CHORDS[int(t // 2) % 4]


class Bus:
    def __init__(self, length: int) -> None:
        self.left = np.zeros(length)
        self.right = np.zeros(length)

    def add(self, at: float, mono: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
        start = int(round(at * SR))
        if start >= len(self.left):
            return
        mono = mono[: len(self.left) - start] * gain
        angle = (pan + 1) * math.pi / 4
        self.left[start : start + len(mono)] += mono * math.cos(angle)
        self.right[start : start + len(mono)] += mono * math.sin(angle)


def seconds(length: float) -> np.ndarray:
    return np.arange(int(length * SR)) / SR


def band(signal: np.ndarray, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / SR)
    shape = 1 / (1 + (low / np.maximum(freqs, 1)) ** 4) / (1 + (freqs / high) ** 4)
    return np.fft.irfft(spectrum * shape, len(signal))


def pad_tone(notes: tuple[int, ...], length: float) -> np.ndarray:
    tt = seconds(length)
    tone = np.zeros_like(tt)
    for note in notes:
        for detune in (-0.0025, 0.0025):
            freq = midi(note) * (1 + detune)
            for harmonic in range(1, 6):
                tone += np.sin(2 * math.pi * freq * harmonic * tt + harmonic) / harmonic ** 1.4
    attack = np.clip(tt / 0.45, 0, 1)
    release = np.clip((length - tt) / 0.8, 0, 1)
    return tone * np.sin(attack * math.pi / 2) ** 2 * np.sin(release * math.pi / 2) ** 2 / (len(notes) * 4)


def pluck(note: float, length: float = 0.6) -> np.ndarray:
    tt = seconds(length)
    freq = midi(note)
    tone = (np.sin(2 * math.pi * freq * tt) * np.exp(-tt / 0.30)
            + 0.4 * np.sin(4 * math.pi * freq * tt) * np.exp(-tt / 0.14)
            + 0.15 * np.sin(6 * math.pi * freq * tt) * np.exp(-tt / 0.07))
    return tone * np.clip(tt / 0.003, 0, 1)


def bell(note: float, length: float = 2.0) -> np.ndarray:
    tt = seconds(length)
    freq = midi(note)
    tone = np.zeros_like(tt)
    for ratio, amp, decay in ((1.0, 1.0, 1.2), (2.0, 0.45, 0.6), (2.76, 0.3, 0.4), (5.4, 0.12, 0.18)):
        tone += amp * np.sin(2 * math.pi * freq * ratio * tt) * np.exp(-tt / decay)
    return tone * np.clip(tt / 0.004, 0, 1) / 1.9


def kick(strength: float = 1.0) -> np.ndarray:
    tt = seconds(0.4)
    freq = 47 + 65 * np.exp(-tt / 0.03)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-tt / (0.16 + 0.2 * (strength - 1))) * strength


def noise_hit(rng: np.random.Generator, length: float, low: float, high: float, decay: float) -> np.ndarray:
    tt = seconds(length)
    hit = band(rng.standard_normal(len(tt)), low, high) * np.exp(-tt / decay)
    return hit / (np.abs(hit).max() + 1e-9)


def sweep(rng: np.random.Generator, length: float, peak_at: float) -> np.ndarray:
    """A soft whoosh: noise that brightens toward peak_at, then falls away fast."""
    tt = seconds(length)
    low = band(rng.standard_normal(len(tt)), 200, 1200)
    high = band(rng.standard_normal(len(tt)), 1500, 7000)
    mix = np.clip(tt / peak_at, 0, 1)
    rise = np.clip(tt / peak_at, 0, 1) ** 2
    fall = np.exp(-np.clip(tt - peak_at, 0, None) / 0.09)
    body = (low * (1 - mix) + high * mix * 0.7) * rise * fall
    return body / (np.abs(body).max() + 1e-9)


def typing_times() -> list[float]:
    times: list[float] = []
    for index, (command, _) in enumerate(HOOK_LINES):
        start = HOOK_START + index * HOOK_STEP
        times += [start + (i + 1) / HOOK_CPS for i in range(len(command))]
    times += [REVEAL_TYPE_START + (i + 1) / REVEAL_CPS for i in range(len(REVEAL_WORD))]
    times += [RUN_TYPE_START + (i + 1) / RUN_CPS for i in range(len("aiup"))]
    times += [LIST_TYPE_START + (i + 1) / LIST_CPS for i in range(len(LIST_WORD))]
    return times


def build_audio(path: pathlib.Path) -> None:
    rng = np.random.default_rng(20261014)
    length = int((DURATION + 0.1) * SR)
    music, sfx, send = Bus(length), Bus(length), Bus(length)

    # Pad under everything, quieter before the drop.
    for bar in range(int(OUTRO_T // 2) + 1):
        start = bar * 2.0
        span = DURATION - start + 0.2 if start >= OUTRO_T else 2.8
        _, notes = chord_at(start)
        level = 0.9 if start + 1 < DROP_T else 1.0
        tone = pad_tone(notes, span)
        music.add(start, tone, 0.22 * level)
        send.add(start, tone, 0.10 * level)

    # Bass on every beat after the drop, then one long root to close.
    for beat in np.arange(DROP_T, OUTRO_T + 2.0, BEAT):
        root, _ = chord_at(beat)
        tt = seconds(0.45)
        note = np.sin(2 * math.pi * midi(root) * tt) + 0.3 * np.sin(4 * math.pi * midi(root) * tt)
        music.add(beat, note * np.exp(-tt / 0.22) * np.clip(tt / 0.005, 0, 1), 0.16)
    tt = seconds(1.6)
    music.add(OUTRO_T + 2.5, np.sin(2 * math.pi * midi(45) * tt) * np.exp(-tt / 0.7) * np.clip(tt / 0.01, 0, 1), 0.2)

    # A soft root pulse on each beat of the hook, so the typing has a groove under it.
    for beat in np.arange(BEAT, DROP_T, BEAT):
        root, _ = chord_at(beat)
        tone = pluck(root + 12, 0.4)
        music.add(beat, tone, 0.07)
        send.add(beat, tone, 0.04)

    # Eighth-note arpeggio from the drop, panned left and right.
    for step, at in enumerate(np.arange(DROP_T, OUTRO_T + 2.5, BEAT / 2)):
        _, (a, b, c) = chord_at(at)
        pattern = (a + 12, b + 12, c + 12, b + 24, c + 12, b + 12, a + 24, c + 12)
        velocity = 1.0 if step % 2 == 0 else 0.7
        tone = pluck(pattern[step % len(pattern)])
        pan = -0.3 if step % 2 == 0 else 0.3
        music.add(at, tone, 0.075 * velocity, pan)
        send.add(at, tone, 0.06 * velocity, -pan)

    # Drums: kick on the beat, soft clap on 2 and 4, quiet off-beat hats.
    for beat in np.arange(DROP_T, OUTRO_T + 2.0, BEAT):
        music.add(beat, kick(1.6 if abs(beat - DROP_T) < 1e-6 else 1.0), 0.32)
    for beat in np.arange(6.5, OUTRO_T, BEAT):
        if round(beat / BEAT) % 2 == 1:
            clap = noise_hit(rng, 0.25, 900, 3500, 0.07)
            music.add(beat, clap, 0.045)
            send.add(beat, clap, 0.05)
    for beat in np.arange(6.5 + BEAT / 2, OUTRO_T + 2.0, BEAT):
        music.add(beat, noise_hit(rng, 0.08, 6000, 15000, 0.018), 0.022, 0.2)

    # Typing clicks, kept under the music.
    for at in typing_times():
        tt = seconds(0.03)
        click = noise_hit(rng, 0.03, 2000, 8000, 0.0018) + 0.3 * np.sin(2 * math.pi * 1900 * tt) * np.exp(-tt / 0.002)
        sfx.add(at, click, 0.05 * rng.uniform(0.6, 1.0), rng.uniform(-0.15, 0.15))

    # Riser into the drop, impact and chime on it, whooshes on each cut.
    riser = sweep(rng, 0.95, 0.8)
    sfx.add(DROP_T - 0.8, riser, 0.10)
    send.add(DROP_T - 0.8, riser, 0.05)
    tt = seconds(1.2)
    sfx.add(DROP_T, np.sin(2 * math.pi * 44 * tt) * np.exp(-tt / 0.5) * np.clip(tt / 0.004, 0, 1), 0.18)
    for note in (81, 88):
        chime = bell(note)
        sfx.add(DROP_T, chime, 0.05)
        send.add(DROP_T, chime, 0.06)
    for cut in CUTS:
        whoosh = sweep(rng, 0.65, 0.42)
        sfx.add(cut - 0.42, whoosh, 0.06)
        send.add(cut - 0.42, whoosh, 0.04)

    # A soft tick for each tool on the progress line, then a two-note chime when the report lands.
    for index in range(len(RUN_TOOLS)):
        tt = seconds(0.04)
        tick = np.sin(2 * math.pi * 2600 * tt) * np.exp(-tt / 0.006)
        sfx.add(RUN_TICK_START + index * RUN_TICK_STEP, tick, 0.018, rng.uniform(-0.2, 0.2))
    for offset, note in enumerate((76, 81)):
        chime = bell(note, 1.6)
        sfx.add(RUN_REPORT_T + offset * 0.12, chime, 0.04)
        send.add(RUN_REPORT_T + offset * 0.12, chime, 0.05)

    # A soft bell on each highlight box, on a tone of the chord under it.
    pings = [when for spec in FEATURES.values() for when, _, _ in spec["marks"]]
    pings += [when for when, *_ in RUN_MARKS] + [OUTRO_T + 0.75]
    for when in pings:
        _, (_, _, top) = chord_at(when)
        chime = bell(top + 12, 1.4)
        sfx.add(when, chime, 0.035)
        send.add(when, chime, 0.05)
    for note in (69, 76, 81):
        chime = bell(note, 2.5)
        sfx.add(OUTRO_T + 0.1, chime, 0.03)
        send.add(OUTRO_T + 0.1, chime, 0.05)

    # One shared room for everything, so the effects sit in the same space.
    tail = seconds(1.6)
    reverb = []
    for channel in (send.left, send.right):
        impulse = band(rng.standard_normal(len(tail)), 150, 6000) * np.exp(-tail / 0.45)
        impulse /= np.sqrt(np.sum(impulse ** 2))
        size = len(channel) + len(impulse)
        wet = np.fft.irfft(np.fft.rfft(channel, size) * np.fft.rfft(impulse, size), size)[: len(channel)]
        reverb.append(wet)

    left = music.left + sfx.left + 0.5 * reverb[0]
    right = music.right + sfx.right + 0.5 * reverb[1]
    left, right = band(left, 30, 18000), band(right, 30, 18000)
    body = slice(int(DROP_T * SR), int(OUTRO_T * SR))
    rms = math.sqrt(float(np.mean(((left[body] + right[body]) / 2) ** 2)))
    gain = 0.13 / max(rms, 1e-9)
    stereo = np.stack([left, right]) * gain
    stereo = np.tanh(stereo * 1.15) / 1.15
    total = int(DURATION * SR)
    stereo = stereo[:, :total]
    tt = np.arange(total) / SR
    stereo *= np.clip(tt / 0.02, 0, 1) * np.clip((DURATION - tt) / 0.5, 0, 1)
    pcm = (np.clip(stereo, -1, 1) * 32000).astype("<i2").T.copy()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())
    print(f"audio: {path.name}, peak {float(np.abs(stereo).max()):.3f}, gain {gain:.2f}")


# ---------------------------------------------------------------- outputs


STILL_TIMES = (
    0.6, 1.8, 3.1, 3.9, 4.6, 5.6, 6.9, 7.3, 8.5, 9.9, 10.8, 12.6,
    13.9, 14.6, 15.4, 16.6, 18.5, 20.7, 22.5, 24.2, 25.6, 27.5, 28.6, 31.6,
)


def write_stills(kit: Kit, work: pathlib.Path) -> None:
    folder = work / "stills"
    folder.mkdir(exist_ok=True)
    for sheet, offset in enumerate(range(0, len(STILL_TIMES), 4)):
        board = Image.new("RGB", (W, H), (0, 0, 0))
        for slot, t in enumerate(STILL_TIMES[offset : offset + 4]):
            frame = render(kit, t).resize((W // 2, H // 2), Image.Resampling.LANCZOS)
            board.paste(frame, ((slot % 2) * W // 2, (slot // 2) * H // 2))
            ImageDraw.Draw(board).text(((slot % 2) * W // 2 + 12, (slot // 2) * H // 2 + 8), f"t={t:.2f}", fill=(255, 255, 0))
        board.save(folder / f"sheet-{sheet + 1}.jpg", quality=85)
    render(kit, POSTER_T).save(folder / "poster-full.jpg", quality=88)
    print(f"stills: {folder}")


def write_video(kit: Kit, work: pathlib.Path, ffmpeg: str) -> None:
    audio = work / "mix.wav"
    build_audio(audio)
    poster = render(kit, POSTER_T)
    poster.save(work / "brag.jpg", quality=90)
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(audio), "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-maxrate", "1800k", "-bufsize", "3600k",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest",
        str(work / "brag.mp4"),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for index in range(FRAMES):
        frame = poster if index == 0 else render(kit, index / FPS)
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    print(f"video: {work / 'brag.mp4'} ({FRAMES} frames)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=pathlib.Path)
    parser.add_argument("mode", choices=("stills", "audio", "full"))
    parser.add_argument("--fonts", type=pathlib.Path, default=pathlib.Path("C:/Windows/Fonts"))
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    if args.mode == "audio":
        build_audio(args.work / "mix.wav")
        return 0
    kit = Kit(args.work / "assets", args.fonts)
    if args.mode == "stills":
        write_stills(kit, args.work)
    else:
        write_video(kit, args.work, args.ffmpeg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
