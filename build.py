#!/usr/bin/env python3
"""
Build script for throckmusic.com
Processes Nunjucks/Jinja2 templates in src/ and outputs to _site/

Usage:
    python build.py          # build only
    python build.py --serve  # build and start local preview server
"""

import os
import re
import shutil
import sys
import http.server
import threading


def load_news_txt(path):
    """Convert news.txt to HTML paragraphs. Blank lines = paragraph break.
    Supports [link text](url) markdown-style links."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Strip comment lines (lines starting with #) before parsing paragraphs
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))

    def convert_links(line):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)

    paragraphs = ['<p class="spacer">&nbsp;</p>']
    for block in re.split(r'\n{2,}', text.strip()):
        lines = block.splitlines()
        css_class = ""
        if lines and lines[0].strip() == "{event}":
            css_class = ' class="event"'
            lines = lines[1:]
        elif lines and lines[0].strip() == "{updated}":
            css_class = ' class="updated"'
            lines = lines[1:]
        lines = [convert_links(l) for l in lines]
        paragraphs.append(f"<p{css_class}>" + "<br>".join(lines) + "</p>")
        paragraphs.append('<p class="spacer">&nbsp;</p>')

    return "\n".join(paragraphs)


def load_txt_content(path, spacer_mode=True):
    """Convert a page's box-content .txt file to HTML paragraphs. Same
    lightweight syntax as news.txt: blank line = new paragraph, # lines are
    comments, [text](url) becomes a link, {event} above a paragraph gives it
    the event-link style, and a lone {spacer} line inserts extra breathing
    room between paragraphs. When spacer_mode is True (default) a spacer is
    also added automatically between every paragraph, for prose-style
    content; set spacer_mode=False for tighter list-style content and add
    {spacer} markers by hand only where extra space is wanted."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))

    def convert_links(line):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)

    paragraphs = []
    if spacer_mode:
        paragraphs.append('<p class="spacer">&nbsp;</p>')
    for block in re.split(r'\n{2,}', text.strip()):
        lines = block.splitlines()
        if lines and lines[0].strip() == "{spacer}":
            paragraphs.append('<p class="spacer">&nbsp;</p>')
            continue
        css_class = ""
        if lines and lines[0].strip() == "{event}":
            css_class = ' class="event"'
            lines = lines[1:]
        lines = [convert_links(l) for l in lines]
        paragraphs.append(f"<p{css_class}>" + "<br>".join(lines) + "</p>")
        if spacer_mode:
            paragraphs.append('<p class="spacer">&nbsp;</p>')

    return "\n".join(paragraphs)

from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
INCLUDES_DIR = os.path.join(SRC_DIR, "_includes")
CSS_SRC_DIR = os.path.join(SRC_DIR, "css")
SITE_DIR = os.path.join(BASE_DIR, "_site")


def parse_front_matter(text):
    """Split YAML front matter from template body. Returns (dict, body_string)."""
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    fm_text, body = match.group(1), match.group(2)
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, body


def build():
    os.makedirs(SITE_DIR, exist_ok=True)

    # Copy static passthrough directories (dirs_exist_ok overwrites in place)
    for dirname in ("images", "audio", "attic"):
        src = os.path.join(BASE_DIR, dirname)
        dst = os.path.join(SITE_DIR, dirname)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"  copied {dirname}/")

    # Copy CSS
    css_dst = os.path.join(SITE_DIR, "css")
    if os.path.isdir(CSS_SRC_DIR):
        shutil.copytree(CSS_SRC_DIR, css_dst, dirs_exist_ok=True)
        print("  copied css/")

    # Copy CNAME (custom domain for GitHub Pages), if present
    cname_src = os.path.join(BASE_DIR, "CNAME")
    if os.path.isfile(cname_src):
        shutil.copy(cname_src, os.path.join(SITE_DIR, "CNAME"))
        print("  copied CNAME")

    # Set up Jinja2 environment pointing at _includes/
    env = Environment(
        loader=FileSystemLoader(INCLUDES_DIR),
        autoescape=False,
        keep_trailing_newline=True,
    )

    # Process each .njk page in src/ (skip _includes/)
    pages = [
        f for f in os.listdir(SRC_DIR)
        if f.endswith(".njk") and os.path.isfile(os.path.join(SRC_DIR, f))
    ]

    news_html = load_news_txt(os.path.join(SRC_DIR, "news.txt"))

    for page_file in sorted(pages):
        page_path = os.path.join(SRC_DIR, page_file)
        with open(page_path, "r", encoding="utf-8") as f:
            raw = f.read()

        fm, body = parse_front_matter(raw)
        layout_name = fm.get("layout", "base.njk")
        permalink = fm.get("permalink", page_file.replace(".njk", ".html"))
        page_vars = {k: v for k, v in fm.items() if k not in ("layout", "permalink")}
        page_vars["news_html"] = news_html

        content_txt_file = fm.get("contentTxt")
        if content_txt_file:
            spacer_mode = fm.get("contentSpacing", "").strip().lower() != "compact"
            page_vars["content_txt"] = load_txt_content(
                os.path.join(SRC_DIR, content_txt_file), spacer_mode=spacer_mode
            )

        # Render the page body as a Jinja2 template (handles any inline tags)
        body_tmpl = env.from_string(body)
        rendered_body = body_tmpl.render(**page_vars)

        # Render the layout with content = rendered body
        layout_tmpl = env.get_template(layout_name)
        final_html = layout_tmpl.render(content=rendered_body, **page_vars)

        out_path = os.path.join(SITE_DIR, permalink)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        print(f"  built {permalink}")

    print(f"\nBuild complete -> {SITE_DIR}")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress per-request logging

    def log_request(self, code="-", size="-"):
        print(f"  {self.command} {self.path} -> {code}")


def serve(port=8080):
    os.chdir(SITE_DIR)
    handler = QuietHandler
    server = http.server.HTTPServer(("", port), handler)
    print(f"\nPreview server running at http://localhost:{port}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    print("Building site...\n")
    build()
    if "--serve" in sys.argv:
        serve()
