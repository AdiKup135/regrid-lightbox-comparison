/**
 * heightExtract.js — derive a display-ready max building height from Zoneomics responses.
 *
 * Sources (pass whichever you have; both is best):
 *   cc  = conditionalControls response: data.controls.max_building_height_ft
 *   zdc = zoneDetail (output_fields=controls&replace_STF=true) response: data.controls  (flat, city-native keys)
 *
 * Returns:
 *   {
 *     ft:        number|null,   // headline: most restrictive GENERAL limit for the primary building
 *     floors:    number|null,   // most restrictive stories cap tied to that limit (2, 2.5, 3), if stated
 *     status:    'ok' | 'review',  // 'review' => show "See code" styling / flag, ft may still be a best guess
 *     detail:    string[],      // everything for the <...> popover, in display order
 *     sourceLink: undefined     // caller attaches zone_details.link
 *   }
 *
 * Design rules derived from an 11-city Bay Area sweep (Aug 2026):
 *  - cc "fixed" numeric agrees with zoneDetail in every observed case -> trust it.
 *  - cc "conditional" rows mix true building limits with wall-plate, accessory,
 *    additions-only, flood, and permit-gated values. Taking min() or worst_case_value
 *    blindly is WRONG (MV worst=15 is a wall plate; Oakland worst=15 is accessory;
 *    Berkeley worst=14 is additions-only). Rows must be filtered by label.
 *  - "For N story structure" rows are alternatives, not stacked restrictions:
 *    the building's ceiling is the value at the HIGHEST story count.
 *  - When labels are uninformative (Oakland: every row "General"), fall back to
 *    parsing the zoneDetail city text for "primary building" clauses; else flag review.
 *  - Stories caps live ONLY in city text ("2 stories", "two stories",
 *    "2 and one half stories", "2.5 stories") or a dedicated *_stories key.
 */

const NUM = /^\d+(?:\.\d+)?$/;

// rows that describe the primary/new building's general limit — the headline scenario
const PREFER = /new\s+building|base\s+height|general\s+height|primary|main\s+building/i;
// rows that are NOT the primary building's overall height limit
const EXCLUDE = /accessor|wall\s*plate|wall\s*height|fence|hedge|daylight|addition|flood|pavement|basement|cellar|steeple|rear\s+main|average|nonresidential|ground\s*floor|lateral\s*slope|measur|combining|overlay/i;
// rows that are only reachable with discretionary approval — not by-right
const PERMIT = /permit|variance|planning\s*commission|design\s*review|exception/i;
// story-alternative rows: "For 1 story structure", "two story dwellings"
const STORY_ROW = /(?:for\s+)?(\d+(?:\.\d+)?|one|two|three|four)\s*(?:-|\s)*stor(?:y|ies)/i;

const WORDS = { one: 1, two: 2, three: 3, four: 4 };

function toNum(v) {
  if (typeof v === 'number' && isFinite(v)) return v;
  if (typeof v !== 'string') return null;
  const s = v.trim().replace(/–|—/g, '-'); // en/em dash
  if (NUM.test(s)) return parseFloat(s);
  const range = s.match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/); // "25-150"
  if (range) return Math.min(parseFloat(range[1]), parseFloat(range[2])); // restrictive end of a max
  return null;
}

function storyCount(text) {
  // "2 and one half stories" / "two and a half stories" / "2.5 stories" / "two stories"
  const m = String(text).match(
    /(\d+(?:\.\d+)?|one|two|three|four)(?:\s+and\s+(?:a|one)\s+half)?\s*(?:-|\s)*stor(?:y|ies)/i
  );
  if (!m) return null;
  let n = NUM.test(m[1]) ? parseFloat(m[1]) : WORDS[m[1].toLowerCase()];
  if (n == null) return null;
  if (/\band\s+(?:a|one)\s+half\b/i.test(m[0])) n += 0.5;
  return n;
}

/** Pick the primary-building height key from flat zoneDetail controls. */
function primaryHeightKey(zdc) {
  const keys = Object.keys(zdc || {});
  const pref = [
    /^max(?:imum)?_(?:main_)?building_height_(?:ft|feet)$/,
    /^maximum_height_limit_(?:ft|feet)$/,
    /building_height/, // last resort, still exclude accessory/fence keys below
  ];
  for (const re of pref) {
    const k = keys.find(k => re.test(k) && !/accessor|fence|stories/i.test(k));
    if (k) return k;
  }
  return null;
}

export function extractHeight(cc, zdc) {
  const detail = [];
  let ft = null;
  let floors = null;
  let status = 'ok';

  const zKey = primaryHeightKey(zdc);
  const zText = zKey ? String(zdc[zKey]) : '';

  // ---------- 1) headline ft from conditionalControls ----------
  if (cc && cc.type === 'fixed') {
    ft = toNum(cc.value); // "NA"/"NULL"/text -> null
  } else if (cc && cc.type === 'conditional' && Array.isArray(cc.conditions)) {
    const rows = cc.conditions
      .map(r => ({ v: toNum(r.value), label: String(r.condition ?? '') }))
      .filter(r => r.v != null);

    const noPermit = rows.filter(r => !PERMIT.test(r.label));
    const byRight = noPermit.filter(r => !EXCLUDE.test(r.label));
    const informative = byRight.filter(r => r.label && !/^general$/i.test(r.label.trim()));

    const storyRows = informative
      .map(r => ({ ...r, n: (r.label.match(STORY_ROW) || [])[1] }))
      .filter(r => r.n != null)
      .map(r => ({ ...r, n: NUM.test(r.n) ? parseFloat(r.n) : WORDS[r.n.toLowerCase()] }));

    // rows naming the primary/new-building general limit outrank blanket exclusions
    // (e.g. Berkeley "New buildings and non residential additions" must survive /addition/)
    const preferred = noPermit.filter(r => PREFER.test(r.label));

    if (storyRows.length) {
      // alternatives by story count: the ceiling is the tallest allowed configuration
      const top = storyRows.reduce((a, b) => (b.n > a.n ? b : a));
      ft = top.v;
      floors = top.n;
    } else if (preferred.length) {
      ft = Math.min(...preferred.map(r => r.v)); // most restrictive primary-building limit
    } else if (informative.length) {
      ft = Math.min(...informative.map(r => r.v)); // most restrictive general limit
    } else if (byRight.length && new Set(byRight.map(r => r.v)).size === 1) {
      ft = byRight[0].v; // all "General" but unanimous
    }
    // permit-gated ceiling goes to detail, never headline
    const gated = rows.filter(r => PERMIT.test(r.label));
    for (const g of gated) detail.push(`Up to ${g.v} ft ${g.label.toLowerCase()}`);
  }
  // cc.type === 'unit_mismatch' or missing -> ft stays null here

  // ---------- 2) fallback / cross-check via zoneDetail city text ----------
  if (ft == null && zText) {
    // "Wall height primary building: 25" style (Oakland) — min over primary-building clauses
    const prim = [...zText.matchAll(/primary building[^:]*:\s*(\d+(?:\.\d+)?)/gi)].map(m => parseFloat(m[1]));
    if (prim.length) ft = Math.min(...prim);
    else {
      // leading number of the city text is the general rule in every observed sample
      const lead = zText.match(/^\s*[^:0-9]*?(\d+(?:\.\d+)?)/);
      if (lead && !EXCLUDE.test(zText.slice(0, zText.indexOf(lead[1])))) ft = parseFloat(lead[1]);
      status = 'review'; // text-derived: show but flag
    }
  }
  if (ft == null) status = 'review';

  // ---------- 3) floors ----------
  if (floors == null) {
    // dedicated stories key wins (e.g. Santa Clara maximum_building_height_stories)
    const sKey = Object.keys(zdc || {}).find(k => /stories/i.test(k));
    if (sKey) floors = storyCount(zdc[sKey]);
    if (floors == null) {
      // first stories mention across primary-building height keys
      // ("30 ft or 2 stories", "28 or two stories") — accessory/fence keys excluded
      for (const [k, v] of Object.entries(zdc || {})) {
        if (!/height/i.test(k) || /accessor|fence|stories/i.test(k)) continue;
        const n = storyCount(v);
        if (n != null) { floors = n; break; }
      }
    }
  }

  // ---------- 4) detail lines for <...> ----------
  if (zdc) {
    for (const [k, v] of Object.entries(zdc)) {
      if (/height|stor|daylight/i.test(k) && String(v) !== 'NA') detail.push(`${k}: ${v}`);
    }
  }
  if (cc?.type === 'conditional') {
    for (const r of cc.conditions || []) detail.push(`${r.condition}: ${r.value}`);
  }

  return { ft, floors, status, detail: [...new Set(detail)] };
}

export default extractHeight;
