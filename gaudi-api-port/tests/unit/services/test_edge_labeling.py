"""Unit tests for parcel edge labeling.

Lots are built in local feet around a fixed origin and converted to WKT with
the module's own projection, so each test states the geometry it means rather
than carrying opaque coordinate strings.

Reference lot, 100 ft (E-W) x 120 ft (N-S), centred on the origin:

      (-50, 60) +-----------------+ (50, 60)
                |                 |
                |     subject     |
                |                 |
     (-50, -60) +-----------------+ (50, -60)

Neighbours are placed beyond whichever edges are meant to be shared; every
remaining edge falls to a road gap.
"""
from typing import List, Optional, Sequence, Tuple

import pytest

from services.compute.parcel_edges.edge_labeling import (
  DEFAULT_CONFIG,
  EdgeLabelingConfig,
  EdgeLabelingInput,
  FrontRuleOverride,
  ZoneomicsParcel,
  label_edges,
)
from services.compute.parcel_edges.geometry import make_projection, round_half_up
from services.compute.parcel_edges.street_names import extract_street_name

ORIGIN_LNG = -122.1
ORIGIN_LAT = 37.4
PROJ = make_projection(ORIGIN_LNG, ORIGIN_LAT)

Ft = Tuple[float, float]


def _wkt(pts_ft: Sequence[Ft]) -> str:
  """Local-feet rectangle -> EPSG:4326 WKT POLYGON, closed."""
  ll = [PROJ.to_ll(p) for p in pts_ft]
  ring = ll + [ll[0]]
  coords = ", ".join(f"{lng} {lat}" for lng, lat in ring)
  return f"POLYGON(({coords}))"


def _rect(x0: float, y0: float, x1: float, y1: float) -> List[Ft]:
  return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _parcel(apn: str, address: str, pts_ft: Sequence[Ft]) -> ZoneomicsParcel:
  """Build a parcel whose lat/lng is its own centroid, as Zoneomics reports."""
  cx = sum(p[0] for p in pts_ft) / len(pts_ft)
  cy = sum(p[1] for p in pts_ft) / len(pts_ft)
  lng, lat = PROJ.to_ll((cx, cy))
  return ZoneomicsParcel(apn=apn, address=address, lat=lat, lng=lng, boundary=_wkt(pts_ft))


SUBJECT_PTS = _rect(-50, -60, 50, 60)
WEST_NEIGHBOR = _parcel("W-1", "90 Main St Sunnyvale CA", _rect(-150, -60, -50, 60))
EAST_NEIGHBOR = _parcel("E-1", "110 Main St Sunnyvale CA", _rect(50, -60, 150, 60))
NORTH_NEIGHBOR = _parcel("N-1", "101 Oak Ave Sunnyvale CA", _rect(-50, 60, 50, 180))


def _subject(address: str = "100 Main St Sunnyvale CA") -> ZoneomicsParcel:
  return _parcel("SUBJ", address, SUBJECT_PTS)


def _label(neighbors: List[ZoneomicsParcel], **kwargs):
  return label_edges(EdgeLabelingInput(
    subject=kwargs.pop("subject", _subject()),
    neighbors=neighbors,
    **kwargs,
  ))


def _by_tag(result, tag: str):
  return [e for e in result.edges if e.tag == tag]


# --- street name extraction ---------------------------------------------------

@pytest.mark.parametrize("address,expected", [
  ("804 Lennox Ct Sunnyvale CA", "lennox ct"),
  ("100 Main Street Sunnyvale CA", "main st"),
  ("22 Grand Avenue", "grand ave"),
  ("22 Grand Av", "grand ave"),
  ("22 GRAND AVE.", "grand ave"),
  ("1234 El Camino Real Menlo Park", "el camino real"),
  ("100 1/2 Main St", "main st"),
  ("", None),
  ("   ", None),
  ("742", None),
])
def test_extract_street_name(address: Optional[str], expected: Optional[str]) -> None:
  assert extract_street_name(address) == expected


def test_unit_suffixed_house_number_is_not_stripped() -> None:
  """Known limitation, carried over from the reference implementation.

  The house-number test accepts digits, slashes, and hyphens only, so a unit
  suffix ("1234-B") is not recognized as a number and leaks into the street
  key. Both sides of a census compare the same way, so two neighbours on the
  same street still agree unless exactly one of them carries a unit suffix.
  Fixing it would change labeling behavior and belongs in a separate change.
  """
  assert extract_street_name("1234-B El Camino Real Menlo Park") == "1234-b el camino"


def test_extract_street_name_canonicalizes_variants_to_one_key() -> None:
  keys = {extract_street_name(a) for a in
          ("1 Oak Ave Napa", "2 Oak Avenue Napa", "3 Oak Av Napa")}
  assert keys == {"oak ave"}


# --- rounding -----------------------------------------------------------------

def test_round_half_up_does_not_use_bankers_rounding() -> None:
  assert round_half_up(0.25) == 0.3
  assert round_half_up(0.35) == 0.4
  assert round(0.25, 1) == 0.2  # the behavior we are deliberately avoiding


# --- mid-block lot ------------------------------------------------------------

def test_midblock_lot_has_one_front_one_rear_two_sides() -> None:
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR])

  fronts = _by_tag(result, "front")
  assert len(fronts) == 1
  front = fronts[0]
  assert front.abuts.kind == "street"
  assert front.abuts.street_name == "main st"
  assert front.basis == "single_frontage"
  assert front.confidence == "high"
  assert front.length_ft == pytest.approx(100, abs=1)

  assert len(_by_tag(result, "rear")) == 1
  assert len(_by_tag(result, "side")) == 2
  assert result.stats.road_gaps == 1
  assert result.stats.neighbors_touching == 3


def test_midblock_rear_is_the_edge_opposite_the_front() -> None:
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR])
  rear = _by_tag(result, "rear")[0]
  assert rear.abuts.kind == "parcels"
  assert rear.abuts.apns == ["N-1"]


def test_single_frontage_wins_regardless_of_jurisdiction_rule() -> None:
  for rule in ("shortest_frontage", "designated", "owner_elected", "all_fronts"):
    result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR], front_rule=rule)
    fronts = _by_tag(result, "front")
    assert len(fronts) == 1, rule
    assert fronts[0].basis == "single_frontage", rule


def test_edges_tile_the_whole_boundary() -> None:
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR])
  perimeter = 2 * (100 + 120)
  assert sum(e.length_ft for e in result.edges) == pytest.approx(perimeter, abs=2)


# --- corner lot ---------------------------------------------------------------

def _corner_result(**kwargs):
  """Corner lot: street to the south (Main) and to the west (Oak)."""
  return _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], **kwargs)


def test_corner_lot_splits_the_gap_into_two_named_frontages() -> None:
  result = _corner_result()
  street_edges = [e for e in result.edges if e.abuts.kind == "street"]
  assert len(street_edges) == 2
  assert {e.abuts.street_name for e in street_edges} == {"main st", "oak ave"}
  assert sorted(result.stats.street_names) == ["main st", "oak ave"]


def test_corner_lot_front_follows_the_address_street_by_default() -> None:
  result = _corner_result()
  front = _by_tag(result, "front")[0]
  assert front.abuts.street_name == "main st"
  assert front.basis == "address_match"
  assert front.confidence == "high"

  street_sides = _by_tag(result, "street_side")
  assert len(street_sides) == 1
  assert street_sides[0].abuts.street_name == "oak ave"


def test_shortest_frontage_rule_picks_the_shorter_street_edge() -> None:
  # South frontage is 100 ft, west frontage 120 ft, so the front moves to Main
  # by geometry rather than by the address.
  result = _corner_result(front_rule="shortest_frontage")
  front = _by_tag(result, "front")[0]
  assert front.basis == "jurisdiction_rule"
  assert front.abuts.street_name == "main st"


def test_shortest_frontage_disagreeing_with_the_address_lowers_confidence() -> None:
  # Address the subject off the LONGER (west/Oak) frontage; the rule still
  # takes the shorter one, and the disagreement is reported as medium.
  result = _corner_result(subject=_parcel("SUBJ", "5 Oak Ave Sunnyvale CA", SUBJECT_PTS),
                          front_rule="shortest_frontage")
  front = _by_tag(result, "front")[0]
  assert front.abuts.street_name == "main st"
  assert front.confidence == "medium"


def test_designated_rule_flags_the_lot_for_review() -> None:
  result = _corner_result(front_rule="designated")
  front = _by_tag(result, "front")[0]
  assert front.confidence == "low"
  assert "front_requires_review" in result.flags


def test_all_fronts_marks_the_secondary_frontage_as_a_second_front() -> None:
  result = _corner_result(front_rule="all_fronts")
  assert "second_front_jurisdiction" in result.flags
  street_side = _by_tag(result, "street_side")[0]
  assert "second_front" in street_side.flags
  assert _by_tag(result, "front")[0].confidence == "medium"


def test_owner_elected_marks_street_edges_electable_and_honors_an_election() -> None:
  result = _corner_result(front_rule="owner_elected")
  assert all("owner_electable" in e.flags
             for e in result.edges if e.abuts.kind == "street")
  default_front = _by_tag(result, "front")[0]
  assert default_front.abuts.street_name == "main st"
  assert default_front.basis == "address_match"

  oak_index = next(i for i, e in enumerate(result.edges)
                   if e.abuts.kind == "street" and e.abuts.street_name == "oak ave")
  elected = _corner_result(front_rule="owner_elected",
                           user_front_override_edge_index=oak_index)
  elected_front = _by_tag(elected, "front")[0]
  assert elected_front.abuts.street_name == "oak ave"
  assert elected_front.basis == "user_override"
  assert elected_front.confidence == "high"


def test_out_of_range_election_index_falls_back_without_raising() -> None:
  result = _corner_result(front_rule="owner_elected", user_front_override_edge_index=99)
  front = _by_tag(result, "front")[0]
  assert front.basis == "address_match"


# --- jurisdiction overrides ---------------------------------------------------

PEDESTRIAN_OVERRIDE = FrontRuleOverride(
  rule="all_fronts",
  condition="pedestrian_oriented_district",
  zone_codes=["MS-G", "MS-C"],
)
OVERSIZED_OVERRIDE = FrontRuleOverride(
  rule="all_fronts",
  condition="oversized_corner_lot",
  thresholds_ft={"residential": 120, "commercial": 150},
)


def test_pedestrian_district_override_replaces_the_base_rule() -> None:
  result = _corner_result(front_rule="shortest_frontage",
                          front_rule_overrides=[PEDESTRIAN_OVERRIDE],
                          zone={"zone_code": "MS-G", "zone_type": "commercial"})
  assert "front_rule_override_applied" in result.flags
  assert "second_front_jurisdiction" in result.flags
  assert "second_front" in _by_tag(result, "street_side")[0].flags


def test_pedestrian_district_override_does_not_fire_for_other_zones() -> None:
  result = _corner_result(front_rule="shortest_frontage",
                          front_rule_overrides=[PEDESTRIAN_OVERRIDE],
                          zone={"zone_code": "R-1", "zone_type": "residential"})
  assert "front_rule_override_applied" not in result.flags
  assert "second_front_jurisdiction" not in result.flags
  assert _by_tag(result, "front")[0].basis == "jurisdiction_rule"


def test_oversized_override_needs_every_frontage_over_the_threshold() -> None:
  # Frontages are 100 ft and 120 ft against a 120 ft residential threshold, so
  # neither "both exceed" nor the override applies.
  result = _corner_result(front_rule="shortest_frontage",
                          front_rule_overrides=[OVERSIZED_OVERRIDE],
                          zone={"zone_code": "R-1", "zone_type": "residential"})
  assert "front_rule_override_applied" not in result.flags


def test_unevaluable_override_falls_back_to_the_address_street_default() -> None:
  # No zone info at all: the condition cannot be evaluated, so the base rule is
  # in doubt and the engine reverts to address_street, flagging why.
  result = _corner_result(front_rule="shortest_frontage",
                          front_rule_overrides=[PEDESTRIAN_OVERRIDE],
                          zone=None)
  assert "front_rule_override_unevaluated" in result.flags
  assert "front_rule_override_applied" not in result.flags
  front = _by_tag(result, "front")[0]
  assert front.basis == "address_match"
  assert front.abuts.street_name == "main st"


def test_overrides_are_ignored_on_a_single_frontage_lot() -> None:
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR],
                  front_rule="shortest_frontage",
                  front_rule_overrides=[PEDESTRIAN_OVERRIDE],
                  zone=None)
  assert "front_rule_override_unevaluated" not in result.flags
  assert _by_tag(result, "front")[0].basis == "single_frontage"


def test_override_records_round_trip_from_the_jurisdiction_db_shape() -> None:
  override = FrontRuleOverride.from_db({
    "rule": "all_fronts",
    "condition": "pedestrian_oriented_district",
    "citation": "SJMC 20.200.670(B)",
    "description": "two front lot lines regardless of lot dimensions",
    "zone_codes": ["MS-G", "MS-C"],
  })
  assert override.rule == "all_fronts"
  assert override.zone_codes == ["MS-G", "MS-C"]
  result = _corner_result(front_rule="shortest_frontage",
                          front_rule_overrides=[override],
                          zone={"zone_code": "ms-g", "zone_type": "commercial"})
  assert "front_rule_override_applied" in result.flags


# --- through lot --------------------------------------------------------------

def test_through_lot_tags_the_opposite_frontage_rear() -> None:
  # Streets north and south, neighbours east and west only.
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR])
  assert "through_lot" in result.flags
  rear = _by_tag(result, "rear")[0]
  assert rear.abuts.kind == "street"


def test_obtuse_corner_lot_is_not_a_through_lot() -> None:
  """Adjacent street frontages meeting at an obtuse corner stay a corner lot.

  Regression (2026-08-30, 1200 Birch Ave San Mateo): a diagonal frontage's
  aggregate normal sits ~130° from the side street's, so the normals-only test
  read the pair as opposite sides and tagged the side street rear/through_lot.
  Street edges that MEET at a corner are a corner lot; rear must fall to the
  shared edge most opposite the front instead.

        D (-50, 80)
         \\            <- diagonal street frontage D-C
    street|  \\
     D-A  |    C (50, 0)
          |    | neighbour E-2
        A +----+ B
          neighbour S-2 below A-B
  """
  subject = _parcel("SUBJ", "100 Diag St Sunnyvale CA",
                    [(-50, -60), (50, -60), (50, 0), (-50, 80)])
  south = _parcel("S-2", "80 Main St Sunnyvale CA", _rect(-50, -180, 50, -60))
  east = _parcel("E-2", "110 Oak Ave Sunnyvale CA", _rect(50, -60, 150, 0))
  result = _label([south, east], subject=subject)

  assert "through_lot" not in result.flags
  assert not [e for e in _by_tag(result, "rear") if e.abuts.kind == "street"]
  street_tags = sorted(e.tag for e in result.edges if e.abuts.kind == "street")
  assert street_tags == ["front", "street_side"]
  rear = _by_tag(result, "rear")
  assert rear and rear[0].abuts.kind == "parcels"


# --- landlocked lot -----------------------------------------------------------

def test_landlocked_lot_is_flagged_and_still_returns_edges() -> None:
  south = _parcel("S-1", "80 Main St Sunnyvale CA", _rect(-50, -180, 50, -60))
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR, south])
  assert "no_street_frontage" in result.flags
  assert result.stats.road_gaps == 0
  assert result.edges
  assert all(e.abuts.kind == "parcels" for e in result.edges)
  assert _by_tag(result, "front")[0].confidence == "low"


# --- serialization ------------------------------------------------------------

def test_to_dict_matches_the_established_wire_shape() -> None:
  payload = _corner_result().to_dict()
  assert set(payload) == {"edges", "flags", "stats"}
  assert set(payload["stats"]) == {"roadGaps", "streetNames", "neighborsTouching"}
  edge = payload["edges"][0]
  assert set(edge) == {"pts", "tag", "abuts", "lengthFt", "basis", "confidence", "flags"}
  assert all(len(p) == 2 for p in edge["pts"])
  street = next(e for e in payload["edges"] if e["abuts"]["kind"] == "street")
  assert "streetName" in street["abuts"]
  parcels = next(e for e in payload["edges"] if e["abuts"]["kind"] == "parcels")
  assert isinstance(parcels["abuts"]["apns"], list)


# --- config -------------------------------------------------------------------

def test_config_defaults_match_the_reference_implementation() -> None:
  assert DEFAULT_CONFIG.snap_tolerance_ft == 1.0
  assert DEFAULT_CONFIG.attribution_step_ft == 5
  assert DEFAULT_CONFIG.vertex_dedupe_ft == 0.5
  assert DEFAULT_CONFIG.arm_length_ft == 10
  assert DEFAULT_CONFIG.corner_min_deg == 45
  assert DEFAULT_CONFIG.corner_max_deg == 170
  assert DEFAULT_CONFIG.gap_probe_ft == 8
  assert DEFAULT_CONFIG.rear_tie_epsilon == 0.1
  assert DEFAULT_CONFIG.road_gap_corner_min_deg == 60
  assert DEFAULT_CONFIG.min_wing_ft == 25
  assert DEFAULT_CONFIG.block_face_lateral_ft == 12
  assert DEFAULT_CONFIG.block_face_angle_deg == 15
  assert DEFAULT_CONFIG.rear_dot_threshold == 0.3


def test_a_partial_config_override_is_applied() -> None:
  tight = EdgeLabelingConfig(attribution_step_ft=2.5)
  result = label_edges(EdgeLabelingInput(
    subject=_subject(),
    neighbors=[WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR],
    config=tight,
  ))
  assert len(_by_tag(result, "front")) == 1


# --- robustness ---------------------------------------------------------------

def test_unparseable_neighbor_boundary_is_dropped_not_fatal() -> None:
  broken = ZoneomicsParcel(apn="X-1", address="1 Broken St", lat=ORIGIN_LAT,
                           lng=ORIGIN_LNG, boundary="NOT WKT AT ALL")
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR, broken])
  assert len(_by_tag(result, "front")) == 1
  assert "X-1" not in {a for e in result.edges for a in e.abuts.apns}


def test_unparseable_subject_boundary_raises() -> None:
  subject = ZoneomicsParcel(apn="SUBJ", address="100 Main St", lat=ORIGIN_LAT,
                            lng=ORIGIN_LNG, boundary="NOT WKT AT ALL")
  with pytest.raises(ValueError):
    label_edges(EdgeLabelingInput(subject=subject, neighbors=[]))


def test_the_subject_is_skipped_if_it_appears_among_its_own_neighbors() -> None:
  subject = _subject()
  result = _label([WEST_NEIGHBOR, EAST_NEIGHBOR, NORTH_NEIGHBOR, subject],
                  subject=subject)
  assert "SUBJ" not in {a for e in result.edges for a in e.abuts.apns}


# --- street namer (Google Roads) merge ------------------------------------------

from services.compute.parcel_edges.street_naming import RoadName


def _namer_returning(mapping):
  """Fake StreetNamer: names each midpoint by which half-plane it falls in.

  mapping: list of (predicate on (lng, lat), key) — first hit wins.
  """
  def name_points(points):
    out = []
    for lng, lat in points:
      x, y = PROJ.to_ft((lng, lat))
      hit = None
      for predicate, key in mapping:
        if predicate(x, y):
          hit = RoadName(key=key, display=key.title(), distance_ft=10.0, place_id="p-" + key)
          break
      out.append(hit)
    return out
  return name_points


# South frontage (y < -55) is Main St; west frontage (x < -45) is Oak Ave.
_CORNER_NAMER = _namer_returning([
  (lambda x, y: y < -55, "main st"),
  (lambda x, y: x < -45, "oak ave"),
])


def test_namer_names_frontages_and_marks_provenance() -> None:
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], street_namer=_CORNER_NAMER)
  street = [e for e in result.edges if e.abuts.kind == "street"]
  assert {e.abuts.street_name for e in street} == {"main st", "oak ave"}
  assert all(e.abuts.street_name_source == "roads" for e in street)


def test_namer_beats_a_disagreeing_census() -> None:
  # Neighbours' addresses all say Main St, but the namer says the west
  # frontage is Oak Ave — the road itself outranks mailing addresses.
  west_lying = _parcel("N-1", "99 Main St Sunnyvale CA", _rect(-50, 60, 50, 180))
  result = _label([EAST_NEIGHBOR, west_lying], street_namer=_CORNER_NAMER)
  west = next(e for e in result.edges
              if e.abuts.kind == "street" and e.abuts.street_name == "oak ave")
  assert west.abuts.street_name_source == "roads"


def test_census_fills_where_the_namer_is_silent() -> None:
  # Namer only knows the south frontage; the west one falls back to census.
  south_only = _namer_returning([(lambda x, y: y < -55, "main st")])
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], street_namer=south_only)
  by_name = {e.abuts.street_name: e for e in result.edges if e.abuts.kind == "street"}
  assert by_name["main st"].abuts.street_name_source == "roads"
  assert by_name["oak ave"].abuts.street_name_source == "census"


def test_namer_rescues_anonymous_neighbors() -> None:
  # No situs addresses anywhere: census is blind, namer still names both
  # frontages and the corner still splits into two named edges.
  anon = [_parcel("E-1", "", _rect(50, -60, 150, 60)),
          _parcel("N-1", "", _rect(-50, 60, 50, 180))]
  blind = _label(anon, subject=_parcel("SUBJ", "", SUBJECT_PTS))
  named = _label(anon, subject=_parcel("SUBJ", "", SUBJECT_PTS), street_namer=_CORNER_NAMER)
  assert "unknown_street_name" in blind.flags
  assert "unknown_street_name" not in named.flags
  assert sorted(named.stats.street_names) == ["main st", "oak ave"]


def test_a_throwing_namer_degrades_to_census_and_flags() -> None:
  def broken(points):
    raise RuntimeError("Roads API down")
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], street_namer=broken)
  assert "street_namer_failed" in result.flags
  street = [e for e in result.edges if e.abuts.kind == "street"]
  assert {e.abuts.street_name for e in street} == {"main st", "oak ave"}
  assert all(e.abuts.street_name_source == "census" for e in street)


def test_a_wrong_length_namer_result_degrades_and_flags() -> None:
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], street_namer=lambda points: [])
  assert "street_namer_failed" in result.flags
  assert len([e for e in result.edges if e.abuts.kind == "street"]) == 2


def test_no_namer_output_is_unchanged_and_carries_census_provenance() -> None:
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR])
  street = [e for e in result.edges if e.abuts.kind == "street"]
  assert all(e.abuts.street_name_source == "census" for e in street)


# --- authoritative subject street (Google Places route) --------------------------

def test_subject_street_name_overrides_the_situs_parse() -> None:
  # Situs address is unit-suffixed garbage; the Google route resolves the front.
  subject = _parcel("SUBJ", "1234-B El Camino Real Menlo Park", SUBJECT_PTS)
  without = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], subject=subject)
  with_route = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], subject=subject,
                      subject_street_name="Main Street")
  assert _by_tag(without, "front")[0].basis != "address_match"
  front = _by_tag(with_route, "front")[0]
  assert front.basis == "address_match"
  assert front.abuts.street_name == "main st"


def test_subject_street_name_is_normalized_before_matching() -> None:
  result = _label([EAST_NEIGHBOR, NORTH_NEIGHBOR], subject_street_name="MAIN   STREET")
  assert _by_tag(result, "front")[0].abuts.street_name == "main st"


# --- shared normalizer guarantees ------------------------------------------------

def test_the_matcher_rejects_toms_four_false_positives() -> None:
  from services.compute.parcel_edges.street_names import (
    normalize_street_key as key, street_keys_match as match)
  assert not match(key("Oakland Ave"), key("Oak Ave"))
  assert not match(key("Oak St"), key("Oak Ave"))
  assert not match(key("N Main St"), key("S Main St"))
  assert not match(key("Parkway Dr"), key("Elm St"))
  assert match(key("Madrono AV"), key("Madrono Avenue"))
  assert match(key("North Main Street"), key("N Main St"))
