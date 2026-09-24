"""
state_track.py
--------------
Per-edge setbacks for a § 66323(a)(2) unit.

On the state track the statute fixes the side and rear values; the front is
the jurisdiction's own number. Counsel (Hila, 2026-09-24):

  side, rear    4 ft  — "four-foot side and rear yard setbacks", § 66323(a)(2)
  front         the jurisdiction's default front setback for housing. § 66323
                does not set a front value (it lists only side and rear), so the
                local residential front setback stands. It comes from the
                jurisdiction database (residential_front_setback.value_ft) or a
                manual value posted with the request; when neither exists the
                edge has no value and the lot is flagged — never a silent 0.
  street_side   4 ft  — treated as a side (engine rule 2026-09-23).
  second_front  4 ft  — all_fronts jurisdictions (Hillsborough, Sunnyvale,
                Contra Costa County) call both street lines fronts. For the
                state-track unit the address street is THE front (local value)
                and the other frontage takes the state's 4 ft.

Coverage, FAR, lot size, open space and design standards do not apply to a
66323 unit (Handbook p. 19), so nothing else is computed here.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

STATE_SIDE_REAR_FT = 4.0

CITE_SIDE_REAR = 'Gov. Code § 66323(a)(2) — four-foot side and rear yard setbacks'
CITE_FRONT = ('Local front setback (jurisdiction default for housing): § 66323(a)(2) sets side and rear '
              'values only, so the local front value applies to a 66323 unit (counsel, 2026-09-24)')
CITE_FRONT_MISSING = ('Local front setback applies (counsel, 2026-09-24) but the jurisdiction database has no '
                      'residential_front_setback value yet — enter it manually')
CITE_STREET_SIDE_AS_SIDE = 'street_side treated as a side lot line (engine rule, 2026-09-23); ' + CITE_SIDE_REAR
CITE_SECOND_FRONT = ('second_front edge (all_fronts jurisdiction): the address street is the front; the other '
                     'frontage takes the state value (counsel, 2026-09-24); ' + CITE_SIDE_REAR)

FLAG_FRONT_SETBACK_MISSING = 'front_setback_missing'
FLAG_FRONT_SETBACK_MANUAL = 'front_setback_from_manual_override'

FRONT_SOURCE_DB = 'jurisdiction_db'
FRONT_SOURCE_MANUAL = 'manual'
FRONT_SOURCE_MISSING = 'missing'


@dataclass(frozen=True)
class FrontSetback:
  """Where the front value came from. ``value_ft`` None = nobody knows it yet."""
  value_ft: Optional[float]
  source: str  # FRONT_SOURCE_*
  citation: Optional[str] = None

  def to_dict(self) -> Dict:
    return {'value_ft': self.value_ft, 'source': self.source, 'citation': self.citation}


FRONT_UNKNOWN = FrontSetback(None, FRONT_SOURCE_MISSING)


@dataclass
class EdgeSetback:
  # Index into the labeled edges list, so the UI can join without re-matching geometry.
  edge_index: int
  tag: str
  # None only for a front whose local value is not in the database and not posted.
  setback_ft: Optional[float]
  basis: str

  def to_dict(self) -> Dict:
    return {'edge_index': self.edge_index, 'tag': self.tag, 'setback_ft': self.setback_ft, 'basis': self.basis}


def state_track_setbacks(edges: List[Dict], front: FrontSetback = FRONT_UNKNOWN) -> Tuple[List[EdgeSetback], List[str]]:
  """Assign the state-track setback to every labeled edge.

  @param edges The labeled edges as dicts (LotEdge.to_dict()): ``tag`` and
    ``flags`` are read; geometry is left to the offset step.
  @param front The jurisdiction's residential front setback (or the manual value).

  @return (setbacks in edge order, lot-level flags).
  """
  out: List[EdgeSetback] = []
  flags: List[str] = []

  def flag(name: str) -> None:
    if name not in flags:
      flags.append(name)

  if front.value_ft is None:
    front_basis = CITE_FRONT_MISSING
  else:
    front_basis = '%s. Source: %s' % (CITE_FRONT, front.citation or front.source)

  for index, edge in enumerate(edges):
    tag = str(edge.get('tag') or '')
    edge_flags = edge.get('flags') or []
    if tag == 'front':
      out.append(EdgeSetback(index, tag, front.value_ft, front_basis))
      if front.value_ft is None:
        flag(FLAG_FRONT_SETBACK_MISSING)
      elif front.source == FRONT_SOURCE_MANUAL:
        flag(FLAG_FRONT_SETBACK_MANUAL)
    elif tag in ('side', 'rear'):
      out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT, CITE_SIDE_REAR))
    elif tag == 'street_side':
      basis = CITE_SECOND_FRONT if 'second_front' in edge_flags else CITE_STREET_SIDE_AS_SIDE
      out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT, basis))
    else:
      # The labeler emits only the four tags; anything else is a contract break,
      # not a legal case. Treat as side (the conservative 4 ft) and say so.
      out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT,
                             'unknown edge tag %r treated as side; ' % tag + CITE_SIDE_REAR))
      flag('unknown_edge_tag')
  return out, flags
