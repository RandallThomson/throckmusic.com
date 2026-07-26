#!/usr/bin/env python3
"""
Start a local preview server for the built site.
Run build.py first, then run this script.

Usage:  python preview.py          (serves on port 8081)
        python preview.py 9000     (serves on custom port)
"""

import os, sys, http.server, socketserver

SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_site")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081

if not os.path.isdir(SITE_DIR) or not os.listdir(SITE_DIR):
    print("ERROR: _site/ is empty or missing. Run  python build.py  first.")
    sys.exit(1)

os.chdir(SITE_DIR)
Handler = http.server.SimpleHTTPRequestHandler

print(f"Preview server running at http://localhost:{PORT}")
print("Open that URL in your browser to preview the site.")
print("Press Ctrl+C to stop.\n")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
