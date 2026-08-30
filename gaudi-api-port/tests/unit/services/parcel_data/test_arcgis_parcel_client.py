"""Unit tests for the ArcGIS parcel client — normalization to the wire parcel
record, the Esri-JSON ring fallback, and both situs-join kinds."""
from __future__ import annotations

from typing import Any, Dict, List

from fake_transport import FakeResponse, FakeSession

from services.parcel_data import arcgis_parcel_client as client

# A unit square-ish lot around (-122.15, 37.43), GeoJSON ring (ccw).
_RING = [[-122.1501, 37.4301], [-122.1499, 37.4301], [-122.1499, 37.4299], [-122.1501, 37.4299], [-122.1501, 37.4301]]

_FIELDS_COUNTY: Dict[str, Any] = {
  'fips': '06085', 'name': 'Santa Clara',
  'parcel_layer_url': 'https://example.test/parcels/FeatureServer/0',
  'apn_field': 'apn',
  'situs_mode': 'fields',
  'situs_components': ['situs_hous', 'situs_stre', 'situs_st_1', 'situs_st_2'],
  'city_field': 'situs_city',
}

_JOIN_ARCGIS_COUNTY: Dict[str, Any] = {
  'fips': '06041', 'name': 'Marin',
  'parcel_layer_url': 'https://example.test/parcels/FeatureServer/0',
  'apn_field': 'Parcel',
  'situs_mode': 'join',
  'situs_join': {
    'layer_url': 'https://example.test/situs/FeatureServer/0',
    'apn_field': 'Parcel',
    'components': ['Number', 'Street', 'Suffix'],
    'city_field': 'MailCity',
  },
}

_JOIN_SOCRATA_COUNTY: Dict[str, Any] = {
  'fips': '06081', 'name': 'San Mateo',
  'parcel_layer_url': 'https://example.test/parcels/FeatureServer/1',
  'apn_field': 'APN',
  'situs_mode': 'join',
  'situs_join': {
    'kind': 'socrata',
    'resource_url': 'https://example.test/resource/nr6j-72z7.json',
    'apn_field': 'apn',
    'components': ['situs_addr'],
    'city_field': 'situs_city',
  },
}

_GEOJSON_PAYLOAD = {
  'features': [{
    'type': 'Feature',
    'properties': {'apn': '12424051', 'situs_hous': '1590', 'situs_stre': '', 'situs_st_1': 'MADRONO', 'situs_st_2': 'AV',
                   'situs_city': 'PALO ALTO'},
    'geometry': {'type': 'Polygon', 'coordinates': [_RING]},
  }],
}

# Same lot in Esri JSON: exterior ring CLOCKWISE per the Esri convention.
_ESRI_PAYLOAD = {
  'features': [{
    'attributes': {'apn': '12424051', 'situs_hous': '1590', 'situs_stre': None, 'situs_st_1': 'MADRONO', 'situs_st_2': 'AV',
                   'situs_city': 'PALO ALTO'},
    'geometry': {'rings': [list(reversed(_RING))]},
  }],
}


class TestComposeSitus:
  def test_skips_empty_components(self) -> None:
    attributes = {'a': '1590', 'b': '', 'c': 'MADRONO', 'd': None, 'e': 'AV'}
    assert client.compose_situs(attributes, ['a', 'b', 'c', 'd', 'e']) == '1590 MADRONO AV'


class TestFetchParcelsAtPoint:
  def test_geojson_normalization(self) -> None:
    session = FakeSession([('parcels', _GEOJSON_PAYLOAD)])
    records = client.fetch_parcels_at_point(_FIELDS_COUNTY, 37.43, -122.15, session=session)
    assert records is not None and len(records) == 1
    record = records[0]
    assert record['apn'] == '12424051'
    assert record['address'] == '1590 MADRONO AV'
    assert record['situs_city'] == 'PALO ALTO'
    assert record['boundary'].startswith('MULTIPOLYGON')
    assert abs(record['lat'] - 37.43) < 1e-3 and abs(record['lng'] - -122.15) < 1e-3

  def test_esri_json_fallback_when_geojson_unsupported(self) -> None:
    def handler(url: str, params: Dict[str, Any]) -> Any:
      if params.get('f') == 'geojson':
        return {'error': {'code': 400, 'message': 'format not supported'}}
      return _ESRI_PAYLOAD
    session = FakeSession([('parcels', handler)])
    records = client.fetch_parcels_at_point(_FIELDS_COUNTY, 37.43, -122.15, session=session)
    assert records is not None and len(records) == 1
    assert records[0]['apn'] == '12424051'
    assert records[0]['boundary'].startswith('MULTIPOLYGON')

  def test_transport_failure_returns_none(self) -> None:
    session = FakeSession([('parcels', ConnectionError('boom'))])
    assert client.fetch_parcels_at_point(_FIELDS_COUNTY, 37.43, -122.15, session=session) is None

  def test_join_mode_leaves_address_empty(self) -> None:
    payload = {'features': [dict(_GEOJSON_PAYLOAD['features'][0], properties={'Parcel': '02801416'})]}
    session = FakeSession([('parcels', payload)])
    records = client.fetch_parcels_at_point(_JOIN_ARCGIS_COUNTY, 37.43, -122.15, session=session)
    assert records is not None and records[0]['address'] == ''


class TestAttachJoinedSitus:
  def test_arcgis_join_composes_and_first_row_wins(self) -> None:
    rows = {'features': [
      {'attributes': {'Parcel': '02801416', 'Number': '26', 'Street': 'CORTE MADERA', 'Suffix': 'AVE', 'MailCity': 'MILL VALLEY'}},
      {'attributes': {'Parcel': '02801416', 'Number': '26', 'Street': 'CORTE MADERA', 'Suffix': 'AVE', 'MailCity': 'DUPLICATE'}},
    ]}
    session = FakeSession([('situs', rows)])
    parcels: List[Dict[str, Any]] = [{'apn': '02801416', 'address': '', 'situs_city': None}]
    assert client.attach_joined_situs(_JOIN_ARCGIS_COUNTY, parcels, session=session) is True
    assert parcels[0]['address'] == '26 CORTE MADERA AVE'
    assert parcels[0]['situs_city'] == 'MILL VALLEY'

  def test_socrata_join(self) -> None:
    rows = [{'apn': '051333140', 'situs_addr': '1312 LAUREL ST', 'situs_city': 'SAN CARLOS'}]
    session = FakeSession([('resource/nr6j-72z7', rows)])
    parcels: List[Dict[str, Any]] = [{'apn': '051333140', 'address': '', 'situs_city': None},
                                     {'apn': '051333150', 'address': '', 'situs_city': None}]
    assert client.attach_joined_situs(_JOIN_SOCRATA_COUNTY, parcels, session=session) is True
    assert parcels[0]['address'] == '1312 LAUREL ST'
    assert parcels[1]['address'] == ''  # no row for this APN: left as-is, not invented

  def test_join_failure_reports_false(self) -> None:
    session = FakeSession([('resource/nr6j-72z7', FakeResponse({}, status_code=500))])
    parcels: List[Dict[str, Any]] = [{'apn': '051333140', 'address': '', 'situs_city': None}]
    assert client.attach_joined_situs(_JOIN_SOCRATA_COUNTY, parcels, session=session) is False

  def test_fields_mode_is_a_noop(self) -> None:
    session = FakeSession([])
    parcels: List[Dict[str, Any]] = [{'apn': 'x', 'address': '1 A ST', 'situs_city': None}]
    assert client.attach_joined_situs(_FIELDS_COUNTY, parcels, session=session) is True
    assert session.requests == []
