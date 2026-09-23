# Harvest scripts and per-host notes

## Scripts

| Script | Role |
|---|---|
| `targets.json` | Every document: URLs, platform, transport, and which sections, nodes, slices or definition entries to keep. The `lot_terms` regex selects tier-2 entries |
| `corpuslib.py` | Paths, hashing, manifest I/O, the multi-part raw container, HTML-to-text, PDF-to-text, curl |
| `extract.py` | Raw to text per platform (`PLATFORMS`), section, node, line and entry slicing, host markers and notes. `python3 extract.py [slug …]` re-extracts from stored raw files |
| `record.py` | Writes a text file and its manifest record |
| `fetch_direct.py` | Curl fetcher for transport `direct`, including contents-page expansion, the GitHub mirror, and marker pages |
| `sink.py` | Localhost receiver on port 8770 for Chrome captures. `/save` accepts payloads and `/wait?ms=N` provides an unthrottled pause |
| `ingest.py` | Verifies each part's sha256 against the browser's hash, stores the raw file, extracts. Used by `sink.py` and `save_doc.py` |
| `save_doc.py` | Ingests payload files when the page cannot reach the receiver |
| `browser/grab.js` | Page-side capture helper. `grab.min.js` is the same code on one line for pasting |
| `browser/markers.js` | Page-side change-marker reader for Chrome-only hosts |
| `check_markers.py` | Compares current host markers with the manifest, without fetching documents |
| `verify.py` | Integrity plus determinism check over all 84 documents |
| `addmuni.py`, `targets_table.py` | Build a Municode target entry, and print REFRESH.md's source table |

## Hosts

| Host | Jurisdictions | Transport | Notes |
|---|---|---|---|
| Municode (`library.municode.com`) | Lafayette, Moraga, Orinda, Hillsborough, Portola Valley, Los Altos, Mountain View, Saratoga, San Jose, Windsor, and Contra Costa, Marin, Napa, Santa Clara and Sonoma counties | Chrome, rendered `#codesContent` | See the Municode notes below |
| eCode360 (`ecode360.com`) | Sunnyvale, Mill Valley, Sausalito, Napa, Menlo Park, Los Altos Hills, Healdsburg | Chrome, same-origin fetch of the exact bytes | See the eCode360 notes below |
| American Legal (`codelibrary.amlegal.com`) | Fairfax, Palo Alto | Chrome, rendered `.codenav__section-body` | See the American Legal notes below |
| municipal.codes (`atherton.municipal.codes`) | Atherton | Chrome, same-origin fetch | See the municipal.codes notes below |
| Code Publishing (`codepublishing.com`) | San Carlos | curl with the old Chrome 91 UA | A current Chrome UA gets 403. Chapter pages open with the chapter's section list, so section slicing takes the last heading match. The marker is on the code home page |
| Open Law Library (`law.cityofsanmateo.org`) | San Mateo | curl from the GitHub bulk mirror `cityofsanmateo/law-html`, default branch | The home page asks visitors not to scrape and points to the bulk download. Mirror files are byte-identical to the live pages. There is one section per page, and each chapter's contents page is kept as part 1 for the chapter heading and history tag |
| County PDF (`smcgov.org`) | San Mateo County | curl | Title 8 Zoning & Development Regulations is one 1,075-page PDF, not yet on Municode. Chapter slices are regexes on "CHAPTER 8.nnn –" and the running footer is stripped |

**Municode:**

- Its `/api/` endpoints return 401 without an in-page token and the site
  loads reCAPTCHA, so they are not used.
- Loading an article or division node renders the whole containing
  document. A chapter that has children renders as a "Mini TOC" instead;
  `gotoNode` refuses those, so list the child nodes.
- Some codes put every definition on its own page (Saratoga, Napa County).
  List those section nodes.
- Text selection is by node-id prefix on the `div.chunk` elements.
  Footnote blocks go to `host_notes`, and duplicate chunks across parts are
  kept once.
- The open `localapi/PublicationVersion` endpoint gives the supplement for
  marker checks.

**eCode360:**

- Plain curl, WebFetch and headless browsers get 403.
- A section node's URL returns its whole chapter.
- The text is one `<article>` per section. The chapter-level "Prior
  History" and the "New Laws" box sit outside the articles and go to
  `host_notes`.
- Definitions are structural markup (`section.definition` and `dfn`) and
  are selected by term.
- Bursts get HTTP 429, so pause between runs.
- The marker is the version JSON's "Includes legislation through …" line.

**American Legal:**

- `fetch()` returns 403 even in Chrome.
- The first section box holds the chapter heading and its section list, so
  it is dropped. The disclaimer footer is dropped too.
- Sections lazy-load as the section body scrolls; `grabAm` scrolls until
  every listed section has rendered.
- It needs both local-network and loopback permissions in Chrome.
- The marker is the version dropdown label.

**municipal.codes:**

- Plain curl gets 403 and bursts get Cloudflare 429.
- There is one `article.type-Section` per section, and the "included in
  your selections" label is dropped.
- The marker is "current through Ordinance N, passed <date>." on every page.

## Resolved sources that differ from the old links

These were checked on 2026-09-23.

- **Menlo Park** moved from Code Publishing to eCode360. The
  `codepublishing.com/CA/MenloPark` URL now returns a General Code error
  page.
- **Moraga's** codified code is on Municode as the "Municipal Code". ADU is
  Ch. 8.124 and definitions are Ch. 8.04.
- **Windsor's** codified ADU and JADU chapters are Title XVII, Ch. 17.82
  and 17.84, on Municode.
- **Healdsburg's** Ch. 20.20 is eCode360 node 48343647, and § 20.20.010
  (ADU/JADU) is node 48343667. Node 48343724 renders the same chapter page.
- **San Mateo County's** zoning is Title 8, adopted Oct. 8, 2024 to replace
  Division VI. It is a county-published PDF (media 159094). The older link,
  media 137136, is a 13-page extract of Ch. 8.392.
- **Zoneomics links.** 13 of the 28 `ordinance_link` values in
  `zoning_ordinance_links.json` point at the Zoneomics code viewer, not 12.
  All 13 now resolve to the canonical host above.
