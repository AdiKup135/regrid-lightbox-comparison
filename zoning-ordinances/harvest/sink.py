"""Localhost receiver for browser-fetched documents.

Run: python3 sink.py [port]   (default 8770)
The page POSTs an ingest payload (see ingest.py) to http://127.0.0.1:8770/save.
Chrome gates public-origin -> loopback requests behind a Local Network Access
permission; if the page's fetch hangs, allow the prompt or use save_doc.py.
"""

import json
import logging
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ingest

LOG = logging.getLogger("corpus.sink")


class Handler(BaseHTTPRequestHandler):
  def _cors(self):
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.send_header("Access-Control-Allow-Private-Network", "true")

  def _reply(self, code, obj):
    body = json.dumps(obj).encode("utf-8")
    self.send_response(code)
    self._cors()
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def do_OPTIONS(self):
    self.send_response(204)
    self._cors()
    self.end_headers()

  def do_GET(self):
    # /wait?ms=N answers after N ms (max 5000): a pause for the page script that
    # Chrome does not throttle in a hidden tab the way it throttles timers
    if self.path.startswith("/wait"):
      m = re.search(r"ms=(\d+)", self.path)
      time.sleep(min(int(m.group(1)) if m else 1000, 5000) / 1000.0)
    self._reply(200, {"ok": True})

  def do_POST(self):
    length = int(self.headers.get("Content-Length") or 0)
    try:
      payload = json.loads(self.rfile.read(length))
      rec = ingest.ingest(payload)
      self._reply(200, {"ok": True, "id": rec["id"], "chars_text": rec["chars_text"],
                        "missing": rec["missing_sections"], "sha256_raw": rec["sha256_raw"]})
    except Exception as exc:  # report every failure to the page
      LOG.error("ingest failed: %s", exc)
      self._reply(400, {"ok": False, "error": str(exc)})

  def log_message(self, fmt, *args):
    LOG.info(fmt, *args)


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
  port = int(argv[1]) if len(argv) > 1 else 8770
  ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
  main(sys.argv)
