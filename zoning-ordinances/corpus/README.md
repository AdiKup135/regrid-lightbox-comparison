# ADU ordinance corpus

Verbatim codified text for the 28 FormX jurisdictions: 23 cities and 5
unincorporated counties. It is the local half of the setback engine's two
sources of truth. The other half is state ADU law (Gov. Code §§ 66310–66342)
read with the HCD ADU Handbook, March 2026, which is at
`../origin/HCD/HCD-adu-handbook-032026.pdf`.

Every document comes from the jurisdiction's own code host: Municode,
eCode360, Code Publishing, American Legal, municipal.codes, Open Law Library,
or a county-published PDF. Nothing here comes from Zoneomics, HCD review
letters, handouts or staff reports. A published, codified ordinance is
treated as in effect. Adopted-but-uncodified amendments are noted in the
manifest and never mixed into the text.

Built 2026-09-23. See `REFRESH.md` for when and how to update it.

## Layout

```
corpus/
  README.md               this file
  REFRESH.md              when and how to re-check and re-fetch
  manifest.json           one record per document (84 = 28 jurisdictions x 3)
  markers-observed.json   latest change-marker check (harvest/check_markers.py)
  <slug>/
    adu-ordinance.raw.html|pdf           tier 1: whole ADU/JADU chapter or section
    adu-ordinance.txt
    definitions.raw.html|pdf             tier 2: lot-line / corner / through lot /
    definitions.txt                        frontage / yard / setback definitions
    sf-district-standards.raw.html|pdf   tier 3: single-family district standards
    sf-district-standards.txt
```

The three San Mateo County raw files are the same PDF, hard-linked, and
git stores it once. Tier 1 covers the whole ADU and JADU chapter, or the
whole section where a city puts ADUs inside a larger chapter; the
manifest's `section_range` says which. Tier 3 covers only single-family and
estate districts. Where a code sets those standards by topic rather than by
district, as Sunnyvale, Hillsborough and Portola Valley do, tier 3 is the
topic chapters, again per `section_range`.

## Raw files

Each raw file is what the host returned, never re-serialised.

- **`server_html` or `pdf`.** These are the exact response bytes, fetched by
  curl or by a same-origin `fetch()` inside Chrome. That covers eCode360,
  municipal.codes, Code Publishing, San Mateo, and the county PDF.
- **`rendered_dom_fragment`.** Municode and American Legal build the page in
  the browser. For those two the raw file is the `outerHTML` of the rendered
  code container: `#codesContent` on Municode and `.codenav__section-body`
  on American Legal. It is captured after the page stops changing, and on
  American Legal after every lazy-loaded section has rendered.
- **Several fetched pages in one document.** They are concatenated with a
  marker line before each part:
  `<!-- formx-part url="…" sha256="…" bytes="N" -->`. The body follows byte
  for byte, then one newline. `corpuslib.split_parts_bytes()` recovers each
  part exactly, and `verify.py` re-hashes every part.

## Text files

A text file holds the ordinance's words only. The Python extractor produces
it from the raw file, and the same raw file always produces the same text;
`verify.py` checks this for all 84 documents. The extractor applies these
rules:

- **Kept:** section headings with their numbers, every subsection, every
  table, and the codified history notes the host prints with a section,
  such as "(Ord. 1615 § 4 (Exh. A), 2024)". Editor's notes printed inside a
  section are kept too.
- **Removed:** site navigation, tables of contents, toolbars, disclaimers,
  and repeated PDF page footers.
- **Moved to the manifest:** host annotations, in `host_notes`. These are
  eCode360's "New Laws" and chapter "Prior History" boxes and Municode's
  footnote blocks.
- **Tables:** each row is one line of `| cell | cell |`. A cell spanning
  several rows is repeated on every row it covers, so each row keeps its
  columns. A cell spanning several columns is followed by empty cells.
- **Superscripts** become `^x`, as in `Chapter 19.32^2`, so a footnote mark
  never fuses with a number.
- **Figures** appear by caption only. The images are not stored.
- **Whitespace** is collapsed and HTML entities are decoded. No words are
  added, removed or paraphrased.
- **Definitions (tier 2)** keep the entries whose term matches the lot-term
  list in `harvest/targets.json` (`lot_terms`). Each entry keeps all its
  sub-items and sits under its section heading. Where a code puts one term
  per section, a section whose title matches is kept whole. The raw file
  always has the whole definitions chapter, so the term list can be widened
  and the text re-extracted without fetching again.

## Manifest fields

| Field | Meaning |
|---|---|
| `id`, `slug`, `doc`, `tier` | Document identity, such as `napa/adu-ordinance`, tier 1 |
| `status` | `captured`, which applies to all 84 |
| `code_name`, `platform`, `host` | Which code and which host |
| `transport` | How the bytes were obtained: `direct-curl (…)`, `chrome-same-origin-fetch`, or `chrome-rendered-dom` |
| `source_url`, `source_urls` | Every page fetched for the document |
| `contents_pages` | For hosts with one section per page, the chapter contents page the section list was read from |
| `fetched` | Date fetched |
| `raw_file`, `raw_kind`, `sha256_raw`, `bytes_raw` | The stored raw file |
| `parts` | Each fetched page: `url`, `http`, `sha256` and `bytes` as received. Browser parts also carry `browser_sha256_verified: true`, meaning Chrome's in-page hash matched on receipt |
| `text_file`, `sha256_text`, `chars_text` | The extracted text |
| `section_range` | The captured range, in words |
| `sections_captured`, `missing_sections` | What the extractor was asked to keep, and anything not found, which is empty everywhere |
| `definition_entries` | Number of definition entries kept, for tier 2 |
| `history_notes` | Codified history notes found in the text, verbatim. This is where the ordinance numbers and dates the page states live |
| `ordinance`, `adopted`, `effective` | Set only where the host states them as structured data for the whole document. Today that is only San Mateo's chapter history tag. Nothing is inferred |
| `host_marker` | The host's own change marker when fetched: Municode "VERSION: <date> (CURRENT)", eCode360 "Includes legislation through …", Code Publishing or municipal.codes "current through Ordinance N, passed <date>", American Legal "Supp. No. N" or "S-N (current)", Open Law Library "Current through <date> …", or the PDF's own dates |
| `host_notes` | Host annotations kept out of the text: eCode360 New Laws table and Prior History, Municode footnotes |
| `mirror_head` | San Mateo only: the GitHub bulk-download branch and commit fetched |
| `notes` | Anything else a reader needs, such as an adopted-but-uncodified amendment |

## Reading it

```bash
grep -il "street side" */adu-ordinance.txt
python3 -c "import json; [print(d['id'], d['host_marker']) for d in json.load(open('manifest.json'))['documents'] if d['doc']=='adu-ordinance']"
```

The scripts are in `../harvest/`; `../harvest/HOSTS.md` describes each host.
