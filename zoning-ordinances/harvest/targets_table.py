"""Print the per-jurisdiction source table used in corpus/REFRESH.md.

Usage: python3 targets_table.py > /tmp/table.md
Columns: jurisdiction, host platform, transport, change marker recorded at the
last fetch, and the canonical URL(s) per tier.
"""

import sys

import corpuslib as cl

SHORT = {"adu-ordinance": "ADU", "definitions": "Definitions", "sf-district-standards": "SF standards"}


def main(argv):
  manifest = {d["id"]: d for d in cl.load_manifest()["documents"]}
  rows = ["| Jurisdiction | Platform / transport | Change marker at last fetch | Tier URLs |",
          "|---|---|---|---|"]
  for jur in sorted(cl.load_targets()["jurisdictions"], key=lambda j: j["jurisdiction"]):
    rec = manifest.get("%s/adu-ordinance" % jur["slug"], {})
    urls = []
    for doc, spec in jur["docs"].items():
      links = spec.get("urls") or (spec.get("toc") or {}).get("urls") or []
      urls.append("%s: %s" % (SHORT[doc], " ".join("<%s>" % u for u in links)))
    rows.append("| %s | %s / %s | %s | %s |" % (
      jur["jurisdiction"], jur.get("platform_label"), jur.get("transport"),
      (rec.get("host_marker") or "").replace("|", "/"), "<br>".join(urls)))
  sys.stdout.write("\n".join(rows) + "\n")
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
