"""Phase B — per-jurisdiction decision trees for the > 800 sf detached ADU (local track, §66314).

Curates the research extract in adu_over800_survey.json (2026-10-07, cited + quoted, 28 jurisdictions)
into one engine-shaped record per jurisdiction, then renders every record through ONE tree skeleton:

  entry → G1 size cap → G2 height (+ height-conditioned setbacks) → G3 edge setbacks (clamped per
  provision) → G4 siting + separation → G5 area budget → G6 other binding axes → local-track envelope

  python3 make_local_track_trees.py        (from zoning-ordinances/)

Writes, next to this script:
  adu_local_track_model.json     the curated model (what the engine would load; NOT yet verified as engine data)
  adu-local-track-trees.html     the page: overview matrix + one SVG tree per jurisdiction (#<slug>, #all for print)

Engine conventions applied (see memory: setback-engine-decisions, adu-front-setback-800sf-rule,
corner-lot-street-side-taxonomy):
  * state law prevails per provision: side/rear ≤ 4 ft, height ≥ 16 ft (18 near transit), size ≥ 850 / 1,000 sf
  * the §66321(b)(3) 800 sf shield does not reach a > 800 sf unit, so the local front setback binds in full
  * a street_side edge is a side (4 ft cap) unless the jurisdiction's front rule is all_fronts
    (Hillsborough, Sunnyvale, Contra Costa County), where the second frontage gets front rules
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_OUT = os.path.join(HERE, 'adu_local_track_model.json')
PAGE_OUT = os.path.join(HERE, 'adu-local-track-trees.html')

# Status vocabulary (drives the matrix chips and the node colours):
#   fixed        numeric, computable from inputs the engine already has (edges, zone, unit_size, height, transit)
#   district     needs the parcel's zone code → district table (front: residential_front_setback.by_district)
#   input        needs a NEW input (bedrooms, lot_area, stories, primary floor area, existing floor area / coverage)
#   conditioned  height- or story-conditioned setback → a branch, not a number
#   clamp        local text exceeds what state law allows → engine clamps + flags
#   ambiguous    text unclear → engine default + flag
#   gap          corpus gap / unsourced
#   none         nothing binds at this gate
#   permissive   local text is more generous than the state floor → honour it

J = []


def add(**k):
  J.append(k)


add(slug='atherton', name='Atherton', county='San Mateo',
    regime='Two tracks in 17.52.040(B)(2): (a) ≤ 800 sf state-type unit; (b) > 800 sf takes the accessory-building setbacks of Ch. 17.40 (not in corpus), interior-facing entrances, tree / privacy / screening rules.',
    cap=dict(model='flat', value='1,200 sf flat', detail='no bedroom or lot-size tiers', inputs=['unit_size'], cite='17.52.040(C)(3)', status='fixed'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · 25 ft above a garage · 2 stories', conditioned='25 ft above a garage only if the whole garage + stairwell meet the Ch. 17.40 accessory setbacks', inputs=['unit_height_in_feet', 'transit'], cite='17.52.040(H)(1)-(6)', status='conditioned'),
    front=dict(kind='gap', value='Ch. 17.40 accessory-building front setback — chapter not in corpus (R-1A main-building front is 60 ft)', cite='17.52.040(F)(4); 17.32.040(D)(1)', status='gap'),
    side_rear=dict(value='4 ft (clamp)', local_text='accessory-building setbacks of Ch. 17.40.040(A), not in corpus; anything above 4 ft conflicts with §66314', cite='17.52.040(F)(4)', status='gap'),
    street_side=dict(local_text='silent; corner lots only get a front / rear designation', engine='side → 4 ft', cite='17.52.040(F)(8)', status='fixed'),
    siting=dict(rules=['entrances must face the interior of the lot'], separation='defers to the accessory-structures section (not in corpus)', cite='17.52.040(G), (F)(5)', status='gap'),
    budget=dict(applies=True, summary='area above 800 sf counts toward the R-1A max floor area (18 % of lot) unless the unit meets the Ch. 17.40 setbacks, then the exemption runs to 1,200 sf; no lot-coverage rule', inputs=['lot_area', 'existing_floor_area'], cite='17.52.040(D)(1)-(2); 17.32.040(C)', status='input'),
    overlays=['Heritage Tree Ordinance', 'privacy glazing above the ground floor', 'landscape screening, 8 ft fence rules', 'shielded lighting'],
    conflicts=['side / rear may exceed 4 ft via Ch. 17.40 → clamp to 4 ft + flag'],
    gaps=['Ch. 17.40 (accessory-building setbacks + separation) missing from corpus'])

add(slug='contra-costa-county', name='Contra Costa County', county='Contra Costa',
    regime='Clean two-track chapter: ≤ 800 sf is exempt from all of 82-24.012; > 800 sf keeps 4 ft side / rear but takes the district front setback and district height — unless any part sits inside a required district yard, then state heights.',
    cap=dict(model='lot_size', value='1,000 sf · 1,200 sf on a lot ≥ 12,000 sf or in an agricultural district', detail='Kensington (-K): 850 sf one bedroom / 1,000 sf more', inputs=['unit_size', 'lot_area', 'zone', 'bedrooms (-K only)'], cite='82-24.012(a)(1)', status='input'),
    height=dict(max='district (R-6: 35 ft / 2.5 stories) when wholly outside the required yards · state 16 / 18 ft when any part is inside a required front, side or rear yard, or in Kensington', conditioned='a unit at 4 ft side / rear sits inside the 5–15 ft district yards → capped at 16 / 18 ft; to use 35 ft it must clear every required yard', inputs=['unit_height_in_feet', 'district yards', 'transit'], cite='82-24.012(h)(1), (h)(4); 84-4.802', status='conditioned'),
    front=dict(kind='district', value='district: R-6 / R-7 / R-10 20 ft (R-20+ 25 ft); corner lot principal frontage 20 ft, other frontage 15 ft', cite='82-24.012(h)(1); 84-4.1004', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft side and rear, same as ≤ 800 sf', cite='82-24.012(h)(3)', status='fixed'),
    street_side=dict(local_text='district "other setback" 15 ft (R-6); Ch. 82-12 applies district setbacks to every street frontage', engine='all_fronts → second frontage is a front: 15 ft', cite='84-4.1004; 82-12.202', status='district'),
    siting=dict(rules=['independent exterior access on the side or rear, or not visible from the street'], separation='silent', cite='82-24.012(e)', status='fixed'),
    budget=dict(applies=False, summary='no FAR, coverage or open-space provision in Ch. 82-24 and none in R-6 … R-10; only "accessory building ≤ 30 % of a required rear yard" (82-14.006)', inputs=[], cite='82-14.006', status='none'),
    overlays=['garage attached to the ADU capped 500 / 600 / 800 sf by lot size', 'one parking space', 'permanent foundation; private sewage / water approval'],
    conflicts=[],
    gaps=[])

add(slug='fairfax', name='Fairfax', county='Marin',
    regime='Inverted: the state-type Class 1 track runs to 1,200 sf (4 ft side / rear, no front setback, no FAR / coverage, 16–18 ft). Class 2 — 10 ft front, 40 % FAR, 50 % coverage, one story — bites only when a unit fails a Class 1 criterion (e.g. height).',
    cap=dict(model='bedrooms', value='Class 1: 1,200 sf regardless of bedrooms · Class 2: 850 sf studio / 1-bd, 1,200 sf 2+ bd', detail='a 1,000 sf studio is fine under Class 1 but over the Class 2 cap', inputs=['unit_size', 'bedrooms (Class 2 only)'], cite='17.048.010(E)(1)(b)2; (G)(1)(a)', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · Class 2 limited to one story', conditioned=None, inputs=['unit_height_in_feet', 'transit', 'stories (Class 2)'], cite='(F)(2)(a)-(b); (G)(12)', status='fixed'),
    front=dict(kind='adu_specific', value='Class 1 (detached ≤ 1,200 sf): none · Class 2: 10 ft ADU-specific', cite='17.048.010(G)(3)(a); (G)(1)(c)', status='fixed'),
    side_rear=dict(value='4 ft', local_text='4 ft on both tracks', cite='17.048.010(E)(1)(b)1; (G)(3)(a)', status='fixed'),
    street_side=dict(local_text='silent in the ADU chapter; the Aug-2026 corner-lot pass recorded 10 ft — reconcile', engine='side → 4 ft, flag', cite='n/a', status='ambiguous'),
    siting=dict(rules=[], separation='silent', cite='n/a', status='none'),
    budget=dict(applies='partial', summary='Class 2 only: lot FAR ≤ 40 %, coverage ≤ 50 %, open space ≥ 50 %, usable open space ≥ 300 sf per unit; Class 1 units (≤ 1,200 sf) exempt', inputs=['lot_area', 'existing_floor_area', 'existing_coverage'], cite='17.048.010(G); 17.136.030(A)', status='input'),
    overlays=['creek buffer: 20 ft or 2× bank depth from Fairfax / San Anselmo Creeks (Class 2)', 'architectural match, dark-sky lighting (Class 2)', 'within 600 ft of a CA Register property → State Historical Building Code'],
    conflicts=[],
    gaps=[])

add(slug='healdsburg', name='Healdsburg', county='Sonoma',
    regime='Two local thresholds: 800 sf ends the front-setback exemption, 850 sf ends the site-coverage exemption. Local detached height is 2 stories / 25 ft. Street side is an explicit 4 ft.',
    cap=dict(model='flat', value='1,200 sf flat', detail='state-mandated (E)(2) track stops at 850 sf', inputs=['unit_size'], cite='20.20.010(C) Table 20', status='fixed'),
    height=dict(max='25 ft / 2 stories, all zones (local track)', conditioned=None, inputs=['unit_height_in_feet'], cite='Table 20 height row', status='permissive'),
    front=dict(kind='district', value='Table 20a (in the ADU chapter): R-1-3.5 20 ft (10 ft non-garage frontage) · R-1-6 20 ft · R-1-12.5 25 ft · R-1-20 / 40 30 ft', cite='20.20.010(C) Table 20a; (D)(1)', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='Table 20', status='fixed'),
    street_side=dict(local_text='4 ft, explicit row in Table 20', engine='4 ft', cite='Table 20', status='fixed'),
    siting=dict(rules=['not between the required front setback and the primary dwelling', 'windows < 10 ft from a rear / side line: clerestory or obscured'], separation='silent', cite='20.20.010(D)(1), (D)(5)', status='fixed'),
    budget=dict(applies=True, summary='site coverage binds above 850 sf: R-1-3.5 50 % · R-1-6 35 % · R-1-12.5 30 % · R-1-20 / 40 25 %; waived if it would preclude an 850 sf / 16 ft / 4 ft unit; no FAR', inputs=['lot_area', 'existing_coverage'], cite='Table 20a', status='input'),
    overlays=['materials / colors / roof slope match the primary', 'landscaping + fire defensible space', 'no parking required'],
    conflicts=[],
    gaps=[])

add(slug='hillsborough', name='Hillsborough', county='San Mateo',
    regime='Class 2 caps at the state floor (850 / 1,000) and expressly strips the 800 sf shield from the 20 ft front, coverage and open space. A 22 ft height tier exists only at 20 ft side / rear + 25 ft from every right-of-way.',
    cap=dict(model='bedrooms', value='850 sf studio / 1-bd · 1,000 sf 2+ bd', detail='each covered accessory structure also ≤ 1,000 sf (17.32.050)', inputs=['unit_size', 'bedrooms'], cite='17.52.020(F)(1)(a)', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · 22 ft with 20 ft side / rear and 25 ft from all rights-of-way · Class 2 one story', conditioned='22 ft tier: side and rear ≥ 20 ft AND ≥ 25 ft from every public right-of-way; second-storey glazing < 30 ft from a line must be clerestory / obscured', inputs=['unit_height_in_feet', 'transit'], cite='(E)(2)(a)(1)-(3); (F)(7)(i)', status='conditioned'),
    front=dict(kind='adu_specific', value='20 ft ADU-specific (Class 2), "notwithstanding" the 800 sf clause', cite='17.52.020(F)(2)(b); (F)(1)(c)', status='fixed'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='17.52.020(F)(2)(a)', status='fixed'),
    street_side=dict(local_text='silent (only a 40 % coverage cap in any setback area adjacent to a street line)', engine='all_fronts → 20 ft ADU front on every street line', cite='17.52.020(F)(3); front rule', status='fixed'),
    siting=dict(rules=['within 600 ft of a CA Register property: not visible from any public right-of-way', 'no structures or mechanical equipment inside the ADU setback area'], separation='silent', cite='(F)(9); (E)(11)', status='fixed'),
    budget=dict(applies=True, summary='Class 2: total coverage ≤ 50 %, ≤ 40 % in any street-adjacent setback area; structural coverage per Table 17.52.020-1 (22 sf per 100 sf net lot to 17,500 sf, then stepped)', inputs=['net_lot_area', 'existing_coverage', 'existing_structural_coverage'], cite='17.52.020(F)(3); Table 17.52.020-1', status='input'),
    overlays=['landscape screening: 15-gal plant per 5 lf of wall or 6 ft fence (WUI may force non-combustible)', 'no direct line of sight from ADU openings to neighbours', 'shared driveway, CCFD access'],
    conflicts=['shield stripped from the 20 ft front / coverage / open space — bites only ≤ 800 sf units, not this track', 'cap equals the state floor exactly'],
    gaps=[])

add(slug='lafayette', name='Lafayette', county='Contra Costa',
    regime='Class C (> 800 sf) gets a 17 ft base height, a district-specific ADU front setback written into the chapter, and an explicit 4 ft "other" setback on corner lots. No FAR / coverage in the single-family R districts.',
    cap=dict(model='flat', value='1,200 sf flat', detail='no bedroom or lot-size tiers', inputs=['unit_size'], cite='6-566(a)(1)', status='fixed'),
    height=dict(max='17 ft Class C base · 18 ft near transit (+2 roof pitch)', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='6-563(b)(1)-(2)', status='fixed'),
    front=dict(kind='adu_specific', value='in the ADU chapter, by district: R-6 / R-10 / R-12 / R-15 / D-1 / M-R 20 ft · R-20 / R-40 / R-65 25 ft · R-100 30 ft · L-R 50 ft', cite='6-566(b)(2)', status='district'),
    side_rear=dict(value='4 ft', local_text='"no more than four feet"', cite='6-566(b)(1)', status='fixed'),
    street_side=dict(local_text='principal frontage takes the district front; "the other setback shall be at least four feet"', engine='4 ft (designated front rule)', cite='6-566(b)(2)(A)-(C)', status='fixed'),
    siting=dict(rules=['an entrance / stair visible from the street may not be on the same side, facing the same direction, as the primary entrance'], separation='silent', cite='6-566(g)(2)', status='fixed'),
    budget=dict(applies=False, summary='no FAR, coverage or open-space threshold for R-6 … R-100 in the ADU chapter or the district chapters (D-1 / M-R districts only)', inputs=[], cite='6-566; district tables', status='none'),
    overlays=['creek setback 12 / 15 / 18 / 21 ft from top of bank by channel depth (3× depth above 21 ft)', 'native tree replacement ≥ 12 in DBH', 'exterior materials / colour match the primary'],
    conflicts=[],
    gaps=[])

add(slug='los-altos', name='Los Altos', county='Santa Clara',
    regime='No 800 sf threshold at all: every detached ADU gets 4 ft side / rear, 18 ft, 5 ft separation and a full FAR / coverage exemption. The only district-dependent number is the front setback.',
    cap=dict(model='bedrooms', value='850 sf one bedroom · 1,200 sf more than one bedroom (summary table says 1,200 flat)', detail='excluding basement', inputs=['unit_size', 'bedrooms'], cite='14.14.070; 14.14.060', status='ambiguous'),
    height=dict(max='18 ft flat, no transit condition', conditioned=None, inputs=['unit_height_in_feet'], cite='14.14.060 table', status='permissive'),
    front=dict(kind='district', value='district: R1-10 25 ft · R1-H 30 ft · R1-20 30 ft · R1-40 50 ft, with a physical-preclusion escape', cite='14.14.060 fn 1; 14.06.080(A)', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='14.14.060 table', status='fixed'),
    street_side=dict(local_text='ADU table says "side 4 ft" without interior / exterior; district R1-10 exterior side is 20 ft', engine='side → 4 ft, flag', cite='14.14.060; 14.06.080(E)(1)', status='ambiguous'),
    siting=dict(rules=['mechanical equipment on interior sides, outside setbacks', 'eaves ≤ 2 ft into a setback; porches ≤ 20 sf'], separation='5 ft', cite='14.14.060; 14.14.080; 14.14.110', status='fixed'),
    budget=dict(applies=False, summary='ADU floor area excluded from parcel FAR and ADU building area excluded from lot coverage, regardless of size', inputs=[], cite='14.14.060', status='none'),
    overlays=['one uncovered parking space (may sit in the front setback)', 'no exterior lighting on sides facing neighbours'],
    conflicts=[],
    gaps=[])

add(slug='los-altos-hills', name='Los Altos Hills', county='Santa Clara',
    regime='850 / 1,000 sf at the state floor; 1,200 sf only as an incentive (side AND rear ≥ 30 ft, one extra parking space, within MDA / MFA). Flat 40 ft ADU front from the right-of-way or access easement.',
    cap=dict(model='incentive', value='850 sf studio / 1-bd · 1,000 sf 2+ bd · 1,200 sf if side AND rear ≥ 30 ft + 1 extra on-site space, within MDA / MFA', detail='the incentive buys area with setback', inputs=['unit_size', 'bedrooms', 'incentive_election'], cite='§ 10-1.1403(a)(2); § 10-1.1407(a)(1)', status='input'),
    height=dict(max='16 ft · 18 ft near transit (20 ft roof-pitch match) · 19 ft incentive', conditioned='19 ft only with side AND rear ≥ 30 ft plus one additional on-site parking space', inputs=['unit_height_in_feet', 'transit'], cite='§ 10-1.1403(f)(2)-(3); § 10-1.1407(a)(2)', status='conditioned'),
    front=dict(kind='adu_specific', value='40 ft from the street right-of-way or access easement (same as the R-A district)', cite='§ 10-1.1403(e)(1)(i); § 10-1.505(c)(1)', status='fixed'),
    side_rear=dict(value='4 ft', local_text='4 ft from side and rear property lines', cite='§ 10-1.1403(e)(2)', status='fixed'),
    street_side=dict(local_text='silent for ADUs; the district designates one street for 40 ft and puts 30 ft on the others', engine='side → 4 ft, flag', cite='§ 10-1.505(c)(2)-(3)', status='ambiguous'),
    siting=dict(rules=['within 30 ft of a side / rear line the exterior entrance may not face that line', 'eaves and projections stay inside the setbacks', 'shared driveway with the primary'], separation='silent', cite='§ 10-1.1404(b); § 10-1.1403(e)(4), (g)(1)', status='fixed'),
    budget=dict(applies=True, summary='first 800 sf of development area and floor area exempt; everything above 800 sf must fit MDA (LUF × 15,000 sf, slope-reduced) and MFA (LUF × 6,000 sf, slope-reduced)', inputs=['lot_area', 'slope', 'LUF', 'existing_development_area', 'existing_floor_area'], cite='§ 10-1.1403(d); §§ 10-1.502 / 503', status='input'),
    overlays=['site development permit if in a recorded easement, slope ≥ 30 %, within 25 ft of a creek bank, geotechnical hazard zone, or heritage-oak root zone'],
    conflicts=['cap equals the state floor exactly'],
    gaps=[])

add(slug='marin-county', name='Marin County', county='Marin',
    regime='Category 2 (> 800 sf) has NO ADU-specific side / rear: the chapter defers to the district (R1 side 6 ft, street side 10 ft, rear 20 % of depth to 25 ft) and the accessory-structure height (16 ft; 30 ft only 40 ft from every line).',
    cap=dict(model='bedrooms', value='850 sf 1-bd / 1,000 sf 2+ bd guaranteed notwithstanding FAR · 1,200 sf if the district FAR (R1 0.30) allows', detail='', inputs=['unit_size', 'bedrooms', 'lot_area', 'existing_floor_area'], cite='§ 22.32.120.B.2', status='input'),
    height=dict(max='16 ft (district accessory limit) · 30 ft if ≥ 40 ft from ALL property lines', conditioned='30 ft only at 40 ft from every line; Category 1 (≤ 800 sf) is 18 ft + 2 ft', inputs=['unit_height_in_feet'], cite='Table 2-5; § 22.20.060.B', status='conditioned'),
    front=dict(kind='district', value='district: R1 (and RA / RR / RE / R2) 25 ft', cite='§ 22.32.120.B.3; Table 2-5', status='district'),
    side_rear=dict(value='4 ft (clamp)', local_text='district R1: side 6 ft, rear 20 % of lot depth to 25 ft — exceeds the §66314 4 ft maximum', cite='§ 22.32.120.B.3; Table 2-5', status='clamp'),
    street_side=dict(local_text='district R1 street side 10 ft', engine='side → 4 ft (clamp), flag', cite='Table 2-5', status='clamp'),
    siting=dict(rules=['within any applicable building envelope (planned districts: Master Plan governs)'], separation='silent', cite='§ 22.32.120.B.3-4', status='fixed'),
    budget=dict(applies=True, summary='FAR 0.30 binds the whole unit, except the 850 / 1,000 sf guarantee; no coverage % in Table 2-5', inputs=['lot_area', 'existing_floor_area'], cite='Table 2-5', status='input'),
    overlays=['ADU Permit (ministerial, 60 days, Director findings)', 'steep-lot parking structure rules'],
    conflicts=['Category 2 side / rear / street side defer to district values above 4 ft → clamp + flag', 'no stated Category 2 height → district 16 ft accessory limit'],
    gaps=[])

add(slug='menlo-park', name='Menlo Park', county='San Mateo',
    regime='Above 800 sf the unit is a "66314 Unit": 850 / 1,000 sf by bedrooms (+100 sf if accessible), district front with the 800 sf yield, and the district coverage / FAL budgets bind in full.',
    cap=dict(model='bedrooms', value='850 sf ≤ 1 bedroom · 1,000 sf more · +100 sf if CBC-accessible', detail='note 3 also caps lots > 10,000 sf at 1,000 sf (oddly placed)', inputs=['unit_size', 'bedrooms'], cite='Table 16.79.070(1) notes 1, 3', status='input'),
    height=dict(max='16 ft · 18 ft near transit · 20 ft roof-pitch match · 18 ft on a multi-storey MF lot', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='Table 16.79.070(1) notes 8-9', status='fixed'),
    front=dict(kind='district', value='district: R-1-U 20 ft above ground (15 ft below) · R-E / R-1-S 20 ft', cite='Table 16.79.070(1); § 16.17.030(4)(ii)(a)', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft; 18 in architectural encroachment', cite='Table 16.79.070(1) note 6', status='fixed'),
    street_side=dict(local_text='silent (table lists Front / Side / Rear only); R-1-U district 12 ft street side not applied to ADUs', engine='side → 4 ft', cite='Table 16.79.070(1)', status='fixed'),
    siting=dict(rules=['second-storey stairs / landings limited to code-minimum egress'], separation='silent', cite='Table note 11', status='none'),
    budget=dict(applies=True, summary='building coverage per district (R-1-U 40 % ≤ 7,000 sf sliding to 35 %; 35 % for 2+ storeys) and FAL (2,800 sf + 25 % of lot area over 7,000 sf) count the ADU in full; coverage may be exceeded only for one ≥ 800 sf detached ADU', inputs=['lot_area', 'existing_coverage', 'existing_FAL', 'stories'], cite='Table note 5; § 16.17.030', status='input'),
    overlays=['CUP (Ch. 16.82) can modify 66314 standards', 'covered porches regulated as part of the ADU'],
    conflicts=[],
    gaps=[])

add(slug='mill-valley', name='Mill Valley', county='Marin',
    regime='Still drafted on Gov. Code 65852.2. Above 800 sf: 850 / 1,000 sf by bedrooms, district exterior yard 15 ft, and the adjusted-floor-area + coverage budgets count the ADU in full (exceptions only through discretionary design review).',
    cap=dict(model='bedrooms', value='850 sf studio / 1-bd · 1,000 sf more', detail='also subject to district adjusted floor area unless that violates the 800 sf shield', inputs=['unit_size', 'bedrooms'], cite='§ 20.90.050(A)(2)', status='input'),
    height=dict(max='16 ft · 25 ft above a garage (combined) · no transit tier in the text', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='§ 20.90.050(A)(4)', status='clamp'),
    front=dict(kind='district', value='district: RS exterior yard 15 ft', cite='§ 20.90.050(A)(1); § 20.16.040(C)', status='district'),
    side_rear=dict(value='4 ft', local_text='"maximum required setback … shall be four feet"', cite='§ 20.90.050(A)(1)(c)', status='fixed'),
    street_side=dict(local_text='for state-track corner lots the remaining frontage "shall be considered the side yard"; a > 800 sf unit does not qualify → district exterior yard 15 ft', engine='side → 4 ft (clamp), flag', cite='§ 20.90.030(A)(12)(b); § 20.16.040(C)', status='clamp'),
    siting=dict(rules=['decks, breezeways, trellises must meet district setbacks'], separation='silent', cite='§ 20.90.050(A)(1)(d)', status='fixed'),
    budget=dict(applies=True, summary='adjusted floor area (< 8,000 sf lot 35 %; 8,000–20,000 10 % + 2,000 sf; > 20,000 5 % + 3,000 sf, max 7,000) and lot coverage (RS-6 / 7.5 / 10 40 %; RS-15 / 20 35 %; RS-30 30 %; RS-43 25 %) count the ADU in full', inputs=['effective_lot_area', 'existing_floor_area', 'existing_coverage'], cite='§ 20.16.040(A)(2); § 20.90.050', status='input'),
    overlays=['watercourse: within 30 ft of top of bank → outside-agency permits', 'floodplain Title 18', 'deed restriction (no separate sale, ≥ 30-day rentals)'],
    conflicts=['no 18 ft transit tier → clamp up to 18 ft near transit', 'no 850 / 1,000 sf guarantee against adjusted floor area → state floor prevails'],
    gaps=[])

add(slug='moraga', name='Moraga', county='Contra Costa',
    regime='"Standard ADU" above 800 sf: 850 / 1,000 sf by bedrooms but shrinking to 800 sf when the lot is at its Design-Guidelines FAR, 19 ft aggregate height but only 16 ft within 10 ft of a property line, slope and grading caps.',
    cap=dict(model='bedrooms', value='850 sf ≤ 1 bedroom · 1,000 sf more · 800 sf if the lot is at or would exceed the Appendix D max floor area', detail='', inputs=['unit_size', 'bedrooms', 'lot_area', 'existing_floor_area'], cite='§ 8.124.130(H)', status='clamp'),
    height=dict(max='19 ft aggregate (highest roof point to lowest natural grade) · 16 ft within 10 ft of a property line · no transit tier', conditioned='any portion over 16 ft must be ≥ 10 ft from every property line (effectively a > 4 ft setback for the tall part)', inputs=['unit_height_in_feet', 'transit'], cite='§ 8.124.130(E)', status='conditioned'),
    front=dict(kind='district', value='district: SFR 1 / 2 DU/ac 25 ft · SFR 3 DU/ac 20 ft · R-R 25 ft from all lines', cite='§ 8.124.130(D); § 8.24.060(A)', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft side and rear', cite='§ 8.124.130(D)', status='fixed'),
    street_side=dict(local_text='silent; district exterior side 25 / 20 / 15 ft and § 8.68.030 applies the district setback to both frontages', engine='side → 4 ft, flag', cite='§ 8.24.060(A); § 8.68.030', status='ambiguous'),
    siting=dict(rules=['construction footprint (unit + grading + outdoor living) on ≤ 20 % average slope', 'accessory building ≤ 30 % of the required rear yard'], separation='silent (fire-safety reference only)', cite='§ 8.124.130(F); § 8.68.070', status='fixed'),
    budget=dict(applies=True, summary='FAR via the size cap: Ch. 8.21 table (0.380 at 5,000 sf net sliding to ~0.33 at 10,000 sf); accessory buildings > 400 sf count; no lot coverage for SFR 1 / 2', inputs=['net_lot_area', 'existing_floor_area'], cite='§ 8.124.130(H); § 8.21.040', status='input'),
    overlays=['grading cut / fill ≤ 200 cu yd', 'parking adjacent to the primary\'s parking, same driveway, permeable', 'historic / native tree rules'],
    conflicts=['800 sf cap at FAR max → state floor 850 / 1,000 prevails', 'no 18 ft transit tier → clamp up', '16 ft within 10 ft of a line is arguably allowed (state floor is 16 ft) → honour + flag'],
    gaps=[])

add(slug='mountain-view', name='Mountain View', county='Santa Clara',
    regime='Generous: 28 ft / 2 storeys for every single-family ADU with 4 ft side / rear and no second-storey stepback. Above 800 sf the excess counts toward FAR. A detached-ADU location standard lives in § 36.12.50 (not in corpus).',
    cap=dict(model='bedrooms', value='850 sf ≤ 1 bedroom · 1,000 sf 2+ bedrooms', detail='excess over 800 sf counts toward district FAR', inputs=['unit_size', 'bedrooms'], cite='§ 36.12.80 table; § 36.12.95(b)(5)', status='input'),
    height=dict(max='28 ft, 1 or 2 storeys, basement included; no separate transit tier', conditioned=None, inputs=['unit_height_in_feet'], cite='§ 36.12.80 table', status='permissive'),
    front=dict(kind='district', value='district: R1 20 ft first-floor wall (+5 ft for a second floor over a projecting attached garage)', cite='§ 36.12.80 table; § 36.10.25', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft, both storeys', cite='§ 36.12.80 table', status='fixed'),
    street_side=dict(local_text='ADU table silent; district R1 "street sides (corner lots) 15 ft" reached through the table\'s deferral clause', engine='side → 4 ft (clamp), flag', cite='§ 36.12.80; § 36.10.25', status='clamp'),
    siting=dict(rules=['detached-ADU location standard referenced by the shield clause — lives in § 36.12.50 (not in corpus)', 'second-storey balconies ≤ 75 sf, 10 ft rear / 7 ft side / 4 ft street side; roof decks prohibited'], separation='silent', cite='§ 36.12.95(b)(1); § 36.12.80 table', status='gap'),
    budget=dict(applies=True, summary='FAR R1 = 0.50 − 0.00001 × lot area (0.45 ≤ 5,000 sf; 0.40 ≥ 10,000 sf); ADU gross floor area exempt up to 800 sf, the rest counts; no lot-coverage %', inputs=['lot_area', 'existing_gross_floor_area'], cite='§ 36.12.95(b)(5); § 36.10.25', status='input'),
    overlays=['enclosed stairs count toward GFA', 'one parking space for 1+ bedroom units (state now bars this)'],
    conflicts=['parking requirement (not a setback) inconsistent with state law'],
    gaps=['§ 36.12.50 detached-ADU location standard missing from corpus'])

add(slug='napa', name='Napa', county='Napa',
    regime='Current (9/2025) and drafted on the new Gov. Code numbering. Flat 1,200 sf; height by reference to § 66321(b)(4); only the 800 sf unit is shielded from the district front setback and coverage.',
    cap=dict(model='flat', value='1,200 sf flat', detail='subject to district structural and impervious coverage except as needed for 800 sf', inputs=['unit_size'], cite='§ 17.52.015(C)(2)(a)', status='fixed'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch), by reference to § 66321(b)(4) · 2 storeys max', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='§ 17.52.015(C)(5)', status='fixed'),
    front=dict(kind='district', value='district: RS-40 / RS-20 30 ft · RS-10 / 7 / 5 / 4, RI, RT 20 ft · or the block average where 50 % of lots are improved', cite='§ 17.52.015(C)(4)(c); § 17.08.030', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft from side and rear lot lines', cite='§ 17.52.015(C)(4)(b)', status='fixed'),
    street_side=dict(local_text='Napa defines "setback, side" to include the street-facing side of a corner lot, district side 30 / 20 / 15 ft; unclear whether the ADU 4 ft overrides', engine='side → 4 ft, flag', cite='§ 17.06.030; § 17.08.030', status='ambiguous'),
    siting=dict(rules=['second storey: entrances / porches / stairs face away from the nearest residential lot line; neighbour-facing windows clerestory or privacy glass'], separation='silent', cite='§ 17.52.015(C)(8)(a)', status='fixed'),
    budget=dict(applies=True, summary='structural coverage: RS-40 20 % · RS-20 25 % · RS-10 40 % · RS-7 45 % · RS-5 45 % · RS-4 50 %; impervious coverage % not found in corpus; no residential FAR', inputs=['lot_area', 'existing_coverage'], cite='§ 17.52.015(C)(2); § 17.08.030', status='input'),
    overlays=['Historic Resources Inventory properties need historic clearance', 'one parking space (inconsistent with state law)'],
    conflicts=['parking requirement (not a setback)'],
    gaps=['impervious-coverage % not in the corpus table'])

add(slug='napa-county', name='Napa County', county='Napa',
    regime='Non-exempt (> 800 sf) detached ADUs get a flat 35 ft height with no stepback, the RS 20 ft front plus county road-centreline setbacks, a 10 ft district street side, and a 500 ft maximum distance from the primary.',
    cap=dict(model='flat', value='1,200 sf flat (inside of exterior walls)', detail='', inputs=['unit_size'], cite='18.104.180.B.5.b', status='fixed'),
    height=dict(max='35 ft flat for non-exempt detached units; no storey limit stated', conditioned=None, inputs=['unit_height_in_feet'], cite='18.104.180.B.5.a', status='permissive'),
    front=dict(kind='district', value='district RS 20 ft, plus road setbacks measured from the road centreline (default 28 ft; 30 / 42 / 70 ft on listed roads)', cite='18.104.180.B.1; Table 18.104.010; Ch. 18.112', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='18.104.180.B.5.c', status='fixed'),
    street_side=dict(local_text='district RS table note C: street side of a corner lot 10 ft', engine='side → 4 ft (clamp), flag', cite='Table 18.104.010 note C', status='clamp'),
    siting=dict(rules=['≤ 500 ft (horizontal) from the nearest living area of the primary, more only for agricultural / utility / sensitive-area constraints'], separation='silent on a minimum; 500 ft maximum', cite='18.104.180.C.1', status='fixed'),
    budget=dict(applies='ambiguous', summary='RS "maximum main building coverage 50 %" — unclear whether a detached ADU counts as a main building; no FAR row', inputs=['lot_area', 'existing_coverage'], cite='Table 18.104.010', status='ambiguous'),
    overlays=['county road centreline setbacks (Ch. 18.112)', 'groundwater (GSP / deficient areas) water-availability analysis', 'one parking space (studios exempt)'],
    conflicts=[],
    gaps=[])

add(slug='orinda', name='Orinda', county='Contra Costa',
    regime='Cap at the state floor in "adjusted square feet" (Orinda\'s own floor-area measurement). No local 800 sf shield clause; a > 800 sf unit simply takes the district 20–25 ft front and the district street-frontage side / rear. FAR expressly does not apply.',
    cap=dict(model='bedrooms', value='850 adjusted sf studio / 1-bd · 1,000 adjusted sf more', detail='measured per OMC 17.6.3 / 17.6.4, not gross or livable area', inputs=['unit_size', 'bedrooms', 'adjusted-sf measurement'], cite='17.3.4.C.6', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · above a garage: 27 ft / 2.5 storeys outside the primary-dwelling setback band', conditioned='above-garage units: > 16 ft only outside the setbacks that apply to the primary dwelling', inputs=['unit_height_in_feet', 'transit'], cite='17.3.4.C.4.c.ii', status='conditioned'),
    front=dict(kind='district', value='district: RVL-E / RVL / RL-40 / RL-20 25 ft · RL-15 / 12 / 10 / 6 20 ft · RM 15 ft', cite='17.3.4.C.4; Schedule 17.4.2; 17.4.22.A', status='district'),
    side_rear=dict(value='4 ft', local_text='"no more than 4 ft"', cite='17.3.4.C.4.b.ii', status='fixed'),
    street_side=dict(local_text='district "side and rear yard with street frontage" 25 / 20 / 15 ft by district', engine='side → 4 ft (clamp), flag', cite='Schedule 17.4.2; 17.4.22.A-B', status='clamp'),
    siting=dict(rules=[], separation='silent in the ADU chapter; district accessory-structure rule 5 ft', cite='17.4.22.C', status='ambiguous'),
    budget=dict(applies=False, summary='floor-area limits of 17.6.2 expressly do not apply; no lot-coverage row in Schedule 17.4.2', inputs=[], cite='17.3.4.C.6', status='none'),
    overlays=['water-channel setbacks 15–45 ft from top of bank (0 for the smallest channels)', 'ridgeline / environmental preservation overlay, tree removal', 'one 9 × 19 ft all-weather parking space for 1+ bedrooms'],
    conflicts=['cap equals the state floor exactly (in adjusted sf)'],
    gaps=[])

add(slug='palo-alto', name='Palo Alto', county='Santa Clara',
    regime='Local-standards units: 900 / 1,000 sf by bedrooms, 3 ft separation, every square foot over 800 counts toward FAR / coverage / max house size. Table 2 never states a detached front setback; the chapter presupposes the R-1 contextual front.',
    cap=dict(model='bedrooms', value='900 sf studio / 1-bd · 1,000 sf 2+ bd', detail='lofts ≥ 5 ft clear count', inputs=['unit_size', 'bedrooms'], cite='18.09.040 Table 2', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · 30 ft in RE · 25 ft in OS', conditioned=None, inputs=['unit_height_in_feet', 'transit', 'zone'], cite='18.09.040 Table 2 note 5', status='fixed'),
    front=dict(kind='ambiguous', value='Table 2 lists only side / rear for detached units; (i) and (j)(4) presuppose the R-1 front: greater of 20 ft or the block average when ≥ 30 ft, plus special setback maps', cite='18.09.040 Table 2, (i), (j)(4); 18.12.040(e)', status='ambiguous'),
    side_rear=dict(value='4 ft', local_text='4 ft; no projections except a 2 ft eave', cite='18.09.040 Table 2; (j)(3)', status='fixed'),
    street_side=dict(local_text='district R-1 street side 16 ft; 10 ft by election when the primary is built / expanded with the ADU', engine='side → 4 ft (clamp), flag', cite='18.09.040(j)(4); R-1 Table 2', status='clamp'),
    siting=dict(rules=['except on corner lots, the entrance may not face the same lot line as the main entrance unless in the rear half of the lot'], separation='3 ft', cite='18.09.040(k)(1); (j)(1)', status='fixed'),
    budget=dict(applies=True, summary='800 sf (attached + detached combined) exempt from FAR, coverage and max house size; the excess counts: R-1 FAR .45 on the first 5,000 sf + .30, coverage 35 % (+5 % patio), 6,000 sf house cap', inputs=['lot_area', 'existing_floor_area', 'existing_coverage'], cite='18.09.040; R-1 Table 2', status='input'),
    overlays=['protected trees: ≤ 25 % canopy / root removal, no trenching in the TPZ', 'basement walls / lightwells ≥ 4 ft from interior lines', 'noise equipment respects the underlying front setback'],
    conflicts=[],
    gaps=[])

add(slug='portola-valley', name='Portola Valley', county='San Mateo',
    regime='Clean two-track chapter. The binding constraint above 800 sf is the parcel\'s Adjusted Maximum Floor Area / impervious-surface budget (ADUs count in full) rather than the 1,200 sf cap; acreage districts have a 50 ft front and scenic-corridor setbacks.',
    cap=dict(model='flat', value='1,200 sf interior livable space', detail='also bounded by AMFA / coverage / FAR / CAR', inputs=['unit_size'], cite='18.25.060.C.3.ii.a; C.4.i', status='fixed'),
    height=dict(max='16 ft · 18 ft near transit or on an MF multi-storey lot (+2 roof pitch)', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='18.25.060.C.5.ii.b', status='fixed'),
    front=dict(kind='district', value='district incl. scenic-corridor setbacks: 7.5M / 15M / 20M 20 ft · 1A–7.5A 50 ft', cite='18.25.060.C.6.ii.a; 18.48.010 Table 1', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='18.25.060.C.6.ii.b-c', status='fixed'),
    street_side=dict(local_text='silent; Table 1 has no street-side column (side 5–25 ft by district)', engine='side → 4 ft', cite='18.48.010 Table 1', status='fixed'),
    siting=dict(rules=[], separation='silent', cite='18.25.060', status='none'),
    budget=dict(applies=True, summary='AMFA (3,019 sf 7.5M … 9,581 sf 7.5A, +5 % if ≤ 1 storey), maximum impervious surface (2,231 sf 7.5M … 19,822 sf 7.5A), FAR, CAR — the ADU counts in full', inputs=['zone', 'lot_area', 'existing_floor_area', 'existing_impervious'], cite='18.25.060.C.4.i; 18.48.010 Table 1; 18.48.020', status='input'),
    overlays=['scenic-corridor setbacks on the front', 'objective design: LRV ≤ 40 %, 700-lumen entry lighting, native plants', 'new utility connections undergrounded; well / septic sizing'],
    conflicts=[],
    gaps=['"CAR" (coverage area ratio) used in the ADU chapter, not defined in the grepped tables'])

add(slug='san-carlos', name='San Carlos', county='San Mateo',
    regime='No numeric cap: the non-exempt unit is bounded by the district Maximum Floor Area left on the lot (800 sf exempt) and 50 % of the existing primary. Second-storey side / rear revert to the district (RS-6 9 / 15 ft) — the clearest state-law tension in the set.',
    cap=dict(model='far_budget', value='remaining district MFA (RS-6: greater of 1,100 sf + 35 % of lot, or 50 % of lot ≤ 7,500 sf; 50 % above; RS-3: none), 800 sf exempt · AND ≤ 50 % of the existing primary', detail='can fall below 850 / 1,000 sf on small lots or small primaries', inputs=['unit_size', 'lot_area', 'existing_floor_area', 'primary_floor_area', 'zone'], cite='18.23.210.F.4.f; Table 18.04.030', status='clamp'),
    height=dict(max='18 ft flat (+2 roof pitch) · 20 ft above a detached garage', conditioned='second storey → district side / rear / street-side setbacks (RS-6 9 / 15 / 7.5–11.5 ft; RS-3 14 / 20 / 10–14 ft)', inputs=['unit_height_in_feet', 'stories'], cite='18.23.210.F.4.i; F.5.c; Table 18.23.210(E)(4)', status='conditioned'),
    front=dict(kind='district', value='district: RS-6 15 ft first storey / 19 ft second storey · RS-3 20 ft', cite='18.23.210.F.4.b-c; Table 18.04.030', status='district'),
    side_rear=dict(value='4 ft (clamp on the 2nd storey)', local_text='first storey 4 ft; second storey district RS-6 9 / 15 ft, RS-3 14 / 20 ft — exceeds the 4 ft maximum', cite='Table 18.23.210(E)(4); 18.23.210.F.4.e.i', status='clamp'),
    street_side=dict(local_text='first storey 4 ft; second storey district 7.5–11.5 ft (RS-6) / 10–14 ft (RS-3); reversed corner lots use the key lot\'s front', engine='4 ft; 2nd storey → clamp, flag', cite='Table 18.23.210(E)(4); 18.04.030.H', status='clamp'),
    siting=dict(rules=['over-garage units must meet the district front', 'detached garage in the front half of the lot per 18.04.030(H)'], separation='Building Code', cite='18.23.210.F.5.a', status='fixed'),
    budget=dict(applies=True, summary='non-exempt from district lot coverage (RS-6 50 %; RS-3 25 % hillside / 35 %); MFA as above with 800 sf exempt; natural-state / open-space rules where applicable', inputs=['lot_area', 'existing_coverage', 'existing_floor_area'], cite='Table 18.23.210(E)(4)', status='input'),
    overlays=['balconies / decks above the first floor 10 ft from side / rear lines; obscured glazing within 5 ft', 'Hillside (H) overlay: lower coverage', 'objective design guidelines of the district'],
    conflicts=['second-storey side / rear / street side at district values → clamp to 4 ft + flag', '50 %-of-primary cap can fall below the state 850 / 1,000 sf floor → state floor prevails'],
    gaps=[])

add(slug='san-jose', name='San Jose', county='Santa Clara',
    regime='More permissive than the state floor on the ground floor (0 ft side / rear) with a 4 ft second-storey setback, a lot-size cap (1,000 / 1,200 sf), a rear-yard-or-45-ft siting rule, 6 ft separation and a 40 % rear-yard coverage cap.',
    cap=dict(model='lot_size', value='1,000 sf on lots ≤ 9,000 sf · 1,200 sf on lots > 9,000 sf', detail='no bedroom tiers', inputs=['unit_size', 'lot_area'], cite='20.80.175.D.1, Table 20-55', status='input'),
    height=dict(max='18 ft one storey (no transit condition) · 25 ft two storeys', conditioned='any second storey must hold 4 ft side / rear with ≤ 1 ft overhang', inputs=['unit_height_in_feet', 'stories'], cite='20.80.175.D.2.a-c; D.3.e', status='conditioned'),
    front=dict(kind='district', value='district: R-1-8 / R-1-5 20 ft · R-1-2 / R-1-1 30 ft · R-1-RR 50 ft (block-average exception); plus the siting rule in G4', cite='20.80.175.D.3.a, D.5.b; Table 20-30', status='district'),
    side_rear=dict(value='0 ft ground storey · 4 ft second storey', local_text='0 ft at the ground storey, 4 ft for any second storey — more permissive than state, honour it', cite='20.80.175.D.3.b-c, D.3.e', status='permissive'),
    street_side=dict(local_text='silent (side 0 ft stated without an interior / corner distinction); district corner side 12.5 / 15 / 20 / 30 ft', engine='side → 0 ft ground / 4 ft upper, flag; all_fronts overrides (oversized corner lots, MS-G / MS-C) → district front on both frontages', cite='20.80.175.D.3.b; 20.200.670', status='ambiguous'),
    siting=dict(rules=['in the rear yard, OR ≥ 45 ft from the front lot line, OR meet accessory-building setbacks (20.30.500)', 'Historic Resources Inventory lots: ≥ 45 ft from the front line'], separation='6 ft', cite='20.80.175.D.5.b-c; E.1.c', status='fixed'),
    budget=dict(applies=True, summary='rear-yard coverage: ADU + accessory structures (except pools) ≤ 40 % of the rear yard; porches / balconies count; no lot-coverage row in R-1', inputs=['rear_yard_area', 'existing_accessory_coverage'], cite='20.80.175.D', status='input'),
    overlays=['riparian corridor: on lots ≥ ½ acre, > 100 ft from top of bank', 'Building / Fire Code setbacks and no-build easements', 'ordinance-size tree removal 1:1 replacement'],
    conflicts=[],
    gaps=[])

add(slug='san-mateo', name='San Mateo', county='San Mateo',
    regime='No numeric cap: living area over 800 sf consumes the remaining district FAR and the unit may not exceed the primary. Height 18 ft plate / 24 ft peak with a 12 ft @ 45° daylight plane at the side / rear lines, or a 0 ft rear-one-third option at accessory-building scale.',
    cap=dict(model='far_budget', value='remaining district FAR (R1-A 0.4 ≤ 10,000 sf + 0.2 above; R1-B / C 0.5 ≤ 6,000 sf + 0.2 above; 6,000 sf parcel ceiling), 800 sf exempt · AND not larger than the primary dwelling', detail='falls below 850 / 1,000 sf when the primary is 800–1,000 sf', inputs=['unit_size', 'lot_area', 'existing_floor_area', 'primary_living_area', 'zone'], cite='27.19.060(b); 27.18.060', status='clamp'),
    height=dict(max='18 ft plate / 24 ft peak · rear-one-third option: 9 ft plate / 16 ft peak', conditioned='R-1 daylight plane (12 ft at the side line, 45°) applied to the ADU side and rear lines — at a 4 ft setback the wall height is limited at the setback line', inputs=['unit_height_in_feet', 'plate_height'], cite='27.19.060(c)(2); (g)(1)', status='conditioned'),
    front=dict(kind='district', value='district: R1-A 25 ft · R1-B / R1-C 15 ft · 50 ft from the centreline of a private road; none for a rear-one-third accessory-scale unit', cite='27.19.060(d)(1), (d)(3); 27.18.070', status='district'),
    side_rear=dict(value='4 ft · or 0 ft in the rear one-third at accessory scale', local_text='4 ft; 0 ft if in the rear third meeting Ch. 27.70 (9 ft plate / 16 ft peak, one habitable floor, 4 ft from the principal building)', cite='27.19.060(d)(1)-(2); 27.18(c)', status='permissive'),
    street_side=dict(local_text='silent; district street side ground floor 15 % of lot width (7.5–25 ft R1-A; 7.5–15 ft R1-B / C), 10 ft above the first storey', engine='side → 4 ft (clamp), flag', cite='27.18.080(b)', status='clamp'),
    siting=dict(rules=['rear-one-third 0 ft option (accessory-building rules)', 'second-storey privacy: obscured glazing, 5 ft stair setback, 50 sf deck cap, no roof decks'], separation='silent (4 ft open to sky for the rear-third option)', cite='27.19.060(d)(1); (g)(2)-(5)', status='fixed'),
    budget=dict(applies=True, summary='FAR: 800 sf of ADU living area exempt per lot, the remainder counts against district FAR; lot coverage silent; accessory buildings ≤ 50 % of the required rear yard', inputs=['lot_area', 'existing_floor_area'], cite='27.19.060(b); 27.18(d)', status='input'),
    overlays=['Zoning Administrator alternative review for height / setback / daylight-plane deviations (cannot raise FAR)', 'front-yard and street-side paving limits'],
    conflicts=['FAR / "not larger than the primary" can fall below the state size floor → state floor prevails', 'no 18 ft transit tier stated (18 ft plate already ≥ the floor)'],
    gaps=[])

add(slug='san-mateo-county', name='San Mateo County', county='San Mateo',
    regime='Detached cap is the greater of 800 sf or 35 % of the primary (≤ 1,500 sf). Front is lot-specific: the lesser of the district front or the primary\'s own distance from the front line. Above 16 ft the side / rear step back to 5 / 10 ft.',
    cap=dict(model='pct_primary', value='greater of 800 sf or 35 % of the primary\'s livable floor area, capped at 1,500 sf; also counts against district total floor area', detail='a 2-bd unit on a primary under ~2,857 sf is capped below the state 1,000 sf floor', inputs=['unit_size', 'primary_living_area', 'bedrooms'], cite='8.392.060(2)(a)', status='clamp'),
    height=dict(max='26 ft, from the lower of finished / natural grade', conditioned='above 16 ft: stepback to 5 ft side / 10 ft rear (upper floor)', inputs=['unit_height_in_feet'], cite='8.392.050(4)(b)-(c)', status='conditioned'),
    front=dict(kind='lot_specific', value='lesser of the district front setback (S-districts 20 ft) or the primary residence\'s distance from the front property line', cite='8.392.050(4)(a)', status='input'),
    side_rear=dict(value='4 ft at grade · 5 / 10 ft above 16 ft', local_text='4 ft side / rear at grade; stepback to 5 side / 10 rear above 16 ft', cite='8.392.050(4)(b)-(c)', status='conditioned'),
    street_side=dict(local_text='silent ("side: four feet"); the definitions treat a street side lot line as a side lot line', engine='side → 4 ft', cite='8.392.050(4)(b); definitions', status='fixed'),
    siting=dict(rules=['ADU atop / below an existing detached garage inside the front setback needs a CUP'], separation='5 ft', cite='8.392.050(4)(a); 8.392.060(1)', status='fixed'),
    budget=dict(applies=True, summary='counts against district lot coverage and total floor area (S-50 50 % / FAR .45; S-71 50 %, 2,000–4,100 sf); R-1 base-district rows not in corpus', inputs=['lot_area', 'existing_coverage', 'existing_floor_area'], cite='8.392.060(2)(a); S-district chapters', status='gap'),
    overlays=['WUI (Emerald Lake Hills, Devonshire): no parking exemption; fire-engine access', 'fire-rated walls / no egress windows on sides that encroach the setbacks', 'scenic corridors; parking in the front yard ≤ 600 sf, pervious'],
    conflicts=['35 %-of-primary cap can fall below the state 850 / 1,000 sf floor → state floor prevails', 'stepback above 16 ft exceeds 4 ft → treat as valid + flag (open decision)'],
    gaps=['R-1 base-district coverage / floor-area rows missing from corpus'])

add(slug='santa-clara-county', name='Santa Clara County', county='Santa Clara',
    regime='Height is coupled to setbacks: 16 ft at 4 ft side / rear; taller (district 35 ft / 2 storeys) only with the full district single-family setbacks (R1 side 5, exterior side 10, rear 25 ft; rural 30 / 30 / 30). No transit tier, no local shield language.',
    cap=dict(model='flat', value='1,200 sf flat (+ 400 sf attached garage, + 400 sf decks / porches, + a 500 sf JADU)', detail='', inputs=['unit_size'], cite='4.10.015(D)(1)', status='fixed'),
    height=dict(max='16 ft at ADU setbacks · district 35 ft / 2 storeys with full district SF setbacks and a hip / gable roof', conditioned='> 16 ft requires the district single-family setbacks (R1 side 5 ft, exterior side 10 ft, rear 25 ft; A / HS / RR 30 ft all round)', inputs=['unit_height_in_feet', 'transit'], cite='4.10.015(D)(2)-(3); Tables 2.30-3, 2.20-3', status='conditioned'),
    front=dict(kind='district', value='district (same as the primary): R1 / R1E / R1S / R2 25 ft · RHS 30 ft · A / AR / HS / RR 30 ft', cite='4.10.015(D)(2); Table 2.30-3', status='district'),
    side_rear=dict(value='4 ft (≤ 16 ft) · district above 16 ft', local_text='4 ft side / rear if ≤ 16 ft; district SF setbacks to go taller', cite='4.10.015(D)(2)-(3)', status='conditioned'),
    street_side=dict(local_text='silent in the chapter; district "corner lot: exterior side" 10 ft (R1) / 20 ft (RHS) binds only above 16 ft', engine='side → 4 ft at ≤ 16 ft; above 16 ft the district branch applies', cite='Table 2.30-3', status='conditioned'),
    siting=dict(rules=[], separation='6 ft', cite='4.10.015(D)', status='fixed'),
    budget=dict(applies='silent', summary='ADU chapter silent; R1 / R1E / RHS / R1S / R2 coverage "—" in Table 2.30-3; in -n1 / -n2 combining districts 800 sf of ADU area is excluded from floor-area calculations', inputs=[], cite='Table 2.30-3; 4.10.015(J)(3)', status='none'),
    overlays=['design combining districts -d / -d1 / -d2 / -sr: LRV ≤ 45', 'historic -h1 Priority List properties → HHC design review', 'scenic road setback 100 ft (district tables)', 'building site approval, OWTS / water supply'],
    conflicts=['no 18 ft transit tier → clamp up to 18 ft near transit', 'no 800 sf shield language (relies on the general "state law prevails" clause)'],
    gaps=[])

add(slug='saratoga', name='Saratoga', county='Santa Clara',
    regime='Ambiguous size ladder: up to 1,000 sf with 4 ft side / rear; 1,200 sf only for a unit "not located within a side or rear setback area" (district side 10–20 ft, rear 25–50 ft). Floor area and site coverage bind fully above 800 sf.',
    cap=dict(model='flat', value='1,000 sf with 4 ft side / rear · 1,200 sf only outside the district side / rear setback areas', detail='both the ADU and the primary count toward the district max floor area', inputs=['unit_size'], cite='15-56.025(a)(1), (a)(3)(a)(ii)', status='ambiguous'),
    height=dict(max='16 ft · 18 ft near transit or on a multi-storey MF lot (+2 roof pitch)', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='15-56.025', status='fixed'),
    front=dict(kind='district', value='district: R-1-10,000 / 12,500 / 15,000 25 ft · R-1-20,000 / 40,000 30 ft · HR 30 ft', cite='15-56.025(a)(5); 15-12.090(a)(1)', status='district'),
    side_rear=dict(value='4 ft (≤ 1,000 sf) · district for 1,001–1,200 sf → clamp', local_text='4 ft up to 1,000 sf; a 1,001–1,200 sf unit must sit outside the district side / rear setback areas (10–20 / 25–50 ft)', cite='15-56.025(a)(1), (a)(3)(a)(ii), (a)(5)', status='clamp'),
    street_side=dict(local_text='silent ("rear and side setbacks of no less than four feet"); district exterior side 25 ft first floor / 30 ft second floor', engine='side → 4 ft (clamp), flag', cite='15-12.090(a)(3)', status='clamp'),
    siting=dict(rules=['shared driveway unless a corner-lot secondary frontage or ≥ 80 ft of interior frontage'], separation='silent', cite='15-56.025(a)(8)', status='fixed'),
    budget=dict(applies=True, summary='district floor area (≤ 4,999 sf lot 2,400 sf; 5,000–10,000 2,400 + 160 / 1,000 sf; stepped above) and site coverage (R-1-10,000 60 % · 12,500 55 % · 15,000 50 % · 20,000 45 % · 40,000 35 %; HR 25 %) count the ADU in full; one-time 10 % bonus on ≥ 10,000 sf lots', inputs=['net_site_area', 'existing_floor_area', 'existing_coverage'], cite='15-56.025(a)(1); 15-12.080 / .090', status='input'),
    overlays=['no roof decks on any new ADU', 'colour must match the main structure', 'HR hillside district: front 30, interior side 20, exterior side 25, coverage 25 %'],
    conflicts=['1,001–1,200 sf tier requires district side / rear (> 4 ft) → clamp to 4 ft + flag, or treat 1,000 sf as the effective cap'],
    gaps=[])

add(slug='sausalito', name='Sausalito', county='Marin',
    regime='Clean two-class chapter (Class 1 = § 66323, Class 2 = §§ 66314–66322). Above 800 sf: 10 ft ADU-specific front, FAR / coverage / impervious-surface budgets, one storey; all capped by the 800 sf floor. Our front-setback DB holds district 0 ft → conflict to resolve.',
    cap=dict(model='bedrooms', value='850 sf studio / 1-bd · 1,000 sf 2+ bd, interior livable space', detail='FAR / coverage may further limit but not below 800 sf', inputs=['unit_size', 'bedrooms'], cite='10.44.080(G)(1)(a)', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch, max 20) · 18 ft on a multi-storey MF lot · Class 2 detached: one storey', conditioned=None, inputs=['unit_height_in_feet', 'transit', 'stories'], cite='10.44.080(G)', status='fixed'),
    front=dict(kind='adu_specific', value='10 ft ADU-specific (Class 2); residential_front_setback DB says district 0 ft (10 ft only on special setback lines) — the ADU chapter governs on this track', cite='10.44.080(G)(3)(a), (G)(1)(c)', status='fixed'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='10.44.080(G)(3)(a)', status='fixed'),
    street_side=dict(local_text='silent; definitions give a corner lot one side line and one rear line', engine='side → 4 ft', cite='10.44.080(G)(3); definitions', status='fixed'),
    siting=dict(rules=['Historic District (-H): entirely behind the rear-most exterior wall of the primary, directly behind it'], separation='silent', cite='10.44.080(G)(10)', status='fixed'),
    budget=dict(applies=True, summary='Class 2 tables in the ADU chapter: FAR R-1-6 .45 / R-1-8 .40 / R-1-20 .35; building coverage 35 / 30 / 30 %; impervious surface 67.5 / 65 / 65 %', inputs=['lot_area', 'existing_floor_area', 'existing_coverage', 'existing_impervious'], cite='10.44.080(G)', status='input'),
    overlays=['septic: percolation test within 5 years for onsite wastewater', 'separate utility connection for Class 2', 'one parking space per unit or bedroom, whichever less'],
    conflicts=[],
    gaps=['front-setback DB (district 0 ft) vs ADU chapter 10 ft — reconcile which the engine loads'])

add(slug='sonoma-county', name='Sonoma County', county='Sonoma',
    regime='Nothing flips at 800 sf for side / rear or size; only the district front, riparian setback and lot coverage carry an 800 sf shield. Detached height inherits the district accessory-building limit but never below 18 ft (35 ft in RR / AR / R2).',
    cap=dict(model='flat', value='1,200 sf flat', detail='', inputs=['unit_size'], cite='26-88-060(h)(5)(i)', status='fixed'),
    height=dict(max='district accessory-building height, not less than 18 ft (R1 18 ft · RR / AR / R2 35 ft)', conditioned=None, inputs=['unit_height_in_feet', 'zone'], cite='26-88-060(h)', status='permissive'),
    front=dict(kind='district', value='district: R1 / RR / R2 20 ft · R3 15 ft · AR 30 ft, plus a 45 ft front street-centreline setback (55 ft AR)', cite='26-88-060(h)(3)(i); Table 8-2', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft', cite='26-88-060(h)(3)(ii)', status='fixed'),
    street_side=dict(local_text='silent; district street side R1 / RR / R2 20 ft, R3 15 ft, AR 30 ft, side-street centreline 45 ft; either street line may be the front', engine='side → 4 ft (clamp), flag', cite='Table 8-2; definitions', status='clamp'),
    siting=dict(rules=['in conformance with easements and building envelopes', 'riparian corridor (Art. 65) setbacks with the 800 sf shield; RC permit first'], separation='silent', cite='26-88-060(h)(3), (h)(3)(iv)', status='fixed'),
    budget=dict(applies=True, summary='base-district lot coverage: RR 35 % · R1 40 % · R2 50 % · R3 60 % · AR by parcel size (Table 8-4); FAR and open space silent', inputs=['lot_area', 'existing_coverage', 'zone'], cite='Table 8-2', status='input'),
    overlays=['groundwater class 3 / 4 and critical fisheries habitat water rules', 'Z (ADU exclusion) combining district prohibits ADUs', 'SRA fire setbacks and fire-resistive construction'],
    conflicts=[],
    gaps=[])

add(slug='sunnyvale', name='Sunnyvale', county='Santa Clara',
    regime='Side / rear stay 4 ft at both floors above 800 sf. The real flip is procedural (MPP) plus the district front and the corner-lot "reducible front", partial coverage / FAR counting (only the area above 800 sf), 5 ft separation and second-floor design rules.',
    cap=dict(model='flat', value='1,000 sf gross floor area, no bedroom restriction', detail='', inputs=['unit_size'], cite='19.79.050(b)(1)', status='fixed'),
    height=dict(max='16 ft · 18 ft near transit (+2 roof pitch) · 18 ft on a multi-storey MF lot · 2 storeys max', conditioned='a second-floor unit takes the district second-storey front (25 ft, 19.34.045) and the solar-access rules', inputs=['unit_height_in_feet', 'transit', 'stories'], cite='Table 19.79.070; 19.79.040(t)(1)', status='conditioned'),
    front=dict(kind='district', value='district: R-0 / R-1 / R-2 15 ft minimum, 20 ft average → 20 ft · R-1.5 20 ft · second storey 25 ft', cite='19.79.040(w)(2); Table 19.34.030; 19.34.045', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft first and second floor', cite='19.79.040(w)(1); Table 19.79.070', status='fixed'),
    street_side=dict(local_text='corner lots: the "reducible front" (longer frontage) district setback applies above 800 sf; may be reduced to 9 ft in R-0 / R-1 / R-1.5 / R-2', engine='all_fronts → second frontage is a front: 20 ft, reducible to 9 ft', cite='Table 19.79.070; 19.34.040(b)', status='district'),
    siting=dict(rules=['ADU entrance and house entrance not on the same wall plane facing the street', 'second-floor entrance not on the same elevation as the primary entrance'], separation='5 ft from the main building and from unconnected accessory structures', cite='19.79.040(i)(1), (t)(2), (g); 19.79.050(b)(2)(A)', status='fixed'),
    budget=dict(applies='partial', summary='only the area above 800 sf counts toward lot coverage (45 % single-storey / 40 % two-storey), gross floor area and FAR (45 % or 3,600 sf, whichever less); covered patios with > 50 % solid roof count', inputs=['lot_area', 'existing_coverage', 'existing_gross_floor_area', 'stories'], cite='Table 19.32.020; 19.79', status='input'),
    overlays=['no ADU in easements that prohibit permanent structures', 'protected trees: 15-gal replacement or fee', 'solar access (Ch. 19.56) for second-floor units', 'no parking required'],
    conflicts=[],
    gaps=[])

add(slug='windsor', name='Windsor', county='Sonoma',
    regime='Fully consistent with the state floors: 850 / 1,200 sf by bedrooms, 16 / 18 / 20 ft, 4 ft on every non-front side including the street side. The 800 sf threshold only runs the front / coverage shield and the cap when paired with a JADU.',
    cap=dict(model='bedrooms', value='850 sf studio / 1-bd · 1,200 sf 2+ bd · 800 sf if combined with a JADU', detail='', inputs=['unit_size', 'bedrooms', 'jadu_present'], cite='17.82.050(D)(1), (2), (4)', status='input'),
    height=dict(max='16 ft · 18 ft near transit (+2 = 20 ft) · 18 ft on a multi-storey multi-unit lot · 25 ft above a detached garage', conditioned=None, inputs=['unit_height_in_feet', 'transit'], cite='17.82.050', status='fixed'),
    front=dict(kind='district', value='district Table 17.10-02: RR 25 ft · ER 20 ft · SR 15 ft · VR / MDR 10 ft', cite='17.82.050(C)(5); Table 17.10-02', status='district'),
    side_rear=dict(value='4 ft', local_text='4 ft interior side / 4 ft rear', cite='17.82.050(C)(5)', status='fixed'),
    street_side=dict(local_text='4 ft, explicit', engine='4 ft', cite='17.82.050(C)(5)', status='fixed'),
    siting=dict(rules=['privacy standard H when the ADU sits outside the primary\'s required setbacks and fronts a neighbour: clerestory / obscured glazing or lattice'], separation='5 ft (or Building Code minimum, whichever greater)', cite='17.82.050(H), (C)(6)', status='fixed'),
    budget=dict(applies=True, summary='parcel coverage by structures: RR 30 % · ER 35 % · SR 50 % · VR 55 % · MDR 60 %; no FAR', inputs=['lot_area', 'existing_coverage'], cite='Table 17.10-02', status='input'),
    overlays=['one all-weather parking space (tandem / setbacks allowed)', 'historic overlay design review', 'fire sprinklers only if the primary needs them'],
    conflicts=[],
    gaps=[])

assert len(J) == 28, len(J)
assert len({j['slug'] for j in J}) == 28

# ---- derived counts for the page header -------------------------------------------------------------
GATES = ['cap', 'height', 'front', 'side_rear', 'street_side', 'siting', 'budget']
NONTRIVIAL = {'input', 'conditioned', 'clamp', 'ambiguous', 'gap'}


def complexity(j):
  n = 0
  for g in GATES:
    if j[g]['status'] in NONTRIVIAL:
      n += 1
  return n


for j in J:
  j['complexity'] = complexity(j)
  j['new_inputs'] = sorted({i for g in GATES for i in j[g].get('inputs', [])
                            if i not in ('unit_size', 'unit_height_in_feet', 'transit', 'zone')})

model = {
  'title': 'Local-track (> 800 sf) detached ADU decision-tree model, 28 jurisdictions',
  'generated': '2026-10-11',
  'source': 'zoning-ordinances/adu_over800_survey.json (2026-10-07) curated by hand; residential_front_setback from zoning_ordinance_links.json',
  'note': 'Engine-shaped research model. Every value traces to a citation in the survey; NOT yet verified as engine data.',
  'status_vocabulary': {
    'fixed': 'numeric, computable from inputs the engine already has',
    'district': 'needs the zone code → district table',
    'input': 'needs a new input (bedrooms, lot area, storeys, primary / existing floor area, coverage)',
    'conditioned': 'height- or storey-conditioned setback → a branch',
    'clamp': 'local text exceeds what state law allows → clamp + flag',
    'ambiguous': 'text unclear → engine default + flag',
    'gap': 'corpus gap / unsourced',
    'none': 'nothing binds at this gate',
    'permissive': 'local text is more generous than the state floor → honour it',
  },
  'gates': GATES,
  'jurisdictions': J,
}

with open(MODEL_OUT, 'w') as f:
  json.dump(model, f, indent=1, ensure_ascii=False)
  f.write('\n')
print('wrote', MODEL_OUT)

with open(os.path.join(HERE, 'local_track_trees_template.html')) as f:
  html = f.read()
html = html.replace('/*__MODEL__*/null', json.dumps(model, ensure_ascii=False))
with open(PAGE_OUT, 'w') as f:
  f.write(html)
print('wrote', PAGE_OUT, len(html), 'bytes')
