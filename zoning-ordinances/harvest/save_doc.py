"""Ingest browser payloads from files instead of the localhost sink.

Usage: python3 save_doc.py payload.json [payload.json ...]
Each file holds one ingest payload (see ingest.py), or a JSON list of them.
Same sha256 verification as the sink.
"""

import json
import logging
import sys

import ingest

LOG = logging.getLogger("corpus.save_doc")


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  failed = 0
  for path in argv[1:]:
    with open(path, encoding="utf-8") as fh:
      data = json.load(fh)
    for payload in data if isinstance(data, list) else [data]:
      try:
        ingest.ingest(payload)
      except ingest.IngestError as exc:
        LOG.error("%s", exc)
        failed += 1
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
