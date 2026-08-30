"""Unit tests for jurisdiction front-rule lookup — both provider vocabularies
(Zoneomics city_id, Census place name) against the real repo database, which is
a data asset of this feature (file read only, no network)."""
from __future__ import annotations

from services.parcel_data.front_rules import front_rule_for, load_jurisdictions


class TestDatabase:
  def test_loads_all_jurisdictions(self) -> None:
    # 23 cities/one county from the original Zoneomics pull + the 5 remaining
    # unincorporated-county records added 2026-08-30.
    assert len(load_jurisdictions()) == 28

  def test_every_registry_county_has_an_unincorporated_record(self) -> None:
    from services.parcel_data.county_registry import COUNTY_REGISTRY
    names = {str(record.get('jurisdiction')) for record in load_jurisdictions()}
    for county in COUNTY_REGISTRY.values():
      expected = '%s County (unincorporated)' % county['name']
      assert expected in names, expected
      rule = front_rule_for(jurisdiction_name=None, county_name=str(county['name']))
      assert rule and rule.get('rule'), expected


class TestLookup:
  def test_by_city_id_matches_the_express_backend_behavior(self) -> None:
    rule = front_rule_for(city_id=295)  # Palo Alto
    assert rule is not None and rule.get('rule')

  def test_by_jurisdiction_name(self) -> None:
    assert front_rule_for(jurisdiction_name='Palo Alto') == front_rule_for(city_id=295)
    assert front_rule_for(jurisdiction_name='  palo  alto ') == front_rule_for(city_id=295)

  def test_unincorporated_county_record(self) -> None:
    rule = front_rule_for(jurisdiction_name=None, county_name='San Mateo')
    assert rule is not None and rule.get('rule')

  def test_unknown_jurisdiction_is_none_not_a_guess(self) -> None:
    assert front_rule_for(jurisdiction_name='Fresno') is None
    assert front_rule_for() is None

  def test_city_id_outranks_name(self) -> None:
    assert front_rule_for(city_id=295, jurisdiction_name='Sunnyvale') == front_rule_for(city_id=295)
