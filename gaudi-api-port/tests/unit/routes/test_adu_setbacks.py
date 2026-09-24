"""Unit tests for the /adu/evaluate route — input validation, the shared label
assembly, and the Phase A response shape on the real engine. Flask test client
only, same caveat as test_parcel_edges.py."""
from __future__ import annotations

import pytest

from app_poc import create_app
import routes.adu_setbacks as route_module

_SUBJECT = {
  'apn': '100', 'address': '1590 MADRONO AV', 'lat': 37.43, 'lng': -122.15,
  'boundary': 'POLYGON ((-122.1502 37.4298, -122.1498 37.4298, -122.1498 37.4302, -122.1502 37.4302, -122.1502 37.4298))',
}
_NEIGHBOR = {
  'apn': '101', 'address': '1600 MADRONO AV', 'lat': 37.43, 'lng': -122.1494,
  'boundary': 'POLYGON ((-122.1498 37.4298, -122.1494 37.4298, -122.1494 37.4302, -122.1498 37.4302, -122.1498 37.4298))',
}
_PAYLOAD = {
  'subject': _SUBJECT, 'neighbors': [_NEIGHBOR],
  'zone': {'zone_code': 'R-1', 'zone_type': 'Residential Single-Family'},
  'meta': {'city_name': 'Palo Alto', 'county_name': 'Santa Clara'},
  'transit': {'near_transit': False},
}


@pytest.fixture()
def client():
  app = create_app()
  app.testing = True
  return app.test_client()


class TestValidation:
  def test_missing_unit_size_is_400(self, client) -> None:
    response = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_height_in_feet': 16})
    assert response.status_code == 400
    assert 'unit_size' in response.get_json()['error']

  def test_missing_height_is_400(self, client) -> None:
    response = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 800})
    assert response.status_code == 400
    assert 'unit_height_in_feet' in response.get_json()['error']

  def test_missing_subject_is_400(self, client) -> None:
    response = client.post('/adu/evaluate', json={'unit_size': 800, 'unit_height_in_feet': 16})
    assert response.status_code == 400


class TestEvaluate:
  def test_state_track_response_shape(self, client) -> None:
    response = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 800, 'unit_height_in_feet': 16})
    assert response.status_code == 200
    body = response.get_json()
    assert body['phase'] == 'A'
    assert body['transit_source'] == 'payload'
    assert body['track'] == 'state_66323'
    assert body['state_height_limit_ft'] == 16.0
    assert body['edges'] and all('setback_ft' in e and e.get('tag') for e in body['edges'])
    assert body['setback_polygon'].startswith('POLYGON')
    assert body['setback_polygon_area_sqft'] > 0
    assert body['labeling']['engine'] == 'python'
    # Palo Alto is in the jurisdiction db: its rule, not the engine default.
    assert body['labeling']['front_rule_used'] not in (None, 'address_street (engine default)')
    for flag in ('zone_use_assumed_residential', 'sb9_split_assumed_no', 'existing_detached_adu_assumed_no'):
      assert flag in body['flags']

  def test_front_value_comes_from_the_jurisdiction_db(self, client) -> None:
    # Palo Alto R-1: PAMC 18.12.040(e), 20 ft — matched through the zone code.
    body = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 800, 'unit_height_in_feet': 16}).get_json()
    assert body['front_setback']['source'] == 'jurisdiction_db'
    assert body['front_setback']['value_ft'] == 20.0
    assert body['front_setback']['citation'].startswith('R-1 district:')
    assert 'front_setback_missing' not in body['flags']
    assert [e['setback_ft'] for e in body['edges'] if e['tag'] == 'front'] == [20.0]

  def test_unknown_jurisdiction_has_no_front_value(self, client) -> None:
    payload = {**_PAYLOAD, 'meta': {'city_name': 'Nowhere', 'county_name': 'Santa Clara'}}
    body = client.post('/adu/evaluate', json={**payload, 'unit_size': 800, 'unit_height_in_feet': 16}).get_json()
    assert body['front_setback']['source'] == 'missing'
    assert 'front_setback_missing' in body['flags']
    assert [e['setback_ft'] for e in body['edges'] if e['tag'] == 'front'] == [None]

  def test_manual_front_value_is_used_and_flagged(self, client) -> None:
    body = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 800, 'unit_height_in_feet': 16,
                                              'front_setback_ft': 20}).get_json()
    assert body['front_setback'] == {'value_ft': 20.0, 'source': 'manual', 'citation': 'entered by the user'}
    assert 'front_setback_from_manual_override' in body['flags'] and 'front_setback_missing' not in body['flags']
    assert [e['setback_ft'] for e in body['edges'] if e['tag'] == 'front'] == [20.0]

  def test_negative_front_value_is_400(self, client) -> None:
    response = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 800, 'unit_height_in_feet': 16,
                                                  'front_setback_ft': -1})
    assert response.status_code == 400

  def test_transit_from_payload_raises_the_height_limit(self, client) -> None:
    near = {**_PAYLOAD, 'transit': {'near_transit': True}, 'unit_size': 800, 'unit_height_in_feet': 18}
    response = client.post('/adu/evaluate', json=near)
    body = response.get_json()
    assert body['track'] == 'state_66323' and body['state_height_limit_ft'] == 18.0
    assert 'transit_straight_line_buffer' in body['flags']

  def test_missing_transit_block_triggers_a_lookup(self, client, monkeypatch) -> None:
    seen = {}

    def fake_lookup(lat, lng, session=None):
      seen['point'] = (lat, lng)
      return {'near_transit': True, 'hqta_types': ['major_stop_rail'], 'agencies': [], 'routes': [], 'area_count': 1,
              'planned_dropped': 0, 'source': 'fake', 'distance_basis': 'half_mile_straight_line_buffer'}
    monkeypatch.setattr(route_module, 'fetch_transit_at_point', fake_lookup)
    without_transit = {k: v for k, v in _PAYLOAD.items() if k != 'transit'}
    response = client.post('/adu/evaluate', json={**without_transit, 'unit_size': 800, 'unit_height_in_feet': 18})
    body = response.get_json()
    assert seen['point'] == (_SUBJECT['lat'], _SUBJECT['lng'])
    assert body['transit_source'] == 'lookup' and body['state_height_limit_ft'] == 18.0

  def test_failed_lookup_is_flagged_not_fatal(self, client, monkeypatch) -> None:
    monkeypatch.setattr(route_module, 'fetch_transit_at_point', lambda lat, lng, session=None: None)
    without_transit = {k: v for k, v in _PAYLOAD.items() if k != 'transit'}
    response = client.post('/adu/evaluate', json={**without_transit, 'unit_size': 800, 'unit_height_in_feet': 16})
    body = response.get_json()
    assert response.status_code == 200
    assert body['transit_source'] == 'lookup_failed' and 'transit_lookup_failed' in body['flags']

  def test_large_unit_is_local_without_polygon(self, client) -> None:
    response = client.post('/adu/evaluate', json={**_PAYLOAD, 'unit_size': 1000, 'unit_height_in_feet': 16})
    body = response.get_json()
    assert body['track'] == 'local_66314'
    assert body['setback_polygon'] is None
    assert 'phase_b_not_built' in body['flags']
