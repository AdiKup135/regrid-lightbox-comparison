"""Unit tests for the orchestrator — Google-or-caller geocoding (no free
fallback, no situs string-matching), parallel fetch stages, neighbour
discovery, and the flag/error contract, all against a URL-routed fake
transport (zero network).

The world: three lots in a row on Madrono Ave, Palo Alto; the subject is the
middle one and the (rooftop) geocode lands inside it.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from fake_transport import FakeSession

from services.parcel_data.fetch_parcel_context import fetch_parcel_context

_SUBJECT_LNG, _SUBJECT_LAT = -122.1500, 37.4300
_SIDE = 0.0002  # ~22 m


def _square(center_lng: float, center_lat: float) -> Dict[str, Any]:
  half = _SIDE / 2
  ring = [[center_lng - half, center_lat - half], [center_lng + half, center_lat - half],
          [center_lng + half, center_lat + half], [center_lng - half, center_lat + half],
          [center_lng - half, center_lat - half]]
  return {'type': 'Polygon', 'coordinates': [ring]}


def _feature(apn: str, house: str, center_lng: float, center_lat: float) -> Dict[str, Any]:
  return {
    'type': 'Feature',
    'properties': {'apn': apn, 'situs_hous': house, 'situs_stre': '', 'situs_st_1': 'MADRONO', 'situs_st_2': 'AV',
                   'situs_city': 'PALO ALTO'},
    'geometry': _square(center_lng, center_lat),
  }


_SUBJECT = _feature('100', '1590', _SUBJECT_LNG, _SUBJECT_LAT)
_WEST = _feature('099', '1580', _SUBJECT_LNG - _SIDE, _SUBJECT_LAT)
_EAST = _feature('101', '1600', _SUBJECT_LNG + _SIDE, _SUBJECT_LAT)

_GOOGLE_OK = {'status': 'OK', 'results': [{
  'formatted_address': '1590 Madrono Ave, Palo Alto, CA 94301, USA',
  'geometry': {'location': {'lat': _SUBJECT_LAT, 'lng': _SUBJECT_LNG}, 'location_type': 'ROOFTOP'},
  'address_components': [
    {'long_name': '1590', 'types': ['street_number']},
    {'long_name': 'Madrono Avenue', 'types': ['route']},
    {'long_name': 'Palo Alto', 'types': ['locality']},
    {'long_name': 'Santa Clara County', 'types': ['administrative_area_level_2']},
  ],
}]}

_CENSUS_COORDINATES = {'result': {'geographies': {
  'Incorporated Places': [{'BASENAME': 'Palo Alto', 'GEOID': '0655282'}],
  'Counties': [{'BASENAME': 'Santa Clara', 'GEOID': '06085'}],
}}}

_ZONE_OK = {'features': [{'attributes': {
  'County': 'SCL', 'Jurisdiction': 'Palo Alto', 'Code': 'R-1', 'Description': 'Residential Single-Family',
  'Source': 'City REST', 'Date': '7/16/2023',
}}]}

_ADDRESS = '1590 Madrono Ave, Palo Alto, CA'


def _parcel_layer_handler(point_features: List[Dict[str, Any]], envelope_features: List[Dict[str, Any]]):
  def handler(url: str, params: Dict[str, Any]) -> Any:
    features = point_features if params.get('geometryType') == 'esriGeometryPoint' else envelope_features
    return {'type': 'FeatureCollection', 'features': copy.deepcopy(features)}
  return handler


def _session(point_features: Optional[List[Dict[str, Any]]] = None,
             envelope_features: Optional[List[Dict[str, Any]]] = None,
             zone_payload: Any = None,
             extra: Optional[List] = None) -> FakeSession:
  routes = list(extra or [])
  routes += [
    ('maps.googleapis.com', _GOOGLE_OK),
    ('geocoder/geographies/coordinates', _CENSUS_COORDINATES),
    ('Santa_Clara_County_Parcels', _parcel_layer_handler(
      point_features if point_features is not None else [_SUBJECT],
      envelope_features if envelope_features is not None else [_SUBJECT, _WEST, _EAST])),
    ('California_Statewide_Zoning_North', zone_payload if zone_payload is not None else _ZONE_OK),
  ]
  return FakeSession(routes)


class TestHappyPath:
  def test_wire_shape_and_content(self) -> None:
    session = _session()
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert not context.get('error')
    assert context['subject']['apn'] == '100'
    assert context['subject']['address'] == '1590 MADRONO AV'
    assert sorted(n['apn'] for n in context['neighbors']) == ['099', '101']
    assert context['zone'] == {'zone_code': 'R-1', 'zone_type': 'Residential Single-Family'}
    assert context['subject_street_name'] == 'Madrono Avenue'
    assert context['meta']['city_name'] == 'Palo Alto'
    assert context['meta']['county_fips'] == '06085'
    assert context['meta']['geocode_source'] == 'google'
    assert context['discovery'] == 'arcgis-envelope'
    assert context['flags'] == []
    assert context['callCount'] == 5  # google + containment + point + envelope + zone

  def test_neighbor_cap_and_distance_order(self) -> None:
    far = _feature('102', '1620', _SUBJECT_LNG + 3 * _SIDE, _SUBJECT_LAT)
    session = _session(envelope_features=[_SUBJECT, far, _EAST, _WEST])
    context = fetch_parcel_context(_ADDRESS, max_neighbors=2, session=session, google_api_key='key')
    # The far lot is the one dropped by the cap; the two adjacent ones stay.
    assert sorted(n['apn'] for n in context['neighbors']) == ['099', '101']
    assert 'neighbors_truncated' in context['flags']

  def test_multiple_parcels_at_point_takes_first_and_flags(self) -> None:
    session = _session(point_features=[_SUBJECT, _EAST])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['subject']['apn'] == '100'
    assert 'multiple_parcels_at_point' in context['flags']


class TestGeocoding:
  def test_no_key_and_no_coordinate_is_bad_request(self) -> None:
    context = fetch_parcel_context(_ADDRESS, session=FakeSession([]))
    assert context['error_kind'] == 'bad_request'
    assert 'GOOGLE_API_KEY' in context['error']

  def test_google_no_result_is_no_match(self) -> None:
    session = _session(extra=[('maps.googleapis.com', {'status': 'ZERO_RESULTS', 'results': []})])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['error_kind'] == 'no_match'

  def test_caller_coordinate_skips_google(self) -> None:
    session = _session()
    context = fetch_parcel_context(_ADDRESS, session=session, lat=_SUBJECT_LAT, lng=_SUBJECT_LNG)
    assert context['meta']['geocode_source'] == 'caller'
    assert not any('maps.googleapis' in url for url, _ in session.requests)

  def test_non_rooftop_geocode_is_flagged(self) -> None:
    google = copy.deepcopy(_GOOGLE_OK)
    google['results'][0]['geometry']['location_type'] = 'RANGE_INTERPOLATED'
    session = _session(extra=[('maps.googleapis.com', google)])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert 'geocode_not_rooftop' in context['flags']

  def test_point_in_right_of_way_is_no_parcel(self) -> None:
    session = _session(point_features=[])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['error_kind'] == 'no_parcel'


class TestDegradations:
  def test_neighbor_fetch_failure_is_flagged_not_silent(self) -> None:
    def parcel_handler(url: str, params: Dict[str, Any]) -> Any:
      if params.get('geometryType') == 'esriGeometryPoint':
        return {'type': 'FeatureCollection', 'features': copy.deepcopy([_SUBJECT])}
      raise ConnectionError('envelope down')
    session = FakeSession([
      ('maps.googleapis.com', _GOOGLE_OK),
      ('geocoder/geographies/coordinates', _CENSUS_COORDINATES),
      ('Santa_Clara_County_Parcels', parcel_handler),
      ('California_Statewide_Zoning_North', _ZONE_OK),
    ])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['neighbors'] == []
    assert 'neighbor_fetch_failed' in context['flags']

  def test_zone_failure_is_flagged_and_none(self) -> None:
    session = _session(zone_payload=ConnectionError('zoning down'))
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['zone'] is None
    assert 'zone_lookup_failed' in context['flags']

  def test_containment_failure_falls_back_to_google_county_flagged(self) -> None:
    def flaky(url: str, params: Dict[str, Any]) -> Any:
      raise ConnectionError('census down')
    session = _session(extra=[('geocoder/geographies/coordinates', flaky)])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert not context.get('error')
    assert context['subject']['apn'] == '100'
    assert 'jurisdiction_lookup_failed' in context['flags']
    assert 'jurisdiction_from_google_locality' in context['flags']
    assert context['meta']['city_name'] == 'Palo Alto'  # postal locality, flagged

  def test_unsupported_county(self) -> None:
    containment = {'result': {'geographies': {
      'Incorporated Places': [{'BASENAME': 'Fresno', 'GEOID': '0627000'}],
      'Counties': [{'BASENAME': 'Fresno', 'GEOID': '06019'}],
    }}}
    session = _session(extra=[('geocoder/geographies/coordinates', containment)])
    context = fetch_parcel_context('1 Somewhere, Fresno, CA', session=session, google_api_key='key')
    assert context['error_kind'] == 'unsupported_county'

  def test_blank_address_is_bad_request(self) -> None:
    context = fetch_parcel_context('  ', session=FakeSession([]), google_api_key='key')
    assert context['error_kind'] == 'bad_request'


class TestUnincorporatedJurisdiction:
  def test_county_jurisdiction_name(self) -> None:
    containment = {'result': {'geographies': {
      'Counties': [{'BASENAME': 'Santa Clara', 'GEOID': '06085'}],
    }}}
    session = _session(extra=[('geocoder/geographies/coordinates', containment)])
    context = fetch_parcel_context(_ADDRESS, session=session, google_api_key='key')
    assert context['meta']['city_name'] == 'Santa Clara County (unincorporated)'
