# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=10"]
# ///
"""Pixel-accurate mockups of the ClaudeMon e-paper screens.

Re-implements the firmware's drawing primitives in Python, reading the real
font5x7 table straight out of DisplayManager.cpp so the mockups can't drift
from the device. Useful for README screenshots and for iterating on layout
without flashing hardware.

Usage:  uv run docs/tools/mockup.py   (writes PNGs into docs/images/)
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
FIRMWARE_DM = REPO / "esp32" / "firmware" / "src" / "display" / "DisplayManager.cpp"
OUT_DIR = REPO / "docs" / "images"

WIDTH, HEIGHT = 200, 200
SCALE = 3
PAPER = (232, 229, 222)   # e-paper off-white
INK = (28, 28, 30)


def load_font() -> list[list[int]]:
    """Parse the font5x7 table out of the firmware source."""
    src = FIRMWARE_DM.read_text()
    block = re.search(r"font5x7\[\]\[5\] PROGMEM = \{(.*?)\n\};", src, re.S).group(1)
    glyphs = [
        [int(v, 16) for v in row.split(",")]
        for row in re.findall(r"\{(0x[0-9A-Fa-f]{2}(?:,0x[0-9A-Fa-f]{2}){4})\}", block)
    ]
    assert len(glyphs) >= 59, f"font table parse failed ({len(glyphs)} glyphs)"
    return glyphs


FONT = load_font()


class Screen:
    """The firmware's DisplayManager drawing primitives, faithfully."""

    def __init__(self) -> None:
        self.px = [[False] * WIDTH for _ in range(HEIGHT)]

    def set_pixel(self, x: int, y: int, black: bool = True) -> None:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.px[y][x] = black

    # --- text (DisplayManager::drawChar / drawText / drawTextBold) ---

    def draw_char(self, x: int, y: int, c: str, scale: int) -> None:
        ch = c.upper()
        if not (" " <= ch <= "Z"):
            return
        glyph = FONT[ord(ch) - ord(" ")]
        for col in range(5):
            line = glyph[col]
            for row in range(7):
                if line & (1 << row):
                    for sx in range(scale):
                        for sy in range(scale):
                            self.set_pixel(x + col * scale + sx, y + row * scale + sy)

    def draw_text(self, x: int, y: int, text: str, scale: int = 1) -> None:
        for ch in text:
            self.draw_char(x, y, ch, scale)
            x += 6 * scale

    def draw_text_bold(self, x: int, y: int, text: str, scale: int = 1) -> None:
        self.draw_text(x, y, text, scale)
        self.draw_text(x + 1, y, text, scale)

    @staticmethod
    def text_width(text: str, scale: int = 1) -> int:
        return len(text) * 6 * scale

    def draw_centered_text(self, y: int, text: str, scale: int = 1) -> None:
        self.draw_text((WIDTH - self.text_width(text, scale)) // 2, y, text, scale)

    # --- shapes ---

    def draw_line(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if y1 == y2:
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.set_pixel(x, y1)
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.set_pixel(x1, y)

    def draw_rect(self, x: int, y: int, w: int, h: int) -> None:
        self.draw_line(x, y, x + w - 1, y)
        self.draw_line(x, y + h - 1, x + w - 1, y + h - 1)
        for yy in range(y, y + h):
            self.set_pixel(x, yy)
            self.set_pixel(x + w - 1, yy)

    def fill_rect(self, x: int, y: int, w: int, h: int, black: bool = True) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_pixel(xx, yy, black)

    def fill_round_rect(self, x: int, y: int, w: int, h: int, r: int, black: bool = True) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                # round the four corners
                dx = max(x + r - xx, xx - (x + w - 1 - r), 0)
                dy = max(y + r - yy, yy - (y + h - 1 - r), 0)
                if dx * dx + dy * dy <= r * r:
                    self.set_pixel(xx, yy, black)

    def save(self, name: str) -> Path:
        img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if self.px[y][x]:
                    img.putpixel((x, y), INK)
        img = img.resize((WIDTH * SCALE, HEIGHT * SCALE), Image.NEAREST)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / name
        img.save(out)
        return out


# --- usage screen (DisplayManager::renderUsageScreen, current firmware) ---

ROWS_TOP, BAR_X, BAR_W, BAR_H = 17, 22, 144, 10
PCT_RIGHT = WIDTH - 2


def draw_progress_bar(s: Screen, x: int, y: int, w: int, h: int, pct: int) -> None:
    s.draw_rect(x, y, w, h)
    if pct < 0:
        s.draw_text(x + (w - s.text_width("--")) // 2, y + (h - 7) // 2, "--")
        return
    fill = (w - 4) * min(pct, 100) // 100
    if fill > 0:
        s.fill_rect(x + 2, y + 2, fill, h - 4)


def draw_usage_gauge(s: Screen, y: int, tag: str, pct: int) -> None:
    s.draw_text(2, y + 1, tag)
    draw_progress_bar(s, BAR_X, y, BAR_W, BAR_H, pct)
    text = f"{pct}%" if pct >= 0 else "--"
    s.draw_text(PCT_RIGHT - s.text_width(text), y + 1, text)


def render_usage(accounts: list[dict], updated: str, stale: bool = False) -> Screen:
    s = Screen()
    s.draw_text_bold(2, 3, "CLAUDEMON")
    if stale:
        wx = WIDTH - 4 - s.text_width("STALE")
        s.draw_rect(wx - 3, 0, s.text_width("STALE") + 6, 13)
        s.draw_text_bold(wx, 3, "STALE")
    else:
        s.draw_text_bold(WIDTH - 2 - s.text_width(updated) - 1, 3, updated)
    s.draw_line(0, 13, WIDTH - 1, 13)

    count = min(len(accounts), 4)
    pitch = (HEIGHT - ROWS_TOP) // count if count else 0
    show_reset = pitch >= 48
    suffix = {"a": "AUTH!", "e": "ERR", "d": "DATA?"}

    for i, a in enumerate(accounts[:4]):
        y = ROWS_TOP + i * pitch
        right = suffix.get(a["st"], a["wk_rnw"])
        right_w = s.text_width(right) + 1
        if right_w > 1:
            s.draw_text_bold(PCT_RIGHT - right_w, y, right)
        max_chars = ((PCT_RIGHT - right_w - 6) - 2) // 6
        s.draw_text_bold(2, y, a["label"][:max_chars])
        draw_usage_gauge(s, y + 11, "5H", a["fh_pct"])
        draw_usage_gauge(s, y + 24, "WK", a["wk_pct"])
        if show_reset and a["fh_rst"]:
            s.draw_text_bold(BAR_X, y + 36, "5H RESETS " + a["fh_rst"])
    return s


# --- boot screen (main.cpp showBootScreen, current firmware) ---

def render_boot() -> Screen:
    s = Screen()
    title = "CLAUDEMON"
    s.draw_text_bold((WIDTH - s.text_width(title, 2) - 1) // 2, 14, title, 2)
    s.draw_centered_text(34, "USAGE MONITOR")

    s.fill_rect(84, 50, 5, 5)
    s.fill_rect(111, 50, 5, 5)
    s.draw_line(86, 55, 86, 62)
    s.draw_line(113, 55, 113, 62)
    s.fill_round_rect(60, 62, 80, 64, 14)
    s.fill_rect(78, 78, 10, 16, False)
    s.fill_rect(112, 78, 10, 16, False)
    s.fill_rect(94, 100, 12, 3, False)
    s.fill_round_rect(72, 108, 56, 13, 4, False)
    s.fill_rect(75, 111, 27, 7)
    s.fill_round_rect(72, 126, 16, 8, 3)
    s.fill_round_rect(112, 126, 16, 8, 3)

    s.draw_line(30, 150, 170, 150)
    s.draw_centered_text(160, "V0.3.0")
    s.draw_centered_text(178, "WAITING FOR HOST")
    return s


def main() -> None:
    demo = [
        {"label": "PERSONAL", "fh_pct": 12, "fh_rst": "3H14M", "wk_pct": 63, "wk_rnw": "WED 8PM (3D)", "st": "ok"},
        {"label": "WORK", "fh_pct": 47, "fh_rst": "1H02M", "wk_pct": 21, "wk_rnw": "SAT 1AM (6D)", "st": "ok"},
        {"label": "SIDEPROJ", "fh_pct": 88, "fh_rst": "44M", "wk_pct": 97, "wk_rnw": "SUN 9PM (7H)", "st": "ok"},
    ]
    states = [
        {"label": "PERSONAL", "fh_pct": 12, "fh_rst": "3H14M", "wk_pct": 63, "wk_rnw": "WED 8PM (3D)", "st": "ok"},
        {"label": "EXPIRED", "fh_pct": -1, "fh_rst": "", "wk_pct": -1, "wk_rnw": "", "st": "a"},
        {"label": "GLITCHY", "fh_pct": 55, "fh_rst": "2H30M", "wk_pct": -1, "wk_rnw": "", "st": "d"},
    ]
    for name, screen in [
        ("usage-screen.png", render_usage(demo, "14:32")),
        ("usage-screen-states.png", render_usage(states, "14:32")),
        ("usage-screen-stale.png", render_usage(demo, "14:32", stale=True)),
        ("boot-screen.png", render_boot()),
    ]:
        print("wrote", screen.save(name))


if __name__ == "__main__":
    main()
