"""Turn a stored raw file into its text file and manifest record."""

import logging
import os

import corpuslib as cl
import extract

LOG = logging.getLogger("corpus.record")


def write_record(jur, doc, spec, raw_path, transport, parts=None, fetched=None,
                 host_marker=None):
  platform = spec.get("platform", jur.get("platform"))
  text, info = extract.extract(spec, platform, raw_path)
  _raw, txt_path = cl.doc_paths(jur["slug"], doc, raw_path.rsplit(".", 1)[-1])
  with open(txt_path, "w", encoding="utf-8") as fh:
    fh.write(text)
  with open(raw_path, "rb") as fh:
    raw_bytes = fh.read()
  enact = extract.stated_enactment(raw_path, platform)
  captured = list(spec.get("sections", [])) + [
    "%s (entries matching %s)" % (g.get("section") or g.get("sections"), g["terms"])
    for g in spec.get("entries", [])]
  rec = {
    "id": "%s/%s" % (jur["slug"], doc),
    "jurisdiction": jur["jurisdiction"],
    "slug": jur["slug"],
    "doc": doc,
    "tier": cl.DOC_TIERS[doc],
    "status": spec.get("status", "captured"),
    "code_name": jur.get("code_name"),
    "platform": spec.get("platform_label", jur.get("platform_label")),
    "host": spec.get("host", jur.get("host")),
    "transport": transport,
    "source_url": (spec.get("urls") or [p["url"] for p in parts or []] or [None])[0],
    "source_urls": spec.get("urls") or [p["url"] for p in parts or []],
    "fetched": fetched or cl.today(),
    "raw_file": os.path.relpath(raw_path, cl.CORPUS_DIR),
    "raw_kind": spec.get("raw_kind", "pdf" if raw_path.endswith(".pdf") else "server_html"),
    "sha256_raw": cl.sha256_bytes(raw_bytes),
    "bytes_raw": len(raw_bytes),
    "text_file": os.path.relpath(txt_path, cl.CORPUS_DIR),
    "sha256_text": cl.sha256_bytes(text.encode("utf-8")),
    "chars_text": len(text),
    "sections_captured": captured,
    "section_range": spec.get("section_range"),
    "contents_pages": (spec.get("toc") or {}).get("urls"),
    "missing_sections": info["missing_sections"],
    "definition_entries": info["entries"] if spec.get("entries") else None,
    "history_notes": extract.history_notes(text),
    "ordinance": spec.get("ordinance") or enact.get("ordinance"),
    "adopted": spec.get("adopted") or enact.get("adopted"),
    "effective": spec.get("effective") or enact.get("effective"),
    "host_marker": (host_marker or extract.raw_marker(raw_path, platform)
                    or spec.get("host_marker", jur.get("host_marker"))),
    "host_notes": extract.host_notes(raw_path, platform, spec),
    "parts": parts,
    "mirror_head": jur.get("mirror_head"),
    "notes": spec.get("notes") or jur.get("notes"),
  }
  if info["missing_sections"]:
    LOG.warning("%s: sections not found in raw: %s", rec["id"], info["missing_sections"])
  cl.upsert_manifest(rec)
  return rec
