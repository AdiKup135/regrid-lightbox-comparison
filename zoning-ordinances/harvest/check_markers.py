"""Cheap change detection: compare each host's current change marker with
the one recorded in corpus/manifest.json, without re-fetching documents.

Usage:
  python3 check_markers.py              check every host reachable by curl
  python3 check_markers.py --browser    also print the snippet for Chrome hosts
  python3 check_markers.py --observed obs.json
                                        fold in markers read in Chrome
                                        (browser/markers.js output, saved as JSON)

Writes corpus/markers-observed.json (latest observation per jurisdiction) and
prints one line per jurisdiction: same / CHANGED / unknown.

Curl-reachable markers:
  Municode       localapi PublicationVersion (supplement name + online date),
                 the same public endpoint the library page itself calls
  Code Publishing "current through Ordinance N, passed <date>" on the code home
  Open Law Library (San Mateo) "Current through <date> Last codified ordinance ..."
                 plus the head commit of the bulk-download mirror
  PDF            HTTP Last-Modified / Content-Length, and the PDF's sha256
Chrome-only hosts (eCode360, American Legal, municipal.codes) print "unknown"
until browser/markers.js output is supplied with --observed.
"""

import datetime
import json
import logging
import os
import re
import subprocess
import sys
import tempfile

import corpuslib as cl
import fetch_direct

LOG = logging.getLogger("corpus.check_markers")
OBSERVED_PATH = os.path.join(cl.CORPUS_DIR, "markers-observed.json")
MONTHS = {m: i for i, m in enumerate(
  ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _get(url, ua=cl.UA_OLD):
  fd, tmp = tempfile.mkstemp(dir=cl.CORPUS_DIR)
  os.close(fd)
  code, _ = cl.curl(url, tmp, ua=ua)
  with open(tmp, "rb") as fh:
    body = fh.read()
  os.remove(tmp)
  return code, body


def municode_marker(jur):
  """Supplement name and online date of the current Municode publication."""
  url = jur["docs"]["adu-ordinance"]["urls"][0]
  m = re.search(r"library\.municode\.com/(\w+)/([^/]+)/codes/([^?/]+)", url)
  state, client, code = m.groups()
  status, body = _get("https://library.municode.com/localapi/Organizations/GetByUrlEncodedNames/%s/%s"
                      % (state, client))
  if status != 200:
    return None
  cid = json.loads(body)["ClientID"]
  status, body = _get("https://library.municode.com/localapi/PublicationVersion/GetViewModel/%s/%s"
                      % (cid, code.replace("_", "%20")))
  if status != 200:
    return None
  ver = json.loads(body)
  return "%s, online %s" % (ver.get("name"), (ver.get("onlineDate") or "")[:10])


def municode_date_from_label(label):
  """'VERSION: JAN 9, 2026 (CURRENT)' -> '2026-01-09'."""
  m = re.search(r"VERSION:\s*([A-Z]{3})\s+(\d{1,2}),\s+(\d{4})", label or "")
  if not m:
    return None
  return "%s-%02d-%02d" % (m.group(3), MONTHS[m.group(1)], int(m.group(2)))


def pdf_marker(jur):
  url = jur["docs"]["adu-ordinance"]["urls"][0]
  res = subprocess.run(["curl", "-sSI", "-L", "-A", cl.UA_OLD, url], capture_output=True, text=True)
  heads = {k.strip().lower(): v.strip() for k, _, v in
           (l.partition(":") for l in res.stdout.splitlines() if ":" in l)}
  status, body = _get(url)
  if status != 200:
    return None
  return "sha256 %s; Last-Modified %s; Content-Length %s" % (
    cl.sha256_bytes(body)[:16], heads.get("last-modified"), len(body))


def current_marker(jur):
  platform = jur.get("platform")
  if platform == "municode":
    return municode_marker(jur)
  if platform == "pdf":
    return pdf_marker(jur)
  if jur.get("marker_url"):
    marker = fetch_direct.fetch_marker(jur, cl.UA_OLD)
    if jur.get("mirror"):
      branch, head = fetch_direct.github_default_branch(jur["mirror"]["repo"])
      marker = "%s | mirror %s@%s" % (marker, branch, (head or {}).get("sha", "")[:12])
    return marker
  return None


def stored_marker(slug, manifest):
  recs = [d for d in manifest["documents"] if d["slug"] == slug]
  if not recs:
    return None, None
  rec = recs[0]
  return rec.get("host_marker"), rec


def compare(jur, stored, rec, now):
  if now is None:
    return "unknown"
  platform = jur.get("platform")
  if platform == "municode":
    return "same" if municode_date_from_label(stored) and municode_date_from_label(stored) in now else "CHANGED"
  if platform == "pdf":
    return "same" if rec and rec["sha256_raw"][:16] in now else "CHANGED"
  base = stored or ""
  return "same" if now.split(" | ")[0] == base or base in now else "CHANGED"


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  observed_in = {}
  if "--observed" in argv:
    with open(argv[argv.index("--observed") + 1], encoding="utf-8") as fh:
      observed_in = {o["slug"]: o["marker"] for o in json.load(fh)}
  manifest = cl.load_manifest()
  out = cl.load_json(OBSERVED_PATH, {})
  rows = []
  for jur in cl.load_targets()["jurisdictions"]:
    stored, rec = stored_marker(jur["slug"], manifest)
    now = observed_in.get(jur["slug"]) or current_marker(jur)
    status = compare(jur, stored, rec, now)
    out[jur["slug"]] = {"checked": datetime.datetime.now().isoformat(timespec="seconds"),
                        "stored": stored, "current": now, "status": status}
    rows.append("%-38s %-8s %s" % (jur["slug"], status, now or "(needs Chrome: browser/markers.js)"))
  cl.save_json(OBSERVED_PATH, out)
  sys.stdout.write("\n".join(rows) + "\n")
  if "--browser" in argv:
    with open(os.path.join(cl.HARVEST_DIR, "browser", "markers.js"), encoding="utf-8") as fh:
      sys.stdout.write("\n" + fh.read())
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
