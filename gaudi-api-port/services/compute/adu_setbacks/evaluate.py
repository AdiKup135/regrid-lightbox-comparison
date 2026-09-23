"""
evaluate.py
-----------
The Phase A pipeline in one call: track → per-edge state-track values → envelope.

Takes the already-labeled edges (the caller runs the edge labeler the same way
/edges/label does) so this module stays free of the data-provider and
street-naming machinery.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .offset import setback_polygon
from .state_track import state_track_setbacks
from .track import TRACK_STATE_66323, TrackDecision, UnitFacts, determine_track, state_height_limit_ft


@dataclass
class AduEvaluation:
  track: TrackDecision
  unit: UnitFacts
  # Labeled edges, each with its setback merged in (setback_ft, setback_basis) on the state track.
  edges: List[Dict] = field(default_factory=list)
  setback_polygon_wkt: Optional[str] = None
  setback_polygon_area_sqft: Optional[float] = None
  flags: List[str] = field(default_factory=list)

  def to_dict(self) -> Dict:
    return {
      'phase': 'A',
      'track': self.track.track,
      'track_reasons': list(self.track.reasons),
      'state_height_limit_ft': state_height_limit_ft(self.unit.near_transit),
      'unit': {'unit_size': self.unit.unit_size, 'unit_height_in_feet': self.unit.unit_height_in_feet,
               'near_transit': self.unit.near_transit, 'sb9_split': self.unit.sb9_split,
               'existing_detached_adu': self.unit.existing_detached_adu},
      'edges': self.edges,
      'setback_polygon': self.setback_polygon_wkt,
      'setback_polygon_area_sqft': self.setback_polygon_area_sqft,
      'flags': list(self.flags),
      'citations': list(self.track.citations),
    }


def evaluate_adu(unit: UnitFacts, labeled_edges: List[Dict], boundary_wkt: str,
                 origin_lng: float, origin_lat: float) -> AduEvaluation:
  """Run Phase A.

  @param unit The unit facts (validated by the caller).
  @param labeled_edges LotEdge.to_dict() list from the edge labeler.
  @param boundary_wkt Subject parcel boundary, EPSG:4326 WKT.
  @param origin_lng @param origin_lat Subject point, for the local projection.

  @return The evaluation. Off the state track, edges are returned unchanged
    and there is no polygon: Phase B is not built (flagged).
  """
  decision = determine_track(unit)
  result = AduEvaluation(track=decision, unit=unit, edges=[dict(e) for e in labeled_edges],
                         flags=list(decision.flags))

  def add_flags(new: List[str]) -> None:
    result.flags.extend(f for f in new if f not in result.flags)

  if decision.track != TRACK_STATE_66323:
    add_flags(['phase_b_not_built'])
    return result

  setbacks, value_flags = state_track_setbacks(result.edges)
  for edge, setback in zip(result.edges, setbacks):
    edge['setback_ft'] = setback.setback_ft
    edge['setback_basis'] = setback.basis
  add_flags(value_flags)

  wkt, area, offset_flags = setback_polygon(boundary_wkt, result.edges, setbacks, origin_lng, origin_lat)
  result.setback_polygon_wkt = wkt
  result.setback_polygon_area_sqft = area
  add_flags(offset_flags)
  return result
