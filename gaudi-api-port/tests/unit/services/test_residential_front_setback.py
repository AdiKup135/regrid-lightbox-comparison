"""residential_front_setback_for: default vs. per-district match, and the null case."""
import json

from services.parcel_data.front_rules import residential_front_setback_for

_DB = {'jurisdictions': [
  {'jurisdiction': 'Testville', 'zoneomics_city_id': 1,
   'residential_front_setback': {'value_ft': 20, 'source': 'code', 'citation': 'TMC 1.2',
                                 'by_district': {'R-1-10,000': 25, 'R-1-40,000': 30}}},
  {'jurisdiction': 'Nullton', 'zoneomics_city_id': 2,
   'residential_front_setback': {'value_ft': None, 'source': None, 'citation': None}},
]}


def _db(tmp_path):
  path = tmp_path / 'db.json'
  path.write_text(json.dumps(_DB))
  return str(path)


def test_default_when_zone_unknown(tmp_path) -> None:
  got = residential_front_setback_for(jurisdiction_name='Testville', db_path=_db(tmp_path))
  assert got == {'value_ft': 20.0, 'source': 'code', 'citation': 'TMC 1.2', 'district': None}


def test_district_match_ignores_punctuation_and_case(tmp_path) -> None:
  got = residential_front_setback_for(city_id=1, zone_code='r1-40000', db_path=_db(tmp_path))
  assert got['value_ft'] == 30.0 and got['district'] == 'R-1-40,000'


def test_unlisted_zone_falls_back_to_default(tmp_path) -> None:
  got = residential_front_setback_for(city_id=1, zone_code='C-1', db_path=_db(tmp_path))
  assert got['value_ft'] == 20.0 and got['district'] is None


def test_null_value_is_none(tmp_path) -> None:
  assert residential_front_setback_for(city_id=2, zone_code='R-1', db_path=_db(tmp_path)) is None


def test_unknown_jurisdiction_is_none(tmp_path) -> None:
  assert residential_front_setback_for(jurisdiction_name='Elsewhere', db_path=_db(tmp_path)) is None
