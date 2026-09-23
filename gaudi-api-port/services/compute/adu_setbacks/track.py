"""
track.py
--------
Which regime governs the proposed unit: the state track or the local track.

The state track is Gov. Code § 66323(a)(2): one detached, new-construction ADU
on a lot with a single-family dwelling, which the local agency must approve
under state standards only. The city may condition it on at most 800 sq ft of
interior livable space and the § 66321(b)(4) height (HCD ADU Handbook, March
2026, p. 16). Anything outside that box is a § 66314 unit, reviewed under the
local ordinance — Phase B, not built here.

Height: 16 ft qualifies anywhere; 18 ft qualifies when the lot is within a
half-mile of a major transit stop or high-quality transit corridor (p. 24).
The statute's extra 2 ft for a roof pitch matching the primary dwelling is
deliberately NOT modelled (decision 2026-09-23): above 18 ft the unit goes to
the local track and a human adjusts in the Gaudi UI if the allowance applies.

Every Q1 gate the engine does not evaluate (residential zone, single-family
dwelling, SB 9 split, existing detached ADU) is surfaced as a flag so the UI can
say what was assumed. FOR-1419/1420/1421 replace those assumptions with data;
FOR-1422 refines the transit test from a straight-line buffer to walking distance.
"""
from dataclasses import dataclass, field
from typing import List, Optional

TRACK_STATE_66323 = 'state_66323'
TRACK_LOCAL_66314 = 'local_66314'

# § 66323(a)(2)(A): the local agency may cap the state-track unit at 800 sq ft
# of interior livable space (Handbook p. 16, p. 38). Every jurisdiction in the
# database does.
STATE_TRACK_MAX_UNIT_SIZE_SQFT = 800.0
# § 66321(b)(4)(A): the base detached height a city must allow.
STATE_HEIGHT_BASE_FT = 16.0
# § 66321(b)(4)(B): 18 ft within a half-mile of a major transit stop or HQ corridor.
STATE_HEIGHT_TRANSIT_FT = 18.0

CITATION_SIZE = 'Gov. Code § 66323(a)(2)(A); HCD ADU Handbook (Mar 2026) p. 16, p. 38'
CITATION_HEIGHT = 'Gov. Code § 66321(b)(4)(A)-(B); HCD ADU Handbook (Mar 2026) p. 24'
CITATION_ONE_PER_LOT = 'Gov. Code § 66323(a)(2); HCD ADU Handbook (Mar 2026) pp. 16-18'


@dataclass(frozen=True)
class UnitFacts:
  """The proposed unit, the transit fact, and the two lot facts the UI asks for.

  Both unit numbers are required: they are eligibility conditions, not
  refinements. gaudi-api has no unit height yet, so for now both are typed in.
  """
  unit_size: float
  unit_height_in_feet: float
  # Lot within a half-mile HQ transit area (services.parcel_data.ca_transit_client).
  # None = lookup failed; the 18 ft allowance is then not granted, and flagged.
  near_transit: Optional[bool] = None
  # Q1 gates that are manual for now (default no). See FOR-1420 / FOR-1421.
  sb9_split: bool = False
  existing_detached_adu: bool = False


@dataclass
class TrackDecision:
  track: str
  # Why the unit is (not) on the state track, in evaluation order.
  reasons: List[str] = field(default_factory=list)
  # Assumptions and unresolved gates, for the UI. Never silent.
  flags: List[str] = field(default_factory=list)
  citations: List[str] = field(default_factory=list)

  def to_dict(self) -> dict:
    return {'track': self.track, 'reasons': list(self.reasons), 'flags': list(self.flags),
            'citations': list(self.citations)}


def _q1_assumption_flags(unit: UnitFacts) -> List[str]:
  """The Q1 gates the engine assumes rather than checks (see FOR-1419/1420/1421)."""
  flags = ['zone_use_assumed_residential', 'dwelling_type_assumed_sfr']
  if unit.sb9_split:
    # Per FOR-1420: a split parcel is assumed to hold one unit and no ADU yet,
    # so one ADU is still allowed; the unit count is not verified.
    flags.append('sb9_split_declared_unit_count_unverified')
  else:
    flags.append('sb9_split_assumed_no')
  if not unit.existing_detached_adu:
    flags.append('existing_detached_adu_assumed_no')
  return flags


def state_height_limit_ft(near_transit: Optional[bool]) -> float:
  """The tallest detached unit the state track admits on this lot."""
  return STATE_HEIGHT_TRANSIT_FT if near_transit else STATE_HEIGHT_BASE_FT


def determine_track(unit: UnitFacts) -> TrackDecision:
  """Decide the track for a detached, new-construction ADU.

  @param unit The unit facts. ``unit_size`` and ``unit_height_in_feet`` must be
    positive numbers; the caller validates and rejects anything else.

  @return The track, the reasons, and the assumption flags.
  """
  assert unit.unit_size > 0, 'unit_size must be positive'
  assert unit.unit_height_in_feet > 0, 'unit_height_in_feet must be positive'

  decision = TrackDecision(track=TRACK_STATE_66323, flags=_q1_assumption_flags(unit),
                           citations=[CITATION_SIZE, CITATION_HEIGHT, CITATION_ONE_PER_LOT])

  # The (a)(2) entitlement is one per lot; a second detached unit is a § 66314 unit.
  if unit.existing_detached_adu:
    decision.track = TRACK_LOCAL_66314
    decision.reasons.append('a2_entitlement_already_used')
    decision.flags.append('existing_detached_adu_declared')

  if unit.unit_size > STATE_TRACK_MAX_UNIT_SIZE_SQFT:
    decision.track = TRACK_LOCAL_66314
    decision.reasons.append('unit_size_over_800_sqft')

  height_limit = state_height_limit_ft(unit.near_transit)
  if unit.near_transit is None:
    decision.flags.append('transit_lookup_failed')
  elif unit.near_transit:
    # The HQ transit areas are straight-line half-mile buffers; the statute says
    # walking distance. Superset, so a pass here is probable, not proven (FOR-1422).
    decision.flags.append('transit_straight_line_buffer')
  if unit.unit_height_in_feet > height_limit:
    decision.track = TRACK_LOCAL_66314
    decision.reasons.append('unit_height_over_%d_ft' % int(height_limit))

  if decision.track == TRACK_STATE_66323:
    decision.reasons.append('fits_66323_a2')
  return decision
