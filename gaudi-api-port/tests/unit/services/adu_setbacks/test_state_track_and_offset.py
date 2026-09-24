"""Unit tests for the state-track values and the envelope offset.

The lot: a 100 ft × 60 ft rectangle at Palo Alto's latitude, built from the
labeler's own projection so the expected areas are exact in feet. Edges are
hand-labeled here — the labeler has its own suite; this pins what Phase A does
with its output.
"""
from __future__ import annotations

from typing import Dict, List

from shapely import from_wkt

from services.compute.adu_setbacks.evaluate import evaluate_adu
from services.compute.adu_setbacks.offset import FLAG_CONCAVE_LOT, FLAG_ENVELOPE_MISSING_VALUE, setback_polygon
from services.compute.adu_setbacks.state_track import (
  FLAG_FRONT_SETBACK_MANUAL,
  FLAG_FRONT_SETBACK_MISSING,
  FRONT_SOURCE_DB,
  FRONT_SOURCE_MANUAL,
  FrontSetback,
  state_track_setbacks,
)
from services.compute.adu_setbacks.track import UnitFacts
from services.compute.parcel_edges.geometry import make_projection

_ORIGIN = (-122.1500, 37.4300)
_PROJ = make_projection(*_ORIGIN)


def _ll(x_ft: float, y_ft: float) -> List[float]:
  return list(_PROJ.to_ll((x_ft, y_ft)))


# Corners in feet: front along the west (x=0) edge, rear on the east, sides north/south.
_A, _B, _C, _D = (0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)


def _wkt(pts_ft) -> str:
  ring = [_ll(*p) for p in pts_ft] + [_ll(*pts_ft[0])]
  return 'POLYGON ((%s))' % ', '.join('%.8f %.8f' % (p[0], p[1]) for p in ring)


def _edge(tag: str, a, b, flags=None) -> Dict:
  return {'tag': tag, 'pts': [_ll(*a), _ll(*b)], 'flags': list(flags or []), 'lengthFt': 0.0,
          'basis': 'test', 'confidence': 'high', 'abuts': {'kind': 'street'}}


_RECT_WKT = _wkt([_A, _B, _C, _D])
# Interior-lot labeling: front west, rear east, two sides.
_INTERIOR = [_edge('front', _D, _A), _edge('side', _A, _B), _edge('rear', _B, _C), _edge('side', _C, _D)]
# Corner-lot labeling: the north edge is a second street.
_CORNER = [_edge('front', _D, _A), _edge('side', _A, _B), _edge('rear', _B, _C), _edge('street_side', _C, _D)]


# A jurisdiction whose code says 20 ft in front of a house.
_FRONT_20 = FrontSetback(20.0, FRONT_SOURCE_DB, 'Test MC 1.2.3')


def _area_ft(wkt: str) -> float:
  ring = [_PROJ.to_ft((x, y)) for x, y in from_wkt(wkt).exterior.coords]
  from shapely.geometry import Polygon
  return Polygon(ring).area


class TestStateTrackValues:
  def test_interior_lot_front_is_the_local_value(self) -> None:
    setbacks, flags = state_track_setbacks(_INTERIOR, _FRONT_20)
    assert [s.setback_ft for s in setbacks] == [20.0, 4.0, 4.0, 4.0]
    assert 'Test MC 1.2.3' in setbacks[0].basis
    assert flags == []

  def test_front_without_a_local_value_is_none_and_flagged(self) -> None:
    setbacks, flags = state_track_setbacks(_INTERIOR)
    assert [s.setback_ft for s in setbacks] == [None, 4.0, 4.0, 4.0]
    assert flags == [FLAG_FRONT_SETBACK_MISSING]

  def test_manual_front_value_is_flagged_as_manual(self) -> None:
    setbacks, flags = state_track_setbacks(_INTERIOR, FrontSetback(15.0, FRONT_SOURCE_MANUAL))
    assert setbacks[0].setback_ft == 15.0
    assert flags == [FLAG_FRONT_SETBACK_MANUAL]

  def test_street_side_is_a_side(self) -> None:
    setbacks, flags = state_track_setbacks(_CORNER, _FRONT_20)
    assert setbacks[3].setback_ft == 4.0
    assert 'side' in setbacks[3].basis
    assert flags == []

  def test_second_front_takes_the_state_4_ft(self) -> None:
    edges = list(_CORNER)
    edges[3] = _edge('street_side', _C, _D, flags=['second_front'])
    setbacks, flags = state_track_setbacks(edges, _FRONT_20)
    assert setbacks[0].setback_ft == 20.0  # the address street keeps the local front
    assert setbacks[3].setback_ft == 4.0
    assert 'second_front' in setbacks[3].basis
    assert flags == []


class TestOffset:
  def test_rectangle_interior_lot_area(self) -> None:
    setbacks, _ = state_track_setbacks(_INTERIOR, _FRONT_20)
    wkt, area, flags = setback_polygon(_RECT_WKT, _INTERIOR, setbacks, *_ORIGIN)
    # 20 ft off the front, 4 ft off the rear and both sides: 76 × 52.
    assert abs(area - 76 * 52) < 1.0
    assert abs(_area_ft(wkt) - 76 * 52) < 2.0  # WKT round-trip, 9 decimals
    assert flags == []

  def test_missing_front_value_is_drawn_at_zero_and_flagged(self) -> None:
    setbacks, _ = state_track_setbacks(_INTERIOR)
    _, area, flags = setback_polygon(_RECT_WKT, _INTERIOR, setbacks, *_ORIGIN)
    assert abs(area - 96 * 52) < 1.0
    assert flags == [FLAG_ENVELOPE_MISSING_VALUE]

  def test_rectangle_corner_lot_area(self) -> None:
    setbacks, _ = state_track_setbacks(_CORNER, _FRONT_20)
    _, area, _ = setback_polygon(_RECT_WKT, _CORNER, setbacks, *_ORIGIN)
    # street_side is a side: same envelope as the interior lot.
    assert abs(area - 76 * 52) < 1.0

  def test_concave_lot_is_flagged(self) -> None:
    # An L-shaped lot: the rectangle with its NE 40 × 30 corner removed.
    pts = [_A, _B, (100.0, 30.0), (60.0, 30.0), (60.0, 60.0), _D]
    edges = [_edge('front', _D, _A), _edge('side', _A, _B), _edge('rear', _B, (100.0, 30.0)),
             _edge('side', (100.0, 30.0), (60.0, 30.0)), _edge('rear', (60.0, 30.0), (60.0, 60.0)),
             _edge('side', (60.0, 60.0), _D)]
    setbacks, _ = state_track_setbacks(edges, _FRONT_20)
    wkt, area, flags = setback_polygon(_wkt(pts), edges, setbacks, *_ORIGIN)
    assert FLAG_CONCAVE_LOT in flags
    assert wkt is not None and 0 < area < 100 * 60 - 40 * 30


class TestEvaluate:
  def test_state_track_end_to_end(self) -> None:
    unit = UnitFacts(unit_size=750, unit_height_in_feet=16, near_transit=False)
    result = evaluate_adu(unit, _INTERIOR, _RECT_WKT, *_ORIGIN, front=_FRONT_20).to_dict()
    assert result['track'] == 'state_66323'
    assert [e['setback_ft'] for e in result['edges']] == [20.0, 4.0, 4.0, 4.0]
    assert result['front_setback'] == {'value_ft': 20.0, 'source': 'jurisdiction_db', 'citation': 'Test MC 1.2.3'}
    assert result['setback_polygon'].startswith('POLYGON')
    assert abs(result['setback_polygon_area_sqft'] - 76 * 52) < 1.0
    assert 'phase_b_not_built' not in result['flags']

  def test_state_track_without_a_front_value(self) -> None:
    unit = UnitFacts(unit_size=750, unit_height_in_feet=16, near_transit=False)
    result = evaluate_adu(unit, _INTERIOR, _RECT_WKT, *_ORIGIN).to_dict()
    assert result['edges'][0]['setback_ft'] is None
    assert result['front_setback']['source'] == 'missing'
    assert FLAG_FRONT_SETBACK_MISSING in result['flags'] and FLAG_ENVELOPE_MISSING_VALUE in result['flags']

  def test_local_track_returns_no_polygon(self) -> None:
    unit = UnitFacts(unit_size=1000, unit_height_in_feet=16, near_transit=False)
    result = evaluate_adu(unit, _INTERIOR, _RECT_WKT, *_ORIGIN).to_dict()
    assert result['track'] == 'local_66314'
    assert result['setback_polygon'] is None
    assert 'phase_b_not_built' in result['flags']
    assert all('setback_ft' not in e for e in result['edges'])
