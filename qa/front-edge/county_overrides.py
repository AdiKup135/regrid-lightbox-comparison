"""
county_overrides.py
-------------------
QA-local parcel-layer substitutions. Nothing here edits the repo.

Phase A turned up a real gap rather than a bad seed: the Sonoma layer in
``services/parcel_data/county_registry.py`` is
``OWTSPublic/Cities_GIS_Parcel_Base``, and — as its name says — it carries the
county's *cities*. Point queries in unincorporated Sonoma come back empty:

    Boyes Hot Springs  0 parcels   Census place: None
    Penngrove          0 parcels   Census place: None
    Guerneville        0 parcels   Census place: None
    Graton             0 parcels   Census place: None

So the provider cannot serve an address in unincorporated Sonoma County at
all, and the jurisdiction's ``owner_elected`` front rule is unreachable
end-to-end. That is a finding for the registry, not something to paper over —
it is written up in the report.

To still exercise the rule, this module supplies a substitute layer the county
also publishes, ``OneStopMapPublic/One_Stop_Parcels``, which does cover
unincorporated territory (verified live: a point query in Guerneville returns
APN 070-050-018, 16129 Main St). It is applied ONLY while the named
jurisdictions are being processed — Healdsburg and Windsor keep running against
the registry's own layer, so the QA does not quietly re-baseline the counties
that work — and every result produced under a substitution is stamped with
``county_layer_override``.
"""
from contextlib import contextmanager

import qa_common  # noqa: F401  — puts gaudi-api-port on sys.path
from services.parcel_data.county_registry import COUNTY_REGISTRY

# jurisdiction name -> a CountyConfig that replaces its county's registry entry
# for the duration of that jurisdiction's processing.
OVERRIDES = {
  'Sonoma County (unincorporated)': {
    'fips': '06097',
    'name': 'Sonoma',
    'parcel_layer_url': 'https://socogis.sonomacounty.ca.gov/map/rest/services/'
                        'OneStopMapPublic/One_Stop_Parcels/MapServer/0',
    'apn_field': 'APN',
    'situs_mode': 'fields',
    'situs_components': ['SitusAddress'],
    'city_field': 'SitusCityState',
    'notes': 'QA substitute for the registry Sonoma layer, which covers incorporated cities only. '
             'Countywide; carries Jurisdiction, PRMDZoning and situs columns.',
    'qa_override': True,
  },
}


@contextmanager
def county_layer_for(jurisdiction):
  """Swap in a substitute parcel layer while one jurisdiction is processed.

  @param jurisdiction The jurisdiction name being processed.
  @return Yields True if a substitution is in effect, False otherwise.
  """
  override = OVERRIDES.get(jurisdiction)
  if override is None:
    yield False
    return
  fips = str(override['fips'])
  original = COUNTY_REGISTRY.get(fips)
  COUNTY_REGISTRY[fips] = override
  try:
    yield True
  finally:
    if original is None:
      COUNTY_REGISTRY.pop(fips, None)
    else:
      COUNTY_REGISTRY[fips] = original
