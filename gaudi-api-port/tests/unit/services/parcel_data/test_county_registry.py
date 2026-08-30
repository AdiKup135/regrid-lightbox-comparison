"""Unit tests for the county registry — lookup keys and config-shape invariants
that the county-agnostic client relies on."""
from __future__ import annotations

from services.parcel_data.county_registry import COUNTY_REGISTRY, county_for_fips, county_for_name

_TERRITORY_FIPS = {'06013', '06041', '06055', '06081', '06085', '06097'}


class TestLookups:
  def test_all_territory_counties_present(self) -> None:
    assert set(COUNTY_REGISTRY) == _TERRITORY_FIPS

  def test_fips_lookup(self) -> None:
    county = county_for_fips('06085')
    assert county is not None and county['name'] == 'Santa Clara'
    assert county_for_fips('06019') is None
    assert county_for_fips(None) is None

  def test_name_lookup_tolerates_county_suffix_and_case(self) -> None:
    assert county_for_name('San Mateo County') is county_for_fips('06081')
    assert county_for_name('santa clara') is county_for_fips('06085')
    assert county_for_name('Alameda') is None


class TestConfigShapes:
  def test_every_config_is_executable_by_the_client(self) -> None:
    for fips, county in COUNTY_REGISTRY.items():
      assert county['fips'] == fips
      assert str(county['parcel_layer_url']).startswith('https://')
      assert county['apn_field']
      mode = county['situs_mode']
      assert mode in ('fields', 'join')
      if mode == 'fields':
        assert county['situs_components'], fips
      else:
        join = county['situs_join']
        assert join['apn_field'] and join['components'], fips
        if join.get('kind') == 'socrata':
          assert str(join['resource_url']).endswith('.json'), fips
        else:
          assert str(join['layer_url']).startswith('https://'), fips
