#!/usr/bin/env python3
"""Capture what the Qoder CLI terminal UI shows, without touching the real screen.

Runs a command inside a pseudo-terminal of a fixed size, feeds its output to the pyte
VT100 emulator, sends scripted keystrokes, and saves each requested screen as an HTML
page (one fixed-width cell per character, colours preserved). The HTML is then turned
into a PNG with headless Chrome. Used to screenshot `qoderclicn --resume <session>`
for the development records; it only replays existing sessions and sends no prompts.

  tui_capture.py --cwd DIR --cols 150 --rows 46 --out shots/01 --title "..." \
      --steps '[{"wait": 12}, {"snap": "a"}, {"send": "\\u001b[5~"}, {"wait": 2}, {"snap": "b"}]' \
      -- qoderclicn --resume <session-id>
Requires: pip install pyte
"""
import argparse
import fcntl
import html
import json
import os
import select
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path

import pyte

NAMED = {
    "black": "#1e1e1e", "red": "#e06c75", "green": "#98c379", "brown": "#e5c07b", "yellow": "#e5c07b",
    "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#dcdfe4",
    "brightblack": "#7f848e", "brightred": "#f28b82", "brightgreen": "#b5e890", "brightbrown": "#f5d08a",
    "brightyellow": "#f5d08a", "brightblue": "#8cc4ff", "brightmagenta": "#e0a3f5", "brightcyan": "#7fd6e0",
    "brightwhite": "#ffffff",
}
FG, BG = "#dcdfe4", "#16181d"


class Screen(pyte.HistoryScreen):
    """pyte screen with scrollback that ignores private SGR sequences (e.g. xterm modifyOtherKeys `CSI > 4;2 m`)."""

    def select_graphic_rendition(self, *attrs, private=False):
        if not private:
            super().select_graphic_rendition(*attrs)


def colour(value: str, default: str) -> str:
    if value in ("default", None, ""):
        return default
    if value in NAMED:
        return NAMED[value]
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return "#" + value
    return default


def render(lines: list, columns: int, title: str) -> str:
    rows = []
    for line in lines:
        cells = []
        x = 0
        while x < columns:
            ch = line[x]
            nxt = line[x + 1] if x + 1 < columns else None
            wide = nxt is not None and nxt.data == "" and ch.data != ""
            fg, bg = colour(ch.fg, FG), colour(ch.bg, BG)
            if ch.reverse:
                fg, bg = bg, fg
            style = f"color:{fg};background:{bg};width:{2 if wide else 1}ch"
            if ch.bold:
                style += ";font-weight:700"
            if ch.italics:
                style += ";font-style:italic"
            if ch.underscore:
                style += ";text-decoration:underline"
            text = html.escape(ch.data) if ch.data.strip() else "&nbsp;"
            cells.append(f'<span style="{style}">{text}</span>')
            x += 2 if wide else 1
        rows.append('<div class="r">' + "".join(cells) + "</div>")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ margin:0; background:#0d0f12; padding:18px; }}
.cap {{ font:13px/1.4 -apple-system, "PingFang SC", sans-serif; color:#9aa4b2; margin:0 0 8px 4px; }}
.term {{ display:inline-block; background:{BG}; border-radius:10px; padding:14px 16px; box-shadow:0 6px 24px #0008; }}
.r {{ white-space:pre; height:1.35em; font:14px/1.35em Menlo, "SF Mono", "PingFang SC", monospace; }}
.r span {{ display:inline-block; overflow:hidden; text-align:left; }}
</style></head><body><div class="cap">{html.escape(title)}</div><div class="term">{''.join(rows)}</div></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--cols", type=int, default=150)
    ap.add_argument("--rows", type=int, default=46)
    ap.add_argument("--out", required=True, help="output prefix; writes <prefix>-<snap>.html")
    ap.add_argument("--title", default="")
    ap.add_argument("--steps", required=True)
    ap.add_argument("--slices", type=int, default=0,
                    help="after the steps, also write the whole scrollback as pages of this many rows")
    ap.add_argument("--cut-at", default="",
                    help="drop the scrollback from the last row containing this text on (used to leave out "
                         "the folder-trust prompt that `--resume` shows; the prompt is never answered)")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd

    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", args.rows, args.cols, 0, 0))
    env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", COLUMNS=str(args.cols), LINES=str(args.rows))
    proc = subprocess.Popen(cmd, cwd=args.cwd, stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
    os.close(slave)
    screen = Screen(args.cols, args.rows, history=100000, ratio=0.5)
    stream = pyte.ByteStream(screen)

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([master], [], [], 0.1)
            if master in ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    return
                if not data:
                    return
                stream.feed(data)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for step in json.loads(args.steps):
        if "wait" in step:
            pump(float(step["wait"]))
        if "send" in step:
            os.write(master, step["send"].encode())
            pump(0.3)
        if "snap" in step:
            path = out.parent / f"{out.name}-{step['snap']}.html"
            visible = [screen.buffer[y] for y in range(screen.lines)]
            path.write_text(render(visible, screen.columns, args.title), encoding="utf-8")
            print("wrote", path)
    if args.slices:
        allrows = list(screen.history.top) + [screen.buffer[y] for y in range(screen.lines)]
        if args.cut_at:
            texts = ["".join(allrows[i][x].data for x in range(screen.columns)) for i in range(len(allrows))]
            hits = [i for i, t in enumerate(texts) if args.cut_at in t]
            if hits:
                allrows = allrows[:hits[-1]]
            while allrows and not "".join(allrows[-1][x].data for x in range(screen.columns)).strip():
                allrows.pop()
        for i in range(0, len(allrows), args.slices):
            path = out.parent / f"{out.name}-h{i // args.slices:03d}.html"
            path.write_text(render(allrows[i:i + args.slices], screen.columns, args.title), encoding="utf-8")
        print("wrote", (len(allrows) + args.slices - 1) // args.slices, "history pages of", args.slices, "rows")
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()
