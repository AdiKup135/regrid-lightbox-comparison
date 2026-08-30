"""Unit tests for the Google geocoding client — component extraction, county
suffix stripping, and the never-raise contract, against a fake transport."""
from __future__ import annotations

from fake_transport import FakeSession

from services.parcel_data.google_geocoder_client import fetch_geocode

_RESULT = {
  'formatted_address': '1590 Madrono Ave, Palo Alto, CA 94301, USA',
  'geometry': {'location': {'lat': 37.43243, 'lng': -122.15219}, 'location_type': 'ROOFTOP'},
  'address_components': [
    {'long_name': '1590', 'types': ['street_number']},
    {'long_name': 'Madrono Avenue', 'types': ['route']},
    {'long_name': 'Palo Alto', 'types': ['locality', 'political']},
    {'long_name': 'Santa Clara County', 'types': ['administrative_area_level_2', 'political']},
  ],
}


class TestFetchGeocode:
  def test_success_extracts_components(self) -> None:
    session = FakeSession([('maps.googleapis.com', {'status': 'OK', 'results': [_RESULT]})])
    record = fetch_geocode('1590 Madrono Ave, Palo Alto, CA', 'key', session=session)
    assert record is not None
    assert (record['lat'], record['lng']) == (37.43243, -122.15219)
    assert record['house_number'] == '1590'
    assert record['street_name'] == 'Madrono Avenue'
    assert record['locality'] == 'Palo Alto'
    assert record['county_name'] == 'Santa Clara'  # ' County' stripped
    assert record['location_type'] == 'ROOFTOP'

  def test_missing_key_short_circuits(self) -> None:
    session = FakeSession([])
    assert fetch_geocode('1590 Madrono Ave', '', session=session) is None
    assert session.requests == []

  def test_zero_results_returns_none(self) -> None:
    session = FakeSession([('maps.googleapis.com', {'status': 'ZERO_RESULTS', 'results': []})])
    assert fetch_geocode('1 Nowhere Rd', 'key', session=session) is None

  def test_error_status_returns_none(self) -> None:
    session = FakeSession([('maps.googleapis.com', {'status': 'REQUEST_DENIED', 'results': []})])
    assert fetch_geocode('1590 Madrono Ave', 'key', session=session) is None

  def test_transport_exception_returns_none(self) -> None:
    session = FakeSession([('maps.googleapis.com', ConnectionError('boom'))])
    assert fetch_geocode('1590 Madrono Ave', 'key', session=session) is None
