"""Accept a document fetched in the browser, verify it, store it, extract it.

Payload (JSON):
  {"slug": "...", "doc": "adu-ordinance|definitions|sf-district-standards",
   "transport": "chrome-same-origin-fetch" | "chrome-rendered-dom" | ...,
   "parts": [{"url": "...", "b64": "<base64 of the exact bytes>",
              "sha256": "<hex digest computed in the browser>",
              "http": 200}]}

Every part's bytes are re-hashed here and compared with the digest the browser
computed before sending. A mismatch (truncation or corruption in transit)
rejects the whole document and nothing is written.
"""

import base64
import logging
import os

import corpuslib as cl
import record

LOG = logging.getLogger("corpus.ingest")


class IngestError(Exception):
  pass


def find_target(slug, doc):
  for jur in cl.load_targets()["jurisdictions"]:
    if jur["slug"] == slug:
      if doc not in jur["docs"]:
        raise IngestError("no target %s/%s" % (slug, doc))
      return jur, jur["docs"][doc]
  raise IngestError("no jurisdiction %s" % slug)


def ingest(payload):
  slug, doc = payload["slug"], payload["doc"]
  jur, spec = find_target(slug, doc)
  parts_in = payload["parts"]
  if not parts_in:
    raise IngestError("no parts")
  bodies = []
  parts = []
  for p in parts_in:
    body = base64.b64decode(p["b64"])
    digest = cl.sha256_bytes(body)
    if digest != p["sha256"]:
      raise IngestError("%s/%s: sha256 mismatch for %s (browser %s, received %s, %d bytes)"
                        % (slug, doc, p["url"], p["sha256"][:12], digest[:12], len(body)))
    if p.get("http") not in (None, 200):
      raise IngestError("%s/%s: HTTP %s for %s" % (slug, doc, p.get("http"), p["url"]))
    bodies.append(body)
    parts.append({"url": p["url"], "http": p.get("http"), "sha256": digest,
                  "bytes": len(body), "browser_sha256_verified": True})
  is_pdf = bodies[0][:5] == b"%PDF-"
  raw_path, _ = cl.doc_paths(slug, doc, "pdf" if is_pdf else "html")
  if is_pdf:
    if len(bodies) != 1:
      raise IngestError("one PDF per document")
    data = bodies[0]
  elif len(bodies) == 1:
    data = bodies[0]
  else:
    data = cl.join_parts([{"url": p["url"], "body": b} for p, b in zip(parts, bodies)])
  with open(raw_path, "wb") as fh:
    fh.write(data)
  rec = record.write_record(jur, doc, spec, raw_path, payload.get("transport"), parts,
                            host_marker=payload.get("host_marker"))
  LOG.info("%s: %d raw bytes, %d text chars, missing=%s", rec["id"], rec["bytes_raw"],
           rec["chars_text"], rec["missing_sections"])
  return rec
