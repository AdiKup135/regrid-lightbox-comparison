"""
front_rules.py
--------------
Jurisdiction front-rule lookup for the labeling pipeline.

The jurisdiction database (zoning-ordinances/zoning_ordinance_links.json, 23
code-cited records) keys its rows two ways and this module resolves both:

* ``zoneomics_city_id`` — how the Zoneomics provider identifies a city. The
  Express backend matches on this today; kept for payload parity.
* the jurisdiction ``name`` — how the free provider identifies one, from the
  Census geocoder's incorporated-place name. An address outside any place is
  the unincorporated case, matched as '<county> County (unincorporated)', which
  is the exact spelling the database uses for its one unincorporated record.

Rule strings are not optional polish: address-street matching alone is legally
correct in 1 of the 23 jurisdictions (front-rule-summary.pdf has the counsel
sign-off). A miss here returns None and the engine falls back to its documented
default (address_street), flagged — never a silent wrong rule.

POC note: the database path points into the site repo's zoning-ordinances/
directory. In gaudi-api the same records would ship as a data asset with the
service; _DB_PATH is the single seam.
"""
import json
import os
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'zoning-ordinances', 'zoning_ordinance_links.json'))

_cached_db: Optional[List[Dict[str, Any]]] = None


def _log_error(message: str) -> None:
  """Best-effort log via the request-bound fx_logger; a no-op outside a request."""
  try:
    from flask import g
    g.fx_logger.log(message, channel_name='error')
  except Exception:
    pass


def _normalize_name(name: str) -> str:
  return ' '.join((name or '').lower().split())


def load_jurisdictions(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
  """The jurisdiction records, loaded once per process.

  @param db_path Override for tests; the default is the repo database.
  @return The records, or [] if the database cannot be read (logged, not raised).
  """
  global _cached_db
  if db_path is None and _cached_db is not None:
    return _cached_db
  path = db_path or _DB_PATH
  try:
    with open(path, encoding='utf-8') as handle:
      records = json.load(handle).get('jurisdictions') or []
  except Exception as error:
    _log_error('front_rules: cannot read jurisdiction db at %s: %s' % (path, error))
    records = []
  if db_path is None:
    _cached_db = records
  return records


def front_rule_for(city_id: Optional[int] = None, jurisdiction_name: Optional[str] = None,
                   county_name: Optional[str] = None,
                   db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
  """The front_rule record for a jurisdiction, or None if it is not in the database.

  @param city_id Zoneomics city id (Zoneomics-provider payloads).
  @param jurisdiction_name Incorporated place name from the Census geocoder,
    e.g. 'Palo Alto'. Pass None for an unincorporated address.
  @param county_name County base name, e.g. 'San Mateo' — used to resolve the
    unincorporated-county record when jurisdiction_name is None.
  @param db_path Override for tests.

  @return The record's ``front_rule`` dict ({rule, source, citation, ...}), or None.
  """
  records = load_jurisdictions(db_path)
  if city_id is not None:
    for record in records:
      if record.get('zoneomics_city_id') == int(city_id):
        return record.get('front_rule')
  wanted = _normalize_name(jurisdiction_name or '')
  if not wanted and county_name:
    wanted = _normalize_name('%s County (unincorporated)' % county_name)
  if wanted:
    for record in records:
      if _normalize_name(str(record.get('jurisdiction') or '')) == wanted:
        return record.get('front_rule')
  return None
