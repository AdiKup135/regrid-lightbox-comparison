"""Build shared fixtures for the TS-vs-Python differential check."""
import json, math, random, sys
sys.path.insert(0, "/Users/adi/Documents/formX/site/gaudi-api-port")
from services.compute.parcel_edges.geometry import make_projection

ORIGIN_LNG, ORIGIN_LAT = -122.1, 37.4
PROJ = make_projection(ORIGIN_LNG, ORIGIN_LAT)

def wkt(pts):
  ll = [PROJ.to_ll(p) for p in pts]
  ring = ll + [ll[0]]
  return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"

def parcel(apn, address, pts):
  cx = sum(p[0] for p in pts) / len(pts)
  cy = sum(p[1] for p in pts) / len(pts)
  lng, lat = PROJ.to_ll((cx, cy))
  return {"apn": apn, "address": address, "lat": lat, "lng": lng, "boundary": wkt(pts)}

def rect(x0, y0, x1, y1):
  return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

SUBJ = rect(-50, -60, 50, 60)
W = parcel("W-1", "90 Main St Sunnyvale CA", rect(-150, -60, -50, 60))
E = parcel("E-1", "110 Main St Sunnyvale CA", rect(50, -60, 150, 60))
N = parcel("N-1", "101 Oak Ave Sunnyvale CA", rect(-50, 60, 50, 180))
S = parcel("S-1", "80 Main St Sunnyvale CA", rect(-50, -180, 50, -60))
subject = parcel("SUBJ", "100 Main St Sunnyvale CA", SUBJ)

PED = {"rule": "all_fronts", "condition": "pedestrian_oriented_district",
       "citation": "SJMC 20.200.670(B)", "zone_codes": ["MS-G", "MS-C"]}
OVERSIZE = {"rule": "all_fronts", "condition": "oversized_corner_lot",
            "citation": "SJMC 20.200.670(A)",
            "thresholds_ft": {"residential": 120, "commercial": 150}}

cases = []
def add(name, **kw):
  case = {"name": name, "subject": kw.pop("subject", subject),
          "neighbors": kw.pop("neighbors", [W, E, N])}
  case.update(kw)
  cases.append(case)

RULES = ["shortest_frontage", "address_street", "designated", "owner_elected", "all_fronts"]

# Fixed scenarios across every rule.
for r in RULES:
  add(f"midblock/{r}", frontRule=r)
  add(f"corner/{r}", neighbors=[E, N], frontRule=r)
  add(f"through/{r}", neighbors=[W, E], frontRule=r)
  add(f"landlocked/{r}", neighbors=[W, E, N, S], frontRule=r)
  add(f"corner-addressed-oak/{r}", neighbors=[E, N], frontRule=r,
      subject=parcel("SUBJ", "5 Oak Ave Sunnyvale CA", SUBJ))

# No rule at all (engine default).
add("corner/default-rule", neighbors=[E, N])
add("midblock/default-rule")

# Override matrix.
for zone in [None, {"zone_code": "MS-G", "zone_type": "commercial"},
             {"zone_code": "R-1", "zone_type": "residential"},
             {"zone_code": "MS-C", "zone_type": "residential"},
             {"zone_type": "residential"}, {"zone_code": "DC"}]:
  add(f"corner/ped-override/{zone}", neighbors=[E, N],
      frontRule="shortest_frontage", frontRuleOverrides=[PED], zone=zone)
  add(f"corner/oversize-override/{zone}", neighbors=[E, N],
      frontRule="shortest_frontage", frontRuleOverrides=[OVERSIZE], zone=zone)
  add(f"corner/both-overrides/{zone}", neighbors=[E, N],
      frontRule="shortest_frontage", frontRuleOverrides=[OVERSIZE, PED], zone=zone)

# A genuinely oversized corner lot (both frontages > 120 ft residential).
BIG = rect(-90, -80, 90, 80)
big_subject = parcel("SUBJ", "100 Main St Sunnyvale CA", BIG)
big_e = parcel("E-1", "110 Main St Sunnyvale CA", rect(90, -80, 250, 80))
big_n = parcel("N-1", "101 Oak Ave Sunnyvale CA", rect(-90, 80, 90, 240))
for zone in [{"zone_code": "R-1", "zone_type": "residential"},
             {"zone_code": "R-1", "zone_type": "commercial"}]:
  add(f"oversized-corner/{zone}", subject=big_subject, neighbors=[big_e, big_n],
      frontRule="shortest_frontage", frontRuleOverrides=[OVERSIZE], zone=zone)

# Owner elections at every index.
for i in range(6):
  add(f"corner/elect-{i}", neighbors=[E, N], frontRule="owner_elected",
      userFrontOverrideEdgeIndex=i)

# Missing addresses (blind census -> geometric fallback).
W_anon = dict(W, address="")
E_anon = dict(E, address="")
N_anon = dict(N, address="")
add("corner/anonymous-neighbors", neighbors=[E_anon, N_anon], frontRule="address_street")
add("midblock/anonymous-neighbors", neighbors=[W_anon, E_anon, N_anon])
add("corner/anon-subject", neighbors=[E, N],
    subject=parcel("SUBJ", "", SUBJ), frontRule="address_street")

# Cul-de-sac: an arc frontage must stay ONE edge.
arc = [(-50, 60), (-50, 0)]
for k in range(19):
  a = math.pi * (1.0 - k / 18.0)
  arc.append((60 * math.cos(a) * -1, -60 + 0 * k) if False else (50 * math.cos(math.pi - a), -60 + 0))
arc = [(-50, 60), (-50, -20)]
for k in range(25):
  th = math.pi * (1 - k / 24)
  arc.append((55 * math.cos(th), -20 - 55 * math.sin(th)))
arc.append((50, 60))
cds_subject = parcel("SUBJ", "100 Court Ct Sunnyvale CA", arc)
cds_w = parcel("W-1", "90 Court Ct Sunnyvale CA", rect(-150, -20, -50, 60))
cds_e = parcel("E-1", "110 Court Ct Sunnyvale CA", rect(50, -20, 150, 60))
cds_n = parcel("N-1", "101 Oak Ave Sunnyvale CA", rect(-50, 60, 50, 180))
add("cul-de-sac", subject=cds_subject, neighbors=[cds_w, cds_e, cds_n])
add("cul-de-sac/shortest", subject=cds_subject, neighbors=[cds_w, cds_e, cds_n],
    frontRule="shortest_frontage")

# Rounded block corner with no names (geometric fallback split).
fillet = [(-50, 60), (-50, -45)]
for k in range(9):
  th = math.pi * (1 + k / 8 * 0.5)
  fillet.append((-35 + 15 * math.cos(th), -45 + 15 * math.sin(th)))
fillet += [(50, -60), (50, 60)]
add("rounded-corner/anon", subject=parcel("SUBJ", "100 Main St Sunnyvale CA", fillet),
    neighbors=[parcel("N-1", "", rect(-50, 60, 50, 180))])

# Randomized quadrilaterals with random neighbor subsets.
rng = random.Random(20260830)
def jitter(p, m=6):
  return (p[0] + rng.uniform(-m, m), p[1] + rng.uniform(-m, m))
for t in range(40):
  pts = [jitter((-50, -60)), jitter((50, -60)), jitter((50, 60)), jitter((-50, 60))]
  sub = parcel("SUBJ", rng.choice(["100 Main St Sunnyvale CA", "5 Oak Ave Sunnyvale CA", ""]), pts)
  pool = [W, E, N, S]
  chosen = [p for p in pool if rng.random() < 0.6]
  add(f"random-{t}", subject=sub, neighbors=chosen, frontRule=rng.choice(RULES + [None]),
      zone=rng.choice([None, {"zone_code": "MS-G", "zone_type": "commercial"},
                       {"zone_code": "R-1", "zone_type": "residential"}]),
      frontRuleOverrides=rng.choice([None, [PED], [OVERSIZE], [OVERSIZE, PED]]))

# Survey spike on a SHARED boundary: the north edge carries a thin sliver that
# doubles back, which must be flagged and must NOT split the edge.
spike_ring = [(-50, -60), (50, -60), (50, 60), (1, 60), (0.5, 120), (0, 60), (-50, 60)]
spike_nb = [(-50, 60), (0, 60), (0.5, 120), (1, 60), (50, 60), (50, 180), (-50, 180)]
spike_subject = parcel("SUBJ", "100 Main St Sunnyvale CA", spike_ring)
spike_neighbor = parcel("N-1", "101 Oak Ave Sunnyvale CA", spike_nb)
add("spike/shared-north", subject=spike_subject, neighbors=[W, E, spike_neighbor])
add("spike/shared-north/shortest", subject=spike_subject,
    neighbors=[W, E, spike_neighbor], frontRule="shortest_frontage")

cases = [{k: v for k, v in c.items() if v is not None} for c in cases]
json.dump(cases, open("cases.json", "w"))
print(f"{len(cases)} cases")
