"""Fetch every target whose transport is `direct` with curl, store raw bytes,
extract text, and write manifest records.

Usage: python3 fetch_direct.py [slug ...]
"""

import html
import json
import logging
import os
import re
import sys
import tempfile

import corpuslib as cl
import record

LOG = logging.getLogger("corpus.fetch_direct")


def expand_toc(toc, ua):
  """Section URLs listed on a chapter contents page (hosts that serve one
  section per page, e.g. law.cityofsanmateo.org). toc = {"urls": [...],
  "href_re": regex on the link path, "label_re": optional regex on the
  link text after the section number}. Done at fetch time, so a refresh
  follows added or renumbered sections."""
  out = []
  for url in toc["urls"]:
    fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
    os.close(fd)
    code, _ = cl.curl(url, tmp, ua=ua)
    with open(tmp, encoding="utf-8", errors="replace") as fh:
      page = fh.read()
    os.remove(tmp)
    if code != 200:
      LOG.error("contents page HTTP %s: %s", code, url)
      continue
    base = url.split("/us/", 1)[0] if "/us/" in url else url.rsplit("/", 1)[0]
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
      href, label = m.group(1), html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
      if not re.search(toc["href_re"], href):
        continue
      title = re.sub(r"^\S+\s+", "", label)
      if toc.get("label_re") and not re.search(toc["label_re"], title, re.I):
        continue
      full = href if href.startswith("http") else base + href
      if full not in out:
        out.append(full)
  return out


def github_default_branch(repo):
  """Default branch of a public GitHub repo (the publication in effect for
  the Open Law Library mirrors), via the GitHub API."""
  fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
  os.close(fd)
  code, _ = cl.curl("https://api.github.com/repos/%s" % repo, tmp)
  with open(tmp, encoding="utf-8") as fh:
    body = fh.read()
  os.remove(tmp)
  if code != 200:
    return None, None
  data = json.loads(body)
  branch = data.get("default_branch")
  fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
  os.close(fd)
  cl.curl("https://api.github.com/repos/%s/branches/%s" % (repo, branch), tmp)
  with open(tmp, encoding="utf-8") as fh:
    head = json.loads(fh.read() or "{}")
  os.remove(tmp)
  commit = head.get("commit", {})
  return branch, {"sha": commit.get("sha"),
                  "message": commit.get("commit", {}).get("message"),
                  "date": commit.get("commit", {}).get("committer", {}).get("date")}


def fetch_marker(jur, ua):
  """The host's own currency statement, read from jur["marker_url"] with
  jur["marker_re"] (e.g. Code Publishing / Open Law Library home pages)."""
  if not jur.get("marker_url") or not jur.get("marker_re"):
    return None
  fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
  os.close(fd)
  code, _ = cl.curl(jur["marker_url"], tmp, ua=ua)
  with open(tmp, encoding="utf-8", errors="replace") as fh:
    page = fh.read()
  os.remove(tmp)
  text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
  m = re.search(jur["marker_re"], text)
  return m.group(0).strip() if m else None


def mirror_url(url, mirror, branch):
  """Map a live page URL onto its bulk-download mirror (see targets.json)."""
  path = url.split(mirror["from"], 1)[1]
  return mirror["to"].format(branch=branch) + path + mirror.get("suffix", "")


def fetch_doc(jur, doc, spec):
  ua = cl.UA_OLD if spec.get("ua", jur.get("ua", "old")) == "old" else cl.UA_NEW
  mirror = jur.get("mirror")
  branch = None
  if mirror:
    branch, head = github_default_branch(mirror["repo"])
    if not branch:
      LOG.error("%s: cannot resolve mirror branch", jur["slug"])
      return None
    jur = dict(jur, mirror_head=dict(head, branch=branch))
  if spec.get("toc"):
    terms = spec["toc"].get("label_re")
    if terms == "LOT_TERMS":
      spec["toc"]["label_re"] = cl.load_targets()["lot_terms"]
    toc = dict(spec["toc"])
    if mirror:
      toc["urls"] = [mirror_url(u, mirror, branch) for u in toc["urls"]]
    urls = expand_toc(toc, ua)
    if mirror:
      # links on a mirrored contents page resolve against the mirror; each
      # section is a directory holding index.html
      sfx = mirror.get("suffix", "")
      urls = [u if u.endswith(sfx) else u + sfx for u in urls]
    if not urls:
      LOG.error("%s/%s: no section links found on contents page", jur["slug"], doc)
      return None
    # the contents page is kept as the first part: it carries the chapter
    # heading and its codification history line
    spec = dict(spec, urls=(toc["urls"] if toc.get("keep_contents") else []) + urls)
  is_pdf = spec.get("raw_ext") == "pdf"
  raw_path, _ = cl.doc_paths(jur["slug"], doc, "pdf" if is_pdf else "html")
  parts = []
  bodies = []
  for url in spec["urls"]:
    fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
    os.close(fd)
    code, final = cl.curl(url, tmp, ua=ua)
    with open(tmp, "rb") as fh:
      body = fh.read()
    os.remove(tmp)
    if code != 200 or not body:
      LOG.error("%s/%s: HTTP %s for %s", jur["slug"], doc, code, url)
      return None
    parts.append({"url": url, "final_url": final, "http": code,
                  "sha256": cl.sha256_bytes(body), "bytes": len(body)})
    bodies.append(body)
  if is_pdf:
    if len(bodies) != 1:
      LOG.error("%s/%s: one PDF per document", jur["slug"], doc)
      return None
    with open(raw_path, "wb") as fh:
      fh.write(bodies[0])
  else:
    with open(raw_path, "wb") as fh:
      fh.write(bodies[0] if len(bodies) == 1 else cl.join_parts(
        [{"url": u, "body": b} for u, b in zip(spec["urls"], bodies)]))
  transport = "direct-curl (%s UA)" % ("old Chrome 91" if ua == cl.UA_OLD else "Chrome 140")
  if mirror:
    transport += ", from bulk-download mirror %s@%s (%s)" % (
      mirror["repo"], branch, (jur["mirror_head"].get("sha") or "")[:12])
  marker = fetch_marker(jur, ua)
  return record.write_record(jur, doc, spec, raw_path, transport, parts, host_marker=marker)


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  slugs = set(argv[1:])
  for jur in cl.load_targets()["jurisdictions"]:
    if slugs and jur["slug"] not in slugs:
      continue
    for doc, spec in jur["docs"].items():
      if spec.get("transport", jur.get("transport")) != "direct":
        continue
      rec = fetch_doc(jur, doc, spec)
      if rec:
        LOG.info("%s: %d chars, missing=%s", rec["id"], rec["chars_text"], rec["missing_sections"])
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
