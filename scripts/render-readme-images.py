"""Render sections of site/index.html to docs/images/*.png for the README.

GitHub strips CSS from READMEs, so the README shows screenshots of the
marketing page instead. Rerun after changing the site: python3 scripts/render-readme-images.py
Needs Google Chrome on macOS.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / "docs" / "images"
TMP = Path(tempfile.mkdtemp(prefix="snapback-shots-"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH = 1200

# name -> CSS selector of the only block to keep visible
TARGETS = {
    "hero": "header.hero",
    "how-it-works": "section#how",
    "features": "section:not([id])",
    "hardware": "section#hardware",
}

html = (SITE / "index.html").read_text()
html = html.replace("<head>", f'<head><base href="{SITE.as_uri()}/">', 1)


def page(selector, extra_js=""):
    css = (
        "nav, footer, header.hero, section { display: none !important; }"
        f"{selector} {{ display: block !important; border-top: 0 !important; }}"
    )
    js = f"<script>window.addEventListener('load',()=>{{{extra_js}}});</script>" if extra_js else ""
    return html.replace("</head>", f"<style>{css}</style>{js}</head>", 1)


def chrome(*args):
    return subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", *args],
        capture_output=True, text=True, timeout=60,
    ).stdout


OUT.mkdir(parents=True, exist_ok=True)
for name, sel in TARGETS.items():
    probe = TMP / f"{name}-probe.html"
    probe.write_text(page(sel, f"document.body.setAttribute('data-h', Math.ceil(document.querySelector('{sel}').getBoundingClientRect().height));"))
    dom = chrome(f"--window-size={WIDTH},800", "--virtual-time-budget=3000", "--dump-dom", probe.as_uri())
    height = int(re.search(r'data-h="(\d+)"', dom).group(1))
    shot = TMP / f"{name}.html"
    shot.write_text(page(sel))
    chrome(
        f"--window-size={WIDTH},{height}",
        "--force-device-scale-factor=2",
        "--virtual-time-budget=3000",
        f"--screenshot={OUT / (name + '.png')}",
        shot.as_uri(),
    )
    print(name, height, file=sys.stderr)
