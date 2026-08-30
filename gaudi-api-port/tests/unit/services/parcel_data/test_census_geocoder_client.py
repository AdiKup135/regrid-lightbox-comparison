"""Unit tests for the Census containment client — parsing, the unincorporated
case, and the transient-failure retry, all against a fake transport (zero
network). The address-matching endpoint was removed; only coordinates ->
geographies remains."""
from __future__ import annotations

from fake_transport import FakeResponse, FakeSession

from services.parcel_data import census_geocoder_client as client

_GEOGRAPHIES = {
  'Incorporated Places': [{'BASENAME': 'Palo Alto', 'GEOID': '0655282'}],
  'Counties': [{'BASENAME': 'Santa Clara', 'GEOID': '06085'}],
}

_COORDINATES_OK = {'result': {'geographies': _GEOGRAPHIES}}
_COORDINATES_UNINCORPORATED = {'result': {'geographies': {'Counties': [{'BASENAME': 'San Mateo', 'GEOID': '06081'}]}}}


class TestGeographiesForPoint:
  def test_incorporated(self) -> None:
    session = FakeSession([('coordinates', _COORDINATES_OK)])
    record = client.geographies_for_point(37.4448, -122.1605, session=session)
    assert record == {'place_name': 'Palo Alto', 'place_geoid': '0655282',
                      'county_name': 'Santa Clara', 'county_fips': '06085'}

  def test_unincorporated_has_county_but_no_place(self) -> None:
    session = FakeSession([('coordinates', _COORDINATES_UNINCORPORATED)])
    record = client.geographies_for_point(37.4, -122.3, session=session)
    assert record is not None
    assert record['place_name'] is None
    assert record['county_fips'] == '06081'

  def test_transient_failure_then_success(self, monkeypatch) -> None:
    monkeypatch.setattr(client.time, 'sleep', lambda seconds: None)
    responses = iter([FakeResponse({}, status_code=500), FakeResponse(_COORDINATES_OK)])
    session = FakeSession([('coordinates', lambda url, params: next(responses))])
    record = client.geographies_for_point(37.4448, -122.1605, session=session)
    assert record is not None and record['place_name'] == 'Palo Alto'

  def test_transport_failure_returns_none(self, monkeypatch) -> None:
    monkeypatch.setattr(client.time, 'sleep', lambda seconds: None)
    session = FakeSession([('coordinates', ConnectionError('boom'))])
    assert client.geographies_for_point(37.4, -122.3, session=session) is None
    assert len(session.requests) == client._ATTEMPTS
