"""Integrity and determinism check over the whole corpus.

Usage: python3 verify.py

For every manifest record:
  - raw and text files exist and match sha256_raw / sha256_text
  - each fetched part's bytes (split back out of a multi-part raw file)
    match the sha256 recorded when it was received
  - re-extracting the raw file now yields exactly the stored text
  - the text holds no known site-interface strings
Exit status 1 if anything fails.
"""

import logging
import os
import re
import sys

import corpuslib as cl
import extract

LOG = logging.getLogger("corpus.verify")

# strings that only ever come from a code host's interface, never an ordinance
UI_STRINGS = re.compile(
  r"share link|print section|download \(docx\)|email section|compare versions|"
  r"hosted by|disclaimer:|mini toc|skip to|help_center|select this content|"
  r"get updates|arrow_back|included in your selections|american legal publishing",
  re.I)


def check(rec, targets):
  problems = []
  raw_path = os.path.join(cl.CORPUS_DIR, rec["raw_file"])
  txt_path = os.path.join(cl.CORPUS_DIR, rec["text_file"])
  if not os.path.exists(raw_path) or not os.path.exists(txt_path):
    return ["missing file"]
  if cl.sha256_file(raw_path) != rec["sha256_raw"]:
    problems.append("raw sha256 differs from manifest")
  with open(txt_path, "rb") as fh:
    text_bytes = fh.read()
  if cl.sha256_bytes(text_bytes) != rec["sha256_text"]:
    problems.append("text sha256 differs from manifest")
  parts = rec.get("parts") or []
  if len(parts) == 1 and parts[0].get("sha256") != rec["sha256_raw"]:
    problems.append("single part sha256 differs from raw file")
  elif len(parts) > 1 and not raw_path.endswith(".pdf"):
    with open(raw_path, "rb") as fh:
      split = cl.split_parts_bytes(fh.read())
    if len(split) != len(parts):
      problems.append("raw holds %d parts, manifest lists %d" % (len(split), len(parts)))
    else:
      for (_url, body), part in zip(split, parts):
        if cl.sha256_bytes(body) != part["sha256"]:
          problems.append("part sha256 differs: %s" % part["url"])
  jur = next((j for j in targets["jurisdictions"] if j["slug"] == rec["slug"]), None)
  if jur is None:
    problems.append("no target")
  else:
    spec = jur["docs"][rec["doc"]]
    text, _ = extract.extract(spec, spec.get("platform", jur.get("platform")), raw_path)
    if text.encode("utf-8") != text_bytes:
      problems.append("re-extraction differs from stored text")
  hit = UI_STRINGS.search(text_bytes.decode("utf-8", "replace"))
  if hit:
    problems.append("interface text in document: %r" % hit.group(0))
  if rec.get("missing_sections"):
    problems.append("sections not found: %s" % rec["missing_sections"])
  return problems


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  targets = cl.load_targets()
  manifest = cl.load_manifest()
  bad = 0
  for rec in manifest["documents"]:
    problems = check(rec, targets)
    if problems:
      bad += 1
      LOG.error("%s: %s", rec["id"], "; ".join(problems))
  LOG.info("%d documents checked, %d with problems", len(manifest["documents"]), bad)
  return 1 if bad else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
