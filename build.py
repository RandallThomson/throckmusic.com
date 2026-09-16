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


DEFAULT_NEWS_BOX_HEIGHT = 402

_NOTE_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]\(([^)]+)\)')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def convert_links(line):
    """[[text]](url) -> a link styled like the small "note" text (matches
    class="note"). [text](url) -> a plain link. Order matters: the
    double-bracket form is matched first so it isn't swallowed by the
    plain-link pattern."""
    line = _NOTE_LINK_RE.sub(r'<a href="\2" class="note">\1</a>', line)
    line = _LINK_RE.sub(r'<a href="\2">\1</a>', line)
    return line


def load_news_txt(path):
    """Convert home.txt to HTML paragraphs. Blank lines = paragraph break.
    Supports [link text](url) markdown-style links, and a lone {left} or
    {center} line above a paragraph to override the box's default centered
    alignment. Returns (html, box_height) where box_height is the pixel
    height set by a lone {box-height: N} line (falling back to
    DEFAULT_NEWS_BOX_HEIGHT if the line is absent)."""
    if not os.path.isfile(path):
        return "", DEFAULT_NEWS_BOX_HEIGHT
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Strip comment lines (lines starting with #) before parsing paragraphs
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))

    box_height = DEFAULT_NEWS_BOX_HEIGHT
    match = re.search(r'^\{box-height:\s*(\d+)\}\s*$', text, re.MULTILINE)
    if match:
        box_height = int(match.group(1))
        text = text[:match.start()] + text[match.end():]

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
        elif lines and lines[0].strip() == "{left}":
            css_class = ' class="left"'
            lines = lines[1:]
        elif lines and lines[0].strip() == "{center}":
            css_class = ' class="center"'
            lines = lines[1:]
        lines = [convert_links(l) for l in lines]
        paragraphs.append(f"<p{css_class}>" + "<br>".join(lines) + "</p>")
        paragraphs.append('<p class="spacer">&nbsp;</p>')

    return "\n".join(paragraphs), box_height


def load_txt_content(path, spacer_mode=True):
    """Convert a page's box-content .txt file to HTML paragraphs. Same
    lightweight syntax as home.txt: blank line = new paragraph, # lines are
    comments, [text](url) becomes a link, {event} above a paragraph gives it
    the event-link style, {event-past} does the same but dims it (for a show
    that's already happened), {left}/{center} above a paragraph overrides
    the box's default centered alignment, and a lone {spacer} line inserts
    extra breathing room between paragraphs. When spacer_mode is True
    (default) a spacer is also added automatically between every paragraph,
    for prose-style content; set spacer_mode=False for tighter list-style
    content and add {spacer} markers by hand only where extra space is
    wanted."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))

    paragraphs = []
    if spacer_mode:
        paragraphs.append('<p class="spacer">&nbsp;</p>')
    for block in re.split(r'\n{2,}', text.strip()):
        lines = block.splitlines()
        if lines and lines[0].strip() == "{spacer}":
            paragraphs.append('<p class="spacer">&nbsp;</p>')
            continue
        if len(lines) == 1 and lines[0].strip().startswith("<hr"):
            paragraphs.append(lines[0].strip())
            if spacer_mode:
                paragraphs.append('<p class="spacer">&nbsp;</p>')
            continue
        css_class = ""
        if lines and lines[0].strip() == "{event}":
            css_class = ' class="event"'
            lines = lines[1:]
        elif lines and lines[0].strip() == "{event-past}":
            css_class = ' class="event past"'
            lines = lines[1:]
        elif lines and lines[0].strip() == "{left}":
            css_class = ' class="left"'
            lines = lines[1:]
        elif lines and lines[0].strip() == "{center}":
            css_class = ' class="center"'
            lines = lines[1:]
        lines = [convert_links(l) for l in lines]
        paragraphs.append(f"<p{css_class}>" + "<br>".join(lines) + "</p>")
        if spacer_mode:
            paragraphs.append('<p class="spacer">&nbsp;</p>')

    return "\n".join(paragraphs)


def load_audio_txt(path):
    """Convert a song-listing .txt file (like src/audio.txt) into the boxed
    HTML structure used on the Audio page. Line-oriented, not paragraph
    (blank-line) based, since a track listing is closer to a list than
    prose. Recognizes:
    - Lines starting with # are comments and are ignored.
    - Blank lines are ignored (they don't add space by themselves - use
      {spacer} for that).
    - [[text]](url) makes a "note"-styled link (matches the small song-link
      style). [text](url) makes a plain link. Plain HTML tags are passed
      through as-is.
    - {box} on its own line starts a new bordered box (closing the
      previous one, if any). Put it before each new section/album.
    - {h3: Heading text} inserts a section heading. Raw HTML is allowed
      inside it, e.g. {h3: Larmes De Colere <span class="note">(tears of
      rage)</span>} to show part of a heading in the small note style.
    - {note} above a line makes that line small "note" style text (for
      details like file size, credits, etc).
    - {image: WIDTHxHEIGHT | alt text} above a line containing just an
      image path (e.g. images/BunFun.gif) inserts that image.
    - {boxend} on its own line closes the current box without opening a
      new one. Use it when you want a spacer or other content to sit
      outside/between boxes rather than inside one.
    - {spacer} on its own line adds a little vertical breathing room.
    - Any other line becomes a plain paragraph.
    """
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    lines = [l for l in raw_lines if not l.strip().startswith("#")]

    h3_re = re.compile(r'^\{h3:\s*(.*?)\s*\}$')
    image_re = re.compile(r'^\{image:\s*(\d+)\s*x\s*(\d+)\s*\|\s*(.*?)\s*\}$')

    out = []
    box_open = False
    pending_note = False
    pending_image = None  # (width, height, alt) once an {image:...} marker is seen

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line == "{box}":
            if box_open:
                out.append("</div>")
            out.append('<div class="box">')
            box_open = True
            continue

        if line == "{boxend}":
            if box_open:
                out.append("</div>")
                box_open = False
            continue

        if line == "{spacer}":
            out.append('<p>&nbsp;</p>')
            continue

        if line == "{note}":
            pending_note = True
            continue

        m = h3_re.match(line)
        if m:
            out.append(f"<h3>{convert_links(m.group(1))}</h3>")
            continue

        m = image_re.match(line)
        if m:
            pending_image = (m.group(1), m.group(2), m.group(3))
            continue

        if pending_image:
            width, height, alt = pending_image
            out.append(f'<p><img src="{line}" width="{width}" height="{height}" alt="{alt}"></p>')
            pending_image = None
            continue

        text = convert_links(line)
        if pending_note:
            out.append(f'<p><span class="note">{text}</span></p>')
            pending_note = False
        else:
            out.append(f"<p>{text}</p>")

    if box_open:
        out.append("</div>")

    return "\n".join(out)

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

    news_html, news_box_height = load_news_txt(os.path.join(SRC_DIR, "home.txt"))

    for page_file in sorted(pages):
        page_path = os.path.join(SRC_DIR, page_file)
        with open(page_path, "r", encoding="utf-8") as f:
            raw = f.read()

        fm, body = parse_front_matter(raw)
        layout_name = fm.get("layout", "base.njk")
        permalink = fm.get("permalink", page_file.replace(".njk", ".html"))
        page_vars = {k: v for k, v in fm.items() if k not in ("layout", "permalink")}
        page_vars["news_html"] = news_html
        page_vars["news_box_height"] = news_box_height

        content_txt_file = fm.get("contentTxt")
        if content_txt_file:
            content_txt_path = os.path.join(SRC_DIR, content_txt_file)
            if fm.get("contentTxtFormat", "").strip().lower() == "audio":
                page_vars["content_txt"] = load_audio_txt(content_txt_path)
            else:
                spacer_mode = fm.get("contentSpacing", "").strip().lower() != "compact"
                page_vars["content_txt"] = load_txt_content(
                    content_txt_path, spacer_mode=spacer_mode
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
