#!/usr/bin/env python3
"""Build the public themorningcommit static site atomically."""
from __future__ import annotations

import argparse
import html
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://themorningcommit.com"
DESCRIPTION = (
    "A daily, source-linked briefing on the developments shaping AI development, "
    "writing, art, research, business, and education."
)
DATE_RE = re.compile(r"<strong>Date</strong><br>\s*([^<]+)", re.I)
TITLE_RE = re.compile(r"<title>.*?</title>", re.I | re.S)
SEO_RE = re.compile(r"\s*<!-- tmc-seo:start -->.*?<!-- tmc-seo:end -->\s*", re.S)
NAV_RE = re.compile(r"\s*<!-- tmc-nav:start -->.*?<!-- tmc-nav:end -->\s*", re.S)
NAV_CSS_RE = re.compile(r"\s*<!-- tmc-nav-css:start -->.*?<!-- tmc-nav-css:end -->\s*", re.S)


def parse_date(raw: str) -> datetime:
    match = DATE_RE.search(raw)
    if not match:
        raise ValueError("reader-facing Date not found")
    return datetime.strptime(
        html.unescape(match.group(1)).strip(), "%B %d, %Y"
    ).replace(tzinfo=timezone.utc)


def decorate(raw: str, date: datetime, canonical: str) -> str:
    raw = SEO_RE.sub("\n", raw)
    raw = NAV_RE.sub("\n", raw)
    raw = NAV_CSS_RE.sub("\n", raw)
    human = f"{date:%B} {date.day}, {date:%Y}"
    title = f"themorningcommit daily intelligence brief | {human}"
    seo = f'''<!-- tmc-seo:start -->
<meta name="description" content="{DESCRIPTION}">
<meta name="author" content="themorningcommit">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="themorningcommit">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="{canonical}">
<meta property="article:published_time" content="{date.date().isoformat()}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{DESCRIPTION}">
<meta name="theme-color" content="#1a1d22">
<!-- tmc-seo:end -->'''
    raw = TITLE_RE.sub(f"<title>{html.escape(title)}</title>", raw, count=1)
    raw = raw.replace("</head>", seo + "\n</head>", 1)
    nav_css = '''<!-- tmc-nav-css:start -->
<style>
.site-nav{width:min(100% - 48px,1180px);margin:0 auto;padding:18px 0 0;display:flex;justify-content:flex-end;gap:20px;font:500 .7rem/1.2 var(--font-sans,system-ui);letter-spacing:.12em;text-transform:uppercase}
.site-nav a{color:var(--text-2,#95938d);text-decoration:none}
.site-nav a:hover,.site-nav a:focus-visible{color:var(--brass-bright,#b0c2ac);text-decoration:underline;text-underline-offset:4px}
@media(max-width:520px){.site-nav{width:min(100% - 24px,1180px)}}
</style>
<!-- tmc-nav-css:end -->'''
    raw = raw.replace("</head>", nav_css + "\n</head>", 1)
    nav = '''<!-- tmc-nav:start -->
<nav class="site-nav" aria-label="Publication"><a href="/">Latest</a><a href="/archive/">Archive</a><a href="/feed.xml">RSS</a></nav>
<!-- tmc-nav:end -->'''
    raw = raw.replace(
        '<body data-style-system="themorningcommit">',
        '<body data-style-system="themorningcommit">\n' + nav,
        1,
    )
    return raw


def archive_index(dates: list[datetime]) -> str:
    items = "\n".join(
        f'<li><a href="/archive/{d:%Y/%m/%d}/">{d:%B} {d.day}, {d:%Y}</a></li>'
        for d in sorted(dates, reverse=True)
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Archive | themorningcommit</title><meta name="description" content="Past editions of themorningcommit daily intelligence brief."><meta name="robots" content="index, follow"><link rel="canonical" href="{SITE}/archive/"><meta property="og:type" content="website"><meta property="og:site_name" content="themorningcommit"><meta property="og:title" content="Archive | themorningcommit"><meta property="og:description" content="Past editions of themorningcommit daily intelligence brief."><meta property="og:url" content="{SITE}/archive/"><meta name="twitter:card" content="summary"><meta name="theme-color" content="#1a1d22"><style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#1a1d22;color:#c4c2bc;font:18px/1.65 Georgia,serif}}main{{width:min(100% - 40px,760px);margin:0 auto;padding:10vh 0}}.mark{{color:#94a890;font:500 .72rem/1.2 system-ui;letter-spacing:.16em;text-transform:uppercase}}h1{{font-size:clamp(2.8rem,8vw,5rem);font-weight:400;line-height:1;margin:.3em 0 .7em}}ul{{list-style:none;padding:0;border-top:1px solid #3a3f4a}}li{{border-bottom:1px solid #2c303a}}a{{display:block;padding:18px 0;color:#b0c2ac;text-decoration:none}}a:hover,a:focus-visible{{color:#c4c2bc;text-decoration:underline;text-underline-offset:5px}}nav{{display:flex;gap:18px;font:500 .7rem system-ui;letter-spacing:.12em;text-transform:uppercase}}nav a{{padding:0}}</style></head><body><main><nav aria-label="Publication"><a href="/">Latest</a><a href="/feed.xml">RSS</a></nav><p class="mark">themorningcommit.</p><h1>Archive</h1><ul>{items}</ul></main></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    report = Path(args.report).resolve()
    root = Path(args.root).resolve()
    public = root / "public"
    raw = report.read_text(encoding="utf-8")
    date = parse_date(raw)
    if re.search(r"RPA Library|rpallibrary", raw, re.I):
        raise ValueError("legacy branding found in report")
    if re.search(r"Processing receipt|provenance ledger|\bUID\s*:|\bNews ID\s*:", raw, re.I):
        raise ValueError("operational metadata found in report")

    staging = Path(tempfile.mkdtemp(prefix="tmc-site-", dir=str(root)))
    try:
        output = staging / "public"
        if public.exists():
            shutil.copytree(public, output)
        else:
            output.mkdir(parents=True)
        dated_route = f"/archive/{date:%Y/%m/%d}/"
        archive_path = output / dated_route.strip("/") / "index.html"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(
            decorate(raw, date, SITE + dated_route), encoding="utf-8"
        )
        (output / "index.html").write_text(
            decorate(raw, date, SITE + "/"), encoding="utf-8"
        )

        dates: list[datetime] = []
        for page in output.glob(
            "archive/[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/index.html"
        ):
            try:
                dates.append(
                    datetime.strptime("/".join(page.parts[-4:-1]), "%Y/%m/%d").replace(
                        tzinfo=timezone.utc
                    )
                )
            except ValueError:
                pass
        (output / "archive").mkdir(exist_ok=True)
        (output / "archive/index.html").write_text(
            archive_index(dates), encoding="utf-8"
        )
        urls = [SITE + "/", SITE + "/archive/"] + [
            f"{SITE}/archive/{d:%Y/%m/%d}/" for d in sorted(dates, reverse=True)
        ]
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{escape(url)}</loc></url>\n" for url in urls)
            + "</urlset>\n"
        )
        (output / "sitemap.xml").write_text(sitemap, encoding="utf-8")
        entries = "".join(
            f'<entry><title>themorningcommit — {d:%B} {d.day}, {d:%Y}</title><link href="{SITE}/archive/{d:%Y/%m/%d}/"/><id>{SITE}/archive/{d:%Y/%m/%d}/</id><updated>{d:%Y-%m-%dT12:00:00Z}</updated><summary>{escape(DESCRIPTION)}</summary></entry>'
            for d in sorted(dates, reverse=True)[:20]
        )
        feed = f'''<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>themorningcommit</title><link href="{SITE}/feed.xml" rel="self"/><link href="{SITE}/"/><id>{SITE}/</id><updated>{date:%Y-%m-%dT12:00:00Z}</updated><subtitle>{escape(DESCRIPTION)}</subtitle>{entries}</feed>'''
        (output / "feed.xml").write_text(feed, encoding="utf-8")

        backup = root / ".public.previous"
        if backup.exists():
            shutil.rmtree(backup)
        if public.exists():
            public.replace(backup)
        output.replace(public)
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    print(
        f"BUILT date={date.date().isoformat()} archive={dated_route} root={root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
