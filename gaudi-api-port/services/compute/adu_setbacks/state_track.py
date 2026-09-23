"""
state_track.py
--------------
Per-edge setbacks for a § 66323(a)(2) unit.

On the state track the jurisdiction contributes exactly one thing: the edge
classification. The values are the statute's:

  side, rear   4 ft  — "four-foot side and rear yard setbacks", § 66323(a)(2)
  front        0 ft  — no front setback may be imposed on a 66323 unit
                       (HCD ADU Handbook, Mar 2026, p. 18 "May be in front
                       setback"; p. 37; § 66323(b))
  street_side  4 ft  — treated as a side. Decision 2026-09-23: a street_side
                       edge is a side unless the jurisdiction is all_fronts.
  street_side carrying the labeler's ``second_front`` flag (all_fronts
  jurisdictions: Hillsborough, Sunnyvale, Contra Costa County) — the city
  calls this line a front, so the 4 ft side cap does not reach it. Whether
  § 66323's no-front-setback rule zeroes it or the local front number applies
  is with counsel. SECOND_FRONT_INTERIM_FT is the placeholder until then, and
  the lot is flagged; change the constant when the answer lands.

Coverage, FAR, lot size, open space and design standards do not apply to a
66323 unit (Handbook p. 19), so nothing else is computed here.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

STATE_SIDE_REAR_FT = 4.0
# PENDING COUNSEL (asked 2026-09-23). 0 ft = HCD's no-front-setback rule applied
# to a line the local code classifies as a front. See FLAG_SECOND_FRONT_PENDING.
SECOND_FRONT_INTERIM_FT = 0.0

CITE_SIDE_REAR = 'Gov. Code § 66323(a)(2) — four-foot side and rear yard setbacks'
CITE_FRONT = 'Gov. Code § 66323(b); HCD ADU Handbook (Mar 2026) p. 18 "May be in front setback", p. 37'
CITE_STREET_SIDE_AS_SIDE = 'street_side treated as a side lot line (engine rule, 2026-09-23); ' + CITE_SIDE_REAR
CITE_SECOND_FRONT = ('second_front edge (all_fronts jurisdiction): a front under the local code; '
                     'value under § 66323 pending counsel — interim %g ft' % SECOND_FRONT_INTERIM_FT)

FLAG_SECOND_FRONT_PENDING = 'second_front_pending_counsel'


@dataclass
class EdgeSetback:
  # Index into the labeled edges list, so the UI can join without re-matching geometry.
  edge_index: int
  tag: str
  setback_ft: float
  basis: str

  def to_dict(self) -> Dict:
    return {'edge_index': self.edge_index, 'tag': self.tag, 'setback_ft': self.setback_ft, 'basis': self.basis}


def state_track_setbacks(edges: List[Dict]) -> Tuple[List[EdgeSetback], List[str]]:
  """Assign the state-track setback to every labeled edge.

  @param edges The labeled edges as dicts (LotEdge.to_dict()): ``tag`` and
    ``flags`` are read; geometry is left to the offset step.

  @return (setbacks in edge order, lot-level flags).
  """
  out: List[EdgeSetback] = []
  flags: List[str] = []

  def flag(name: str) -> None:
    if name not in flags:
      flags.append(name)

  for index, edge in enumerate(edges):
    tag = str(edge.get('tag') or '')
    edge_flags = edge.get('flags') or []
    if tag == 'front':
      out.append(EdgeSetback(index, tag, 0.0, CITE_FRONT))
    elif tag in ('side', 'rear'):
      out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT, CITE_SIDE_REAR))
    elif tag == 'street_side':
      if 'second_front' in edge_flags:
        out.append(EdgeSetback(index, tag, SECOND_FRONT_INTERIM_FT, CITE_SECOND_FRONT))
        flag(FLAG_SECOND_FRONT_PENDING)
      else:
        out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT, CITE_STREET_SIDE_AS_SIDE))
    else:
      # The labeler emits only the four tags; anything else is a contract break,
      # not a legal case. Treat as side (the conservative 4 ft) and say so.
      out.append(EdgeSetback(index, tag, STATE_SIDE_REAR_FT,
                             'unknown edge tag %r treated as side; ' % tag + CITE_SIDE_REAR))
      flag('unknown_edge_tag')
  return out, flags
