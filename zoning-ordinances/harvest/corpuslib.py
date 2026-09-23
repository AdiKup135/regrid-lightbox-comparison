"""Shared helpers for the ADU ordinance corpus: paths, hashing, manifest I/O,
and HTML/PDF -> plain-text extraction.

Text extraction is deterministic from the stored raw file, so any document can
be re-extracted later with `extract.py` without re-fetching.
"""

import datetime
import hashlib
import html
import json
import logging
import os
import re
import subprocess
from html.parser import HTMLParser

LOG = logging.getLogger("corpus")

HARVEST_DIR = os.path.dirname(os.path.abspath(__file__))
ORD_DIR = os.path.dirname(HARVEST_DIR)
CORPUS_DIR = os.path.join(ORD_DIR, "corpus")
MANIFEST_PATH = os.path.join(CORPUS_DIR, "manifest.json")
TARGETS_PATH = os.path.join(HARVEST_DIR, "targets.json")

DOC_TIERS = {
  "adu-ordinance": 1,
  "definitions": 2,
  "sf-district-standards": 3,
}

# Old Chrome UA: Code Publishing 403s current Chrome UAs and 200s this one.
UA_OLD = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
UA_NEW = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

PART_MARK = "<!-- formx-part "


def today():
  return datetime.date.today().isoformat()


def sha256_bytes(data):
  return hashlib.sha256(data).hexdigest()


def sha256_file(path):
  with open(path, "rb") as fh:
    return sha256_bytes(fh.read())


def load_json(path, default):
  if not os.path.exists(path):
    return default
  with open(path, encoding="utf-8") as fh:
    return json.load(fh)


def save_json(path, data):
  tmp = path + ".tmp"
  with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
  os.replace(tmp, path)


def load_targets():
  return load_json(TARGETS_PATH, {"jurisdictions": []})


def load_manifest():
  return load_json(MANIFEST_PATH, {"documents": []})


def upsert_manifest(record):
  manifest = load_manifest()
  docs = [d for d in manifest["documents"] if d["id"] != record["id"]]
  docs.append(record)
  docs.sort(key=lambda d: (d["slug"], DOC_TIERS.get(d["doc"], 9)))
  manifest["documents"] = docs
  manifest["generated"] = today()
  save_json(MANIFEST_PATH, manifest)
  return record


def doc_paths(slug, doc, raw_ext):
  folder = os.path.join(CORPUS_DIR, slug)
  os.makedirs(folder, exist_ok=True)
  raw = os.path.join(folder, "%s.raw.%s" % (doc, raw_ext))
  txt = os.path.join(folder, "%s.txt" % doc)
  return raw, txt


def join_parts(parts):
  """Concatenate several fetched responses into one raw file (bytes).

  parts: [{"url": str, "body": bytes}]. Each part is preceded by a one-line
  marker comment naming its URL, the sha256 of the bytes exactly as received
  and their length; the body follows byte for byte, then one newline that is
  not part of the body. read_parts() splits the file back out exactly.
  """
  out = []
  for part in parts:
    body = part["body"]
    out.append(('%surl="%s" sha256="%s" bytes="%d" -->\n'
                % (PART_MARK, part["url"], sha256_bytes(body), len(body))).encode("utf-8"))
    out.append(body)
    out.append(b"\n")
  return b"".join(out)


def split_parts_bytes(raw):
  """Inverse of join_parts: [(url, bytes)]. A file without part markers is a
  single part with url None."""
  mark = PART_MARK.encode("utf-8")
  if not raw.startswith(mark):
    return [(None, raw)]
  out = []
  pos = 0
  while pos < len(raw):
    end = raw.index(b" -->\n", pos)
    head = raw[pos:end].decode("utf-8")
    url = re.search(r'url="([^"]*)"', head).group(1)
    size = int(re.search(r'bytes="(\d+)"', head).group(1))
    start = end + len(b" -->\n")
    out.append((url, raw[start:start + size]))
    pos = start + size + 1
  return out


def read_parts(path):
  """[(url, text)] for a stored raw HTML file, one entry per fetched part."""
  with open(path, "rb") as fh:
    raw = fh.read()
  return [(url, body.decode("utf-8", "replace")) for url, body in split_parts_bytes(raw)]


# --------------------------------------------------------------------------
# HTML -> text

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "section", "article", "header", "footer", "li", "ul",
         "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "table",
         "tr", "thead", "tbody", "tfoot", "caption", "blockquote", "pre",
         "form", "figure", "figcaption", "main", "aside", "nav", "address",
         "center", "hr", "br"}
SKIP = {"script", "style", "noscript", "template", "svg", "button", "select",
        "option", "iframe", "head", "input", "textarea"}


class Node:
  __slots__ = ("tag", "attrs", "children", "parent")

  def __init__(self, tag, attrs, parent):
    self.tag = tag
    self.attrs = dict(attrs)
    self.children = []
    self.parent = parent

  def classes(self):
    return (self.attrs.get("class") or "").split()

  def iter(self):
    yield self
    for child in self.children:
      if isinstance(child, Node):
        yield from child.iter()


class TreeBuilder(HTMLParser):
  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.root = Node("#root", {}, None)
    self.cur = self.root

  def handle_starttag(self, tag, attrs):
    node = Node(tag, attrs, self.cur)
    self.cur.children.append(node)
    if tag not in VOID:
      self.cur = node

  def handle_startendtag(self, tag, attrs):
    self.cur.children.append(Node(tag, attrs, self.cur))

  def handle_endtag(self, tag):
    node = self.cur
    while node is not None and node.tag != tag:
      node = node.parent
    if node is not None and node.parent is not None:
      self.cur = node.parent

  def handle_data(self, data):
    self.cur.children.append(data)


def parse_html(text):
  builder = TreeBuilder()
  builder.feed(text)
  builder.close()
  return builder.root


def select(root, tag=None, id_=None, cls=None):
  out = []
  for node in root.iter():
    if tag and node.tag != tag:
      continue
    if id_ and node.attrs.get("id") != id_:
      continue
    if cls and cls not in node.classes():
      continue
    out.append(node)
  return out


def _matches(node, rules):
  for rule in rules:
    if rule.get("tag") and node.tag != rule["tag"]:
      continue
    if rule.get("id") and node.attrs.get("id") != rule["id"]:
      continue
    if rule.get("cls") and rule["cls"] not in node.classes():
      continue
    if rule.get("cls_prefix") and not any(c.startswith(rule["cls_prefix"]) for c in node.classes()):
      continue
    if rule.get("attr") and rule["attr"] not in node.attrs:
      continue
    return True
  return False


def _drop(node, drop):
  return node.tag in SKIP or _matches(node, drop)


class _Writer:
  def __init__(self):
    self.lines = []
    self.buf = []
    self.glue = False

  def text(self, s):
    self.buf.append(s)
    if self.glue and s.strip():
      self.glue = False

  def newline(self):
    if self.glue:
      # enumerator waiting for its text: the line continues
      self.buf.append(" ")
      return
    line = re.sub(r"[\s\u00a0\u2000-\u200b\u2028\u2029\u3000\ufeff]+", " ",
                  "".join(self.buf)).strip()
    self.buf = []
    if line:
      self.lines.append(line)
    elif self.lines and self.lines[-1] != "":
      self.lines.append("")

  def result(self):
    self.glue = False
    self.newline()
    out = []
    for line in self.lines:
      if line == "" and (not out or out[-1] == ""):
        continue
      out.append(line)
    while out and out[-1] == "":
      out.pop()
    return "\n".join(out) + "\n"


def _cell_text(node, drop, glue=None):
  w = _Writer()
  _render(node, w, drop, glue)
  lines = [l for l in w.result().splitlines() if l.strip()]
  return " ".join(lines).replace("|", "/")


def _span(cell, name):
  val = (cell.attrs.get(name) or "1").strip()
  return int(val) if val.isdigit() and int(val) > 0 else 1


def _render_table(node, w, drop, glue=None):
  """One line per row, cells joined by ' | '. A cell spanning several rows is
  repeated on each row it covers so every row keeps the table's columns; a
  cell spanning several columns is followed by empty cells."""
  w.newline()
  pending = {}  # column index -> [remaining rows, text]
  for tr in node.iter():
    if tr.tag != "tr":
      continue
    cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ("td", "th")]
    if not cells and not pending:
      continue
    row = []
    col = 0
    queue = list(cells)
    while queue or any(k >= col for k in pending):
      if col in pending:
        left, txt = pending[col]
        row.append(txt)
        if left <= 1:
          del pending[col]
        else:
          pending[col] = [left - 1, txt]
        col += 1
        continue
      if not queue:
        row.append("")
        col += 1
        continue
      cell = queue.pop(0)
      txt = _cell_text(cell, drop, glue)
      rs, cs = _span(cell, "rowspan"), _span(cell, "colspan")
      for k in range(cs):
        row.append(txt if k == 0 else "")
        if rs > 1:
          pending[col] = [rs - 1, txt if k == 0 else ""]
        col += 1
    if any(c.strip() for c in row):
      w.text("| " + " | ".join(row) + " |")
      w.newline()
  w.newline()


def _render(node, w, drop, glue=None):
  for child in node.children:
    if isinstance(child, str):
      w.text(child)
      continue
    if _drop(child, drop):
      continue
    if child.tag == "table":
      caps = [c for c in child.children if isinstance(c, Node) and c.tag == "caption"]
      for cap in caps:
        w.newline()
        _render(cap, w, drop, glue)
        w.newline()
      _render_table(child, w, drop, glue)
      continue
    if child.tag == "br":
      w.newline()
      continue
    if child.tag == "sup":
      # footnote markers and exponents: "19.32^2", never "19.322"
      w.text("^")
      _render(child, w, drop, glue)
      continue
    if glue and _matches(child, glue):
      # an enumerator such as "(a)": keep it on the line of the text it numbers
      w.newline()
      _render(child, w, drop, glue)
      w.glue = True
      continue
    block = child.tag in BLOCK
    if block:
      w.newline()
    _render(child, w, drop, glue)
    if block:
      w.newline()
    elif child.tag in ("td", "th"):
      w.text(" ")


def html_to_text(raw_html, roots=None, drop=None, glue=None):
  """Render HTML to plain text.

  roots: list of selector dicts ({tag,id,cls}); the text of every matching
  node (document order, outermost only) is concatenated. Empty -> whole doc.
  drop: list of selector dicts whose subtrees are removed.
  glue: selectors for enumerator elements whose text joins the next line.
  """
  tree = parse_html(raw_html)
  drop = drop or []
  picked = []
  for rule in roots or []:
    hits = select(tree, tag=rule.get("tag"), id_=rule.get("id"), cls=rule.get("cls"))
    if hits:
      picked = hits
      break
  if not picked:
    picked = [tree]
  # keep outermost only
  chosen = []
  ids = set()
  for node in picked:
    anc = node.parent
    nested = False
    while anc is not None:
      if id(anc) in ids:
        nested = True
        break
      anc = anc.parent
    if not nested:
      chosen.append(node)
      ids.add(id(node))
  w = _Writer()
  for node in chosen:
    w.newline()
    _render(node, w, drop, glue)
    w.newline()
  return html.unescape(w.result())


def pdf_to_text(pdf_path, first=None, last=None):
  cmd = ["pdftotext", "-layout", "-enc", "UTF-8"]
  if first:
    cmd += ["-f", str(first)]
  if last:
    cmd += ["-l", str(last)]
  cmd += [pdf_path, "-"]
  res = subprocess.run(cmd, capture_output=True, check=True)
  text = res.stdout.decode("utf-8", "replace").replace("\f", "\n")
  lines = [l.rstrip() for l in text.splitlines()]
  out = []
  for line in lines:
    if line == "" and out and out[-1] == "":
      continue
    out.append(line)
  return "\n".join(out).strip() + "\n"


def curl(url, dest, ua=UA_OLD, timeout=60):
  """Fetch url to dest with curl. Returns (http_code, final_url)."""
  cmd = ["curl", "-sS", "-L", "--compressed", "--max-time", str(timeout),
         "-A", ua, "-o", dest, "-w", "%{http_code} %{url_effective}", url]
  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    return 0, res.stderr.strip()
  code, _, final = res.stdout.strip().partition(" ")
  return int(code or 0), final
