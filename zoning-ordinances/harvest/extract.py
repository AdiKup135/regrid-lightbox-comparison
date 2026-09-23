"""Raw file -> ordinance text, per platform, plus section / entry slicing.

The raw file always holds what the host returned (a whole chapter page, a
PDF, or the rendered code-content fragment for client-rendered hosts). The
text file holds only the captured range: whole sections listed in the target
(`sections`), and/or definition entries whose term matches `terms`.

CLI: python3 extract.py [slug ...]   re-extract text from stored raw files.
"""

import html
import logging
import os
import re
import subprocess
import sys

import corpuslib as cl

LOG = logging.getLogger("corpus.extract")

# Content root and chrome to strip, per platform key.
PLATFORMS = {
  "codepublishing": {
    "roots": [{"id": "mainContent"}],
    "drop": [{"cls": "footnote-ref"}, {"id": "navTop"}, {"id": "navBottom"}],
    "toc_in_text": True,
  },
  "ecode360": {
    # one <article> per section; chapter-level history and the New Laws box
    # sit outside the articles and go to the manifest (host_notes) instead.
    "roots": [{"tag": "article"}],
    "drop": [{"cls": "selectionBox"}, {"cls": "notes"}, {"cls": "questions"},
             {"cls": "schemeIcons"}, {"tag": "nav"}, {"tag": "aside"},
             {"cls": "material-icons"}],
    "glue": [{"cls": "litem_number"}, {"cls": "defitem_number"}, {"tag": "dfn"}],
    "meta_roots": [{"id": "newLaws"}, {"cls": "article_content"}],
    # definitions are marked up: <section class="definition"><dfn class="term">
    "entry_node": {"tag": "section", "cls": "definition"},
    "term_node": {"tag": "dfn"},
  },
  "municode": {
    # client-rendered; the raw file is the rendered #codesContent fragment.
    # One div.chunk per node, id "c_<nodeId>"; targets select chunks by
    # node-id prefix ("nodes"), so a whole article/chapter is picked exactly.
    "roots": [{"id": "codesContent"}],
    "drop": [{"cls": "mcc_codes_content_action_bar"}, {"cls": "btn-group"},
             {"cls": "hidden-print"}, {"cls": "sr-only"}, {"cls": "table-toolbar"},
             {"cls": "footnote-content"}, {"cls": "chunk-toolbar"}],
    "glue": [{"cls_prefix": "incr"}],
    "node_select": {"tag": "div", "cls": "chunk", "id_prefix": "c_"},
    "meta_nodes": {"cls": "footnote-content"},
  },
  "amlegal": {
    # client-rendered; raw = rendered .codenav__section-body. #section-0 holds
    # the chapter heading and its list of section titles (page furniture);
    # .code-footer is the publisher's disclaimer.
    "roots": [{"cls": "codenav__section-body"}],
    "drop": [{"id": "section-0"}, {"cls": "code-footer"}, {"cls": "annotation-drawer"},
             {"cls": "sr-only"}, {"tag": "style"}],
  },
  "municipalcodes": {
    # municipal.codes (OpenGov): server-rendered; one <article class="type-Section">
    # per section inside the chapter article (whose "Sections:" list is skipped)
    "roots": [{"tag": "article", "cls": "type-Section"}],
    "drop": [{"tag": "nav"}, {"cls": "noprint"}, {"tag": "button"}, {"cls": "sr-only"},
             {"cls": "track-indicator"}],
  },
  "sanmateo_law": {
    # law.cityofsanmateo.org (Open Law Library): one section per page, text in
    # <article class="content">; history in the page's annotations block.
    "roots": [{"tag": "article", "cls": "content"}],
    "drop": [{"tag": "nav"}, {"cls": "sr-only"}, {"cls": "visually-hidden"}],
  },
  "html": {"roots": [{"tag": "main"}, {"tag": "article"}], "drop": [{"tag": "nav"}]},
}

SEC_NUM = r"(?:§+\s*)?(?:(?:[Ss]ec(?:tion)?|SEC(?:TION)?)\.?\s*)?(\d+[A-Z]?(?:[.\-]\d+[A-Z]?)+(?:\.\d+)?)"
HEADING_RE = re.compile(r"^" + SEC_NUM + r"(?:\s*[.\-–—:]?\s+|\.$)(?=\S)")

DIVISION_RE = re.compile(
  r"^(ARTICLE|Article|CHAPTER|Chapter|PART|Part|DIVISION|Division|TITLE|Title|SUBCHAPTER|Subchapter)"
  r"\s+[\dIVXLC]+[A-Z]?(?:[.\-]\d+[A-Z]?)*\b")
ENUM_RE = re.compile(r"^(\(?\d+[.)]|\(?[a-z]{1,2}[.)]|\(?[ivxl]+[.)]|\([A-Z]\)|[A-Z]\.\s)\s*")
NOT_ENTRY_RE = re.compile(r"^(FIGURE|Figure|TABLE|Table|Note|NOTE|See |\||\()")
ENTRY_RE = re.compile(
  r"^[“\"']?([A-Z][A-Za-z0-9 ,/\-’'()]{1,90}?)[”\"']?"
  r"(?:\s+or\s+[“\"][^”\"]{1,60}[”\"])*"
  r"(?:\s+(?:means|shall mean|is defined|refers to|is|are|encompasses)\b|\.\s|\.$|:\s|:$|\s+—|\s+-\s)")


def _heading_id(line):
  """Section number if the line opens a section. A bare number with a single
  dot ("6.6. Lodging") is an enumerated entry, not a section: without a
  "Sec."/"§" prefix a heading number needs two separators or a hyphen."""
  m = HEADING_RE.match(line)
  if not m:
    return None
  num = m.group(1)
  prefixed = re.match(r"^\s*(§|[Ss]ec|SEC)", line) is not None
  if not prefixed and "-" not in num and num.count(".") < 2:
    return None
  return num


def slice_sections(text, sections, toc_in_text=False):
  """Return the text of each listed section, heading line through the line
  before the next heading that is not this section or one of its
  subsections. toc_in_text (Code Publishing chapter pages): the chapter
  opens with a list of its section headings, so the last match is the
  section itself; elsewhere the first match is, and later lines that start
  with the section number (figure captions) stay inside it."""
  lines = text.splitlines()
  out = []
  missing = []
  for sec in sections:
    starts = [i for i, l in enumerate(lines) if _heading_id(l) == sec]
    if not starts:
      missing.append(sec)
      continue
    start = starts[-1] if toc_in_text else starts[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
      hid = _heading_id(lines[j])
      if (hid and hid != sec and not hid.startswith(sec + ".")) or DIVISION_RE.match(lines[j]):
        end = j
        break
    chunk = "\n".join(lines[start:end]).strip()
    out.append(chunk)
  return out, missing


def slice_lines(text, start_re, end_re):
  lines = text.splitlines()
  for i, line in enumerate(lines):
    if re.search(start_re, line):
      for j in range(i + 1, len(lines)):
        if re.search(end_re, lines[j]):
          return "\n".join(lines[i:j]).strip("\n"), False
      return "\n".join(lines[i:]).strip("\n"), False
  return "", True


def split_by_headings(text, toc_in_text=False):
  """Every section in the text, in document order (see slice_sections for
  toc_in_text)."""
  lines = text.splitlines()
  pos = {}
  for i, line in enumerate(lines):
    hid = _heading_id(line)
    if hid and (toc_in_text or hid not in pos):
      pos[hid] = i
  secs = sorted(pos, key=lambda k: pos[k])
  chunks, _ = slice_sections(text, secs, toc_in_text)
  return chunks


def _paragraphs(text):
  return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _entry_term(par, enum=None):
  """The defined term if this paragraph opens a definition entry, else None.

  enum: regex for the enumerator that numbers top-level entries (e.g.
  r"\\(\\d+\\)\\s*" for Sunnyvale's "(14) "Lot" means"). With enum set, only
  paragraphs carrying it can open an entry; without it, enumerated
  paragraphs are always sub-items of the entry above."""
  if enum:
    m = re.match(enum, par)
    if not m:
      return None
    par = par[m.end():]
  elif ENUM_RE.match(par):
    return None
  if NOT_ENTRY_RE.match(par):
    return None
  m = ENTRY_RE.match(par)
  if not m:
    return None
  return m.group(1).strip().strip("“”\"'").strip()


def slice_entries(text, terms_re, heading=None, enum=None):
  """Definition entries whose term matches terms_re (case-insensitive).

  An entry runs from its opening paragraph through its enumerated
  sub-paragraphs and figure captions, up to the next entry. `heading` is
  kept as the first line so the section number stays with the entries."""
  rx = re.compile(terms_re, re.I)
  pars = _paragraphs(text)
  if heading and pars and _heading_id(heading):
    # one-term-per-section codes: a section titled with a matching term is
    # kept whole ("18.04.560 - Yard, required front.")
    title = HEADING_RE.sub("", heading, count=1).strip(" .-–—:")
    if title and rx.search(title) and not re.match(r"(?i)definitions?\b", title):
      return "\n\n".join(pars), 1
  out = []
  cur = None
  for par in pars:
    if _heading_id(par.splitlines()[0]):
      if cur is not None:
        out.append(cur)
        cur = None
      continue
    term = _entry_term(par, enum)
    if term is not None:
      if cur is not None:
        out.append(cur)
        cur = None
      if rx.search(term):
        cur = [par]
      continue
    if cur is not None:
      cur.append(par)
  if cur is not None:
    out.append(cur)
  body = "\n\n".join("\n\n".join(e) for e in out)
  if heading and body:
    body = heading + "\n\n" + body
  return body, len(out)


def _node_text(node, cfg):
  w = cl._Writer()
  cl._render(node, w, cfg.get("drop", []), cfg.get("glue"))
  return w.result()


def structural_entries(raw_path, platform, terms_re, sections=None, enum=None):
  """Definition entries picked from the host's own markup (one element per
  entry, term in its own element). Each matching entry is rendered whole,
  sub-items included, under the heading of the section it sits in. Sections
  without entry markup fall back to the paragraph heuristic."""
  cfg = PLATFORMS[platform]
  rx = re.compile(terms_re, re.I)
  en, tn = cfg["entry_node"], cfg["term_node"]
  pieces, count = [], 0
  for _url, body in cl.read_parts(raw_path):
    tree = cl.parse_html(body)
    for art in cl.select(tree, tag="article"):
      text = _node_text(art, cfg)
      heading = text.splitlines()[0] if text.strip() else ""
      hid = _heading_id(heading)
      if sections and sections != "*" and hid not in sections:
        continue
      defs = []
      for node in art.iter():
        if node is art or not cl._matches(node, [en]):
          continue
        anc, nested = node.parent, False
        while anc is not None and anc is not art:
          if cl._matches(anc, [en]):
            nested = True
            break
          anc = anc.parent
        if not nested:
          defs.append(node)
      if defs:
        hits = []
        for d in defs:
          terms = [n for n in d.iter() if cl._matches(n, [tn])]
          term = _node_text(terms[0], cfg).strip().strip("“”\"'.").strip() if terms else ""
          if term and rx.search(term):
            hits.append(_node_text(d, cfg).strip())
        if hits:
          count += len(hits)
          pieces.append(heading + "\n\n" + "\n\n".join(hits))
      else:
        body_txt, n = slice_entries(text, terms_re, heading=heading, enum=enum)
        count += n
        if body_txt:
          pieces.append(body_txt)
  return pieces, count


def _selected_nodes(tree, cfg, prefixes):
  sel = cfg["node_select"]
  out = []
  for node in cl.select(tree, tag=sel.get("tag"), cls=sel.get("cls")):
    nid = node.attrs.get("id") or ""
    if not nid.startswith(sel.get("id_prefix", "")):
      continue
    nid = nid[len(sel.get("id_prefix", "")):]
    if any(nid == p or nid.startswith(p + "_") for p in prefixes):
      out.append(node)
  return out


def node_text(raw_path, platform, prefixes):
  """Text of the host's content nodes whose ids start with one of prefixes
  (Municode chunks), in document order."""
  cfg = PLATFORMS[platform]
  texts = []
  seen = set()
  for _url, body in cl.read_parts(raw_path):
    tree = cl.parse_html(body)
    for node in _selected_nodes(tree, cfg, prefixes):
      # several fetched pages can render the same node (one article page per
      # listed division); each node's text is kept once, first copy wins
      nid = node.attrs.get("id")
      if nid in seen:
        continue
      seen.add(nid)
      texts.append(_node_text(node, cfg).strip())
  return "\n\n".join(t for t in texts if t)


def raw_to_text(raw_path, platform):
  if raw_path.endswith(".pdf"):
    return cl.pdf_to_text(raw_path)
  cfg = PLATFORMS.get(platform, PLATFORMS["html"])
  texts = []
  for _url, body in cl.read_parts(raw_path):
    texts.append(cl.html_to_text(body, roots=cfg["roots"], drop=cfg["drop"],
                                 glue=cfg.get("glue")))
  return "\n".join(texts)


def raw_marker(raw_path, platform):
  """The host's change marker as stored in the raw file itself, when the
  host embeds one: eCode360's current version line ("Includes legislation
  through Ord. No. ..."), municipal.codes' "current through Ordinance ...",
  a PDF's own creation/modification dates."""
  if raw_path.endswith(".pdf"):
    res = subprocess.run(["pdfinfo", raw_path], capture_output=True, text=True)
    dates = [l.split(":", 1)[1].strip() for l in res.stdout.splitlines()
             if l.startswith(("CreationDate", "ModDate"))]
    return ("PDF CreationDate %s; ModDate %s" % tuple(dates)) if len(dates) == 2 else None
  with open(raw_path, encoding="utf-8", errors="replace") as fh:
    raw = html.unescape(fh.read())
  if platform == "ecode360":
    for m in re.finditer(r'\{[^{}]*"displayDate":"([^"]+)"[^{}]*\}', raw):
      if '"current":true' in m.group(0):
        return m.group(1)
  if platform == "municipalcodes":
    m = re.search(r"current through Ordinance [^<.]{0,60}\.?", raw)
    if m:
      return m.group(0)
  return None


def stated_enactment(raw_path, platform):
  """Ordinance number and dates where the page states them as structured
  data for the whole document (Open Law Library's chapter <annotation
  type="History" doc=... app=... eff=...>). Section history notes are
  recorded separately (history_notes); nothing is inferred from them."""
  if platform != "sanmateo_law" or raw_path.endswith(".pdf"):
    return {}
  first = cl.read_parts(raw_path)[0][1]
  m = re.search(r"<annotation([^>]*)type=\"History\"[^>]*>", first)
  if not m:
    return {}
  attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))
  return {"ordinance": attrs.get("doc"), "adopted": attrs.get("app"), "effective": attrs.get("eff")}


def host_notes(raw_path, platform, spec=None):
  """Host annotations outside the ordinance text (eCode360 New Laws table,
  chapter-level prior-history notes). Stored in the manifest, never in text."""
  cfg = PLATFORMS.get(platform, {})
  if raw_path.endswith(".pdf"):
    return []
  if cfg.get("meta_nodes") and spec and spec.get("nodes"):
    with open(raw_path, encoding="utf-8", errors="replace") as fh:
      tree = cl.parse_html(fh.read())
    notes = []
    for node in _selected_nodes(tree, cfg, spec["nodes"]):
      for fn in cl.select(node, cls=cfg["meta_nodes"]["cls"]):
        w = cl._Writer()
        cl._render(fn, w, [], None)
        txt = " ".join(l for l in w.result().splitlines() if l.strip())
        if txt and txt not in notes:
          notes.append(txt)
    return notes
  if not cfg.get("meta_roots"):
    return []
  notes = []
  for url, body in cl.read_parts(raw_path):
    tree = cl.parse_html(body)
    for rule in cfg["meta_roots"]:
      for node in cl.select(tree, tag=rule.get("tag"), id_=rule.get("id"), cls=rule.get("cls")):
        w = cl._Writer()
        cl._render(node, w, cfg.get("drop", []))
        txt = " / ".join(l for l in w.result().splitlines() if l.strip())
        if txt and txt not in notes:
          notes.append(("%s: %s" % (url, txt)) if url else txt)
  return notes


def extract(doc_spec, platform, raw_path):
  """Apply a target's doc spec to a raw file. Returns (text, info)."""
  if doc_spec.get("nodes"):
    full = node_text(raw_path, platform, doc_spec["nodes"])
  else:
    full = raw_to_text(raw_path, platform)
  if raw_path.endswith(".pdf") and doc_spec.get("pdf_pages"):
    first, last = doc_spec["pdf_pages"]
    full = cl.pdf_to_text(raw_path, first, last)
  for rx in doc_spec.get("strip_lines", []):
    # page furniture repeated by the PDF (running headers/footers), never text
    full = "\n".join(l for l in full.splitlines() if not re.match(rx, l))
  info = {"missing_sections": [], "entries": 0}
  pieces = []
  toc = PLATFORMS.get(platform, {}).get("toc_in_text", False)
  for sl in doc_spec.get("slices", []):
    # line ranges: from the first line matching `start` up to the line before
    # the next line matching `end` (chapter-level cuts in long PDFs)
    chunk, miss = slice_lines(full, sl["start"], sl["end"])
    if miss:
      info["missing_sections"].append(sl["start"])
    elif sl.get("entries"):
      terms = sl["entries"]["terms"]
      if terms == "LOT_TERMS":
        terms = cl.load_targets()["lot_terms"]
      first = chunk.strip().splitlines()[0].strip()
      body, n = slice_entries(chunk, terms, heading=first, enum=sl["entries"].get("enum"))
      info["entries"] += n
      if body:
        pieces.append(body)
    else:
      pieces.append(chunk)
  if doc_spec.get("sections"):
    chunks, missing = slice_sections(full, doc_spec["sections"], toc)
    pieces.extend(chunks)
    info["missing_sections"] = missing
  for group in doc_spec.get("entries", []):
    terms = group["terms"]
    if terms == "LOT_TERMS":
      terms = cl.load_targets()["lot_terms"]
    wanted = group.get("sections", [group.get("section")])
    if PLATFORMS.get(platform, {}).get("entry_node") and not raw_path.endswith(".pdf"):
      chunks, n = structural_entries(raw_path, platform, terms, wanted, group.get("enum"))
      info["entries"] += n
      pieces.extend(chunks)
      continue
    if wanted == "*":
      chunks = split_by_headings(full, toc)
    else:
      chunks, missing = slice_sections(full, wanted, toc)
      info["missing_sections"].extend(missing)
    for chunk in chunks:
      first_line = chunk.splitlines()[0]
      body, n = slice_entries(chunk, terms, heading=first_line, enum=group.get("enum"))
      info["entries"] += n
      if body:
        pieces.append(body)
  if not doc_spec.get("sections") and not doc_spec.get("entries") and not doc_spec.get("slices"):
    pieces.append(full.strip())
  text = "\n\n".join(p.strip() for p in pieces if p.strip()) + "\n"
  return text, info


def history_notes(text):
  """Codified history notes as printed, e.g. '(Ord. 1234 § 2, 2024)'."""
  pat = re.compile(r"\((?:[^()]|\([^()]*\))*?\b(?:Ord|Ords|Ordinance)\.?\s*(?:No\.?\s*)?[\dA-Z][^()]*?(?:\([^()]*\)[^()]*?)*\)")
  seen = []
  for m in pat.finditer(text):
    note = re.sub(r"\s+", " ", m.group(0))
    if note not in seen and len(note) < 600:
      seen.append(note)
  return seen


def main(argv):
  logging.basicConfig(level=logging.INFO, format="%(message)s")
  import record
  slugs = set(argv[1:])
  targets = cl.load_targets()
  manifest = cl.load_manifest()
  by_id = {d["id"]: d for d in manifest["documents"]}
  for jur in targets["jurisdictions"]:
    if slugs and jur["slug"] not in slugs:
      continue
    for doc, spec in jur["docs"].items():
      rec = by_id.get("%s/%s" % (jur["slug"], doc))
      if not rec or not rec.get("raw_file"):
        continue
      raw_path = os.path.join(cl.CORPUS_DIR, rec["raw_file"])
      record.write_record(jur, doc, spec, raw_path, rec.get("transport"),
                          rec.get("parts"), rec.get("fetched"), rec.get("host_marker"))
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
