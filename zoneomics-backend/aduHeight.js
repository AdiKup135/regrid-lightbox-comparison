/**
 * aduHeight.js — ADU branch of the height decision tree (detached ADUs only;
 * attached ADUs are not supported by the software).
 *
 * Steps:
 *   1. State floor S = 16 ft (Gov. Code §66321). The 18 ft near-major-transit
 *      floor is not wired to a transit check yet — see step 3.
 *   2. Local limit L: scan zoneDetail flat controls (replace_STF=true) for
 *      ADU / accessory-height keys; fall back to an "Accessory structures: N"
 *      clause embedded in the main building-height text.
 *   3. ft = max(L, S) — the state floor preempts a lower local cap.
 *      The transit comment ("may be 18 ft near major transit") is added ONLY
 *      when ft < 18: if the local code already allows 18+ the transit floor
 *      can never change the answer, so the note would be noise.
 *
 * Returns { ft, floors, status: 'ok'|'review', detail: string[] }
 *   - floors comes from the local text only when L governs (L >= S); a story
 *     cap attached to a preempted local limit is preempted with it.
 *   - status 'review' when no local key exists (most cities keep ADU rules in
 *     a separate ordinance chapter Zoneomics doesn't return).
 */

const STATE_FLOOR_FT = 16;
const TRANSIT_FLOOR_FT = 18;

const ADU_KEY = /adu|junior/i;
const ACCESSORY_HEIGHT_KEY = /accessor\w*.*height|height.*accessor\w*/i;
const ACCESSORY_REQ_KEY = /accessor\w*.*requirement/i;
const MAIN_HEIGHT_KEY = /^max(?:imum)?_(?:main_)?building_height_(?:ft|feet)$/;

const WORDS = { one: 1, two: 2, three: 3, four: 4 };

function storyCount(text) {
  const m = String(text).match(
    /(\d+(?:\.\d+)?|one|two|three|four)(?:\s+and\s+(?:a|one)\s+half)?\s*(?:-|\s)*stor(?:y|ies)/i
  );
  if (!m) return null;
  let n = /^\d/.test(m[1]) ? parseFloat(m[1]) : WORDS[m[1].toLowerCase()];
  if (n != null && /\band\s+(?:a|one)\s+half\b/i.test(m[0])) n += 0.5;
  return n ?? null;
}

/** Max height allowance found in a local ADU/accessory text value. */
function localFt(text) {
  const s = String(text);
  if (!s || s === 'NA' || s === 'NULL' || s === 'STF') return null;
  const hits = [];
  // "28 feet", "12 ft"
  for (const m of s.matchAll(/(\d+(?:\.\d+)?)\s*(?:feet|ft|foot)\b/gi)) hits.push(parseFloat(m[1]));
  // "shall be 16 feet" already caught; "Accessory structures: 15" style
  for (const m of s.matchAll(/accessor\w*[^:]{0,30}:\s*(\d+(?:\.\d+)?)\b/gi)) hits.push(parseFloat(m[1]));
  // bare "height ...: N"
  for (const m of s.matchAll(/height[^:]{0,40}:\s*(\d+(?:\.\d+)?)\b/gi)) hits.push(parseFloat(m[1]));
  const plausible = hits.filter(n => n >= 8 && n <= 45); // drop story counts, angles, separations
  return plausible.length ? Math.max(...plausible) : null; // the local *allowance* (best local case)
}

export function aduHeight(zdcFlat) {
  const detail = [];
  const zdc = zdcFlat || {};

  // ---- step 1: state floor ----
  const S = STATE_FLOOR_FT;

  // ---- step 2: local limit L ----
  let L = null;
  let lKey = null;
  let lText = null;
  const keys = Object.keys(zdc);
  const pick = (re) => keys.find(k => re.test(k) && localFt(zdc[k]) != null);
  lKey = pick(ADU_KEY) || pick(ACCESSORY_HEIGHT_KEY) || pick(ACCESSORY_REQ_KEY) || null;
  if (lKey) {
    lText = String(zdc[lKey]);
    L = localFt(lText);
  } else {
    // embedded "Accessory structures: 15" inside the main building-height text
    const mainKey = keys.find(k => MAIN_HEIGHT_KEY.test(k));
    const m = mainKey && String(zdc[mainKey]).match(/accessor\w*[^:]{0,30}:\s*(\d+(?:\.\d+)?)\b/i);
    if (m) { L = parseFloat(m[1]); lKey = mainKey; lText = m[0]; }
  }

  // ---- step 3: resolve ----
  const ft = L != null ? Math.max(L, S) : S;
  const status = L != null ? 'ok' : 'review';

  let floors = null;
  if (L != null && L >= S) floors = storyCount(lText); // story cap only survives if local governs

  if (L != null) {
    detail.push(`local: ${lKey} = "${lText.slice(0, 160)}"`);
    if (L < S) detail.push(`local ${L} ft preempted by state floor ${S} ft (Gov. Code §66321)`);
  } else {
    detail.push(`no local ADU/accessory height in base-district controls — check the city's ADU ordinance chapter`);
    detail.push(`showing state floor ${S} ft (Gov. Code §66321)`);
  }
  // transit note only when it could still change the answer
  if (ft < TRANSIT_FLOOR_FT) {
    detail.push(`may be ${TRANSIT_FLOOR_FT} ft within ½-mile walk of major transit — transit check not wired yet`);
  }

  return { ft, floors, status, detail };
}

export default aduHeight;
