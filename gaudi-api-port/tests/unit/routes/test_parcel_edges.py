"""Unit tests for the parcel_edges blueprint — route assembly, error mapping,
and the label route running the real engine on a synthetic offline payload.

Flask test client only — NOT an endpoint E2E in the gaudi-api sense (no real
process, no auth); those land with the gaudi integration per its testing
contract. What this pins is the wiring this repo owns: request parsing, the
error_kind -> status map, front-rule resolution from meta, and the
EdgeLabelingInput assembly.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app_poc import create_app
import routes.parcel_edges as route_module

# Two 100x100 ft-ish lots side by side; the subject fronts an unnamed gap on
# its other sides. Enough for the engine to run and return labeled edges.
_SUBJECT = {
  'apn': '100', 'address': '1590 MADRONO AV', 'lat': 37.43, 'lng': -122.15,
  'boundary': 'POLYGON ((-122.1502 37.4298, -122.1498 37.4298, -122.1498 37.4302, -122.1502 37.4302, -122.1502 37.4298))',
}
_NEIGHBOR = {
  'apn': '101', 'address': '1600 MADRONO AV', 'lat': 37.43, 'lng': -122.1494,
  'boundary': 'POLYGON ((-122.1498 37.4298, -122.1494 37.4298, -122.1494 37.4302, -122.1498 37.4302, -122.1498 37.4298))',
}


@pytest.fixture()
def client():
  app = create_app()
  app.testing = True
  return app.test_client()


class TestGetEdges:
  def test_missing_address_is_400(self, client) -> None:
    response = client.get('/edges')
    assert response.status_code == 400

  def test_error_kind_maps_to_status(self, client, monkeypatch) -> None:
    monkeypatch.setattr(route_module, 'fetch_parcel_context',
                        lambda address, **kwargs: {'error': 'nope', 'error_kind': 'unsupported_county'})
    response = client.get('/edges?address=1+Somewhere,+Fresno,+CA')
    assert response.status_code == 422

  def test_success_passes_context_through(self, client, monkeypatch) -> None:
    def fake_fetch(address: str, **kwargs: Any) -> Dict[str, Any]:
      assert kwargs.get('lat') == 37.43 and kwargs.get('lng') == -122.15
      return {'geocode': {'lat': 37.43, 'lng': -122.15}, 'subject': _SUBJECT, 'neighbors': [],
              'meta': {'city_name': 'Palo Alto'}, 'zone': None, 'callCount': 3, 'flags': []}
    monkeypatch.setattr(route_module, 'fetch_parcel_context', fake_fetch)
    response = client.get('/edges?address=x&lat=37.43&lng=-122.15')
    assert response.status_code == 200
    assert response.get_json()['subject']['apn'] == '100'


class TestLabelRoute:
  def test_missing_subject_is_400(self, client) -> None:
    response = client.post('/edges/label', json={'neighbors': []})
    assert response.status_code == 400

  def test_labels_a_payload_with_the_real_engine(self, client) -> None:
    payload = {
      'subject': _SUBJECT,
      'neighbors': [_NEIGHBOR],
      'zone': {'zone_code': 'R-1', 'zone_type': 'Residential Single-Family'},
      'meta': {'city_name': 'Palo Alto', 'county_name': 'Santa Clara'},
    }
    response = client.post('/edges/label', json=payload)
    assert response.status_code == 200
    body = response.get_json()
    assert body['engine'] == 'python'
    edges = body['result']['edges']
    assert edges and all(e.get('tag') for e in edges)
    # Palo Alto is in the jurisdiction db: its rule, not the engine default.
    assert body['front_rule_used'] not in (None, 'address_street (engine default)')

  def test_explicit_front_rule_outranks_meta(self, client) -> None:
    payload = {'subject': _SUBJECT, 'neighbors': [], 'front_rule': 'shortest_frontage',
               'meta': {'city_name': 'Palo Alto'}}
    response = client.post('/edges/label', json=payload)
    assert response.status_code == 200
    assert response.get_json()['front_rule_used'] == 'shortest_frontage'
