"""Add or replace a Municode jurisdiction in targets.json.

Usage: python3 addmuni.py spec.json   where spec.json holds
  {"jurisdiction","slug","code_name","base": "<.../codes/<code>?nodeId=>",
   "docs": {"adu-ordinance": {"nodes": [...], "section_range": "..."}, ...},
   optional "host_marker", "notes"}
Every node listed becomes one fetched page (url) and one selection prefix.
"""

import json
import sys

import corpuslib as cl


def main(argv):
  with open(argv[1], encoding="utf-8") as fh:
    spec = json.load(fh)
  targets = cl.load_targets()
  items = spec if isinstance(spec, list) else [spec]
  for s in items:
    base = s.pop("base")
    host = base.split("//", 1)[1].split("/codes/")[0]
    for doc in s["docs"].values():
      doc.setdefault("urls", [base + n for n in doc["nodes"]])
      doc.setdefault("raw_kind", "rendered_dom_fragment")
      if doc.pop("defs", False):
        doc["entries"] = [{"sections": "*", "terms": "LOT_TERMS"}]
    s.update({"platform": "municode", "platform_label": "Municode (CivicPlus)",
              "host": host, "transport": "chrome"})
    targets["jurisdictions"] = [j for j in targets["jurisdictions"] if j["slug"] != s["slug"]] + [s]
  cl.save_json(cl.TARGETS_PATH, targets)
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
