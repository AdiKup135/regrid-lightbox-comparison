"""
adu_setbacks
------------
Phase A of the ADU setback engine: the state track (Gov. Code § 66323(a)(2)).

Given the labeled lot edges (services.compute.parcel_edges), two facts about
the proposed unit — ``unit_size`` (sq ft, footprint incl. exterior walls, excl. decks; the name
gaudi-api already uses in EstimatorParameters) and ``unit_height_in_feet`` —
and whether the lot sits in a high-quality transit area, decide which track
the unit is on and, on the state track, assign every edge its setback and draw
the buildable envelope.

Decision record: the tree and every assumption behind it are kept on the
"ADU Setback Decision Tree" page (see the setback-engine-decisions memory) and
in Linear FOR-1418 with sub-issues FOR-1419/1420/1421/1422 for the deferred
gates.

Phase B (the local ordinance track, § 66314) and Phase C (the owner's choice
between envelopes) are not here: a unit that leaves the state track gets a
track verdict and no polygon.
"""
from .evaluate import AduEvaluation, evaluate_adu  # noqa: F401
from .offset import setback_polygon  # noqa: F401
from .state_track import EdgeSetback, state_track_setbacks  # noqa: F401
from .track import (  # noqa: F401
  TRACK_LOCAL_66314,
  TRACK_STATE_66323,
  TrackDecision,
  UnitFacts,
  determine_track,
)
