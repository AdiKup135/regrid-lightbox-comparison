"""
county_registry.py
------------------
The six county parcel-fabric endpoints behind the free ("opendata") provider.

Parcel data in California is county-published open data: every county in our
23-jurisdiction territory exposes its assessor parcel layer as a keyless ArcGIS
REST service. This registry is the single place those per-county decisions
live — which layer, which field is the APN, and how to reconstruct a situs
address. Everything else (arcgis_parcel_client, fetch_parcel_context) is
county-agnostic and reads its instructions from here.

Two situs shapes exist in the wild, so a config declares one of two modes:

* ``fields`` — the parcel layer itself carries situs columns; the address is
  the ordered non-empty components joined with spaces.
* ``join``   — the parcel layer is geometry-only (Marin, San Mateo) and a
  companion address point layer is queried by APN in one batched ``IN (...)``
  call; components then come from that layer's rows.

Endpoints were verified live 2026-08-30 (metadata + point query). Known data
caveats are recorded per county in ``notes`` and surfaced to callers via
``vintage_flag`` so downstream can see, e.g., that San Mateo's public fabric
was last edited in 2020.

Keys are county FIPS codes as returned by the Census geocoder (state 06 +
county), which is how fetch_parcel_context selects a config.
"""
from typing import Dict, List, Optional

# One county's parcel-fabric access instructions. Plain dicts rather than a
# dataclass: the registry is declarative config, read-only, and json-dumpable
# for debug endpoints.
CountyConfig = Dict[str, object]

COUNTY_REGISTRY: Dict[str, CountyConfig] = {
  # Contra Costa — Lafayette, Moraga, Orinda.
  '06013': {
    'fips': '06013',
    'name': 'Contra Costa',
    'parcel_layer_url': 'https://gis.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0',
    'apn_field': 'APN',
    'situs_mode': 'fields',
    # S_STR_NBR is null across the fabric (verified live); the house number only
    # exists inside the pre-composed column, which may carry a unit token
    # between number and street ('3664 E104 MT DIABLO BLVD').
    'situs_components': ['full_address_search'],
    'city_field': 's_city',
    'notes': 'County-hosted MapServer. Granular situs columns exist but their number column is unpopulated.',
  },
  # Marin — Fairfax, Mill Valley, Sausalito.
  '06041': {
    'fips': '06041',
    'name': 'Marin',
    'parcel_layer_url': 'https://services6.arcgis.com/T8eS7sop5hLmgRRH/arcgis/rest/services/Parcels/FeatureServer/0',
    'apn_field': 'Parcel',
    'situs_mode': 'join',
    'situs_join': {
      'layer_url': 'https://services6.arcgis.com/T8eS7sop5hLmgRRH/arcgis/rest/services/Situs_Address_Points/FeatureServer/0',
      'apn_field': 'Parcel',
      'components': ['Number', 'PreDir', 'Street', 'Suffix'],
      'city_field': 'MailCity',
    },
    'notes': 'Parcel layer is geometry+APN only; situs joined from the Situs Address Points layer. Fabric current (edited 2026-06).',
  },
  # Napa — the city of Napa.
  '06055': {
    'fips': '06055',
    'name': 'Napa',
    'parcel_layer_url': 'https://services.arcgis.com/KYQI4l6C3kTBM5OU/arcgis/rest/services/Parcels_County/FeatureServer/0',
    'apn_field': 'ASMT',
    'situs_mode': 'fields',
    'situs_components': ['StreetNum', 'StreetDir', 'Street', 'StreetType'],
    'city_field': 'Community',
    'notes': 'Managed jointly by Napa County GIS + City of Napa GIS; also carries Jurisdiction and Zoning columns. '
             'Alternate: Napa_County_Public_Parcels on services1.arcgis.com/Ko5rxt00spOfjMqj.',
  },
  # San Mateo — Atherton, Hillsborough, Menlo Park, Portola Valley, San Carlos,
  # San Mateo, and unincorporated San Mateo County.
  '06081': {
    'fips': '06081',
    'name': 'San Mateo',
    'parcel_layer_url': 'https://services.arcgis.com/yq3FgOI44hYHAFVZ/arcgis/rest/services/APN_SUB_ADDRESSMETRICS/FeatureServer/1',
    'apn_field': 'APN',
    'situs_mode': 'join',
    # Geometry from the county's AGOL fabric; situs from the county's Socrata
    # portal (data.smcgov.org "Parcels", updated 2024-08, pre-composed
    # situs_addr). The AGOL companion address layer looked right but covers
    # Daly City only; the Socrata table is countywide. Its own geometry column
    # is WKT text in State Plane (not queryable spatially), hence the hybrid.
    'situs_join': {
      'kind': 'socrata',
      'resource_url': 'https://data.smcgov.org/resource/nr6j-72z7.json',
      'apn_field': 'apn',
      'components': ['situs_addr'],
      'city_field': 'situs_city',
    },
    'vintage_flag': 'parcel_fabric_vintage_2020',
    'notes': 'Geometry fabric last edited 2020-06 (county portal maps.smcgov.org was unreachable when surveyed); '
             'situs joined from data.smcgov.org nr6j-72z7. Swap geometry for the official service when reachable.',
  },
  # Santa Clara — Los Altos, Los Altos Hills, Mountain View, Palo Alto,
  # San Jose, Saratoga, Sunnyvale.
  '06085': {
    'fips': '06085',
    'name': 'Santa Clara',
    'parcel_layer_url': 'https://services8.arcgis.com/fpjs8A5Vtkshblnd/arcgis/rest/services/Santa_Clara_County_Parcels/FeatureServer/0',
    'apn_field': 'apn',
    'situs_mode': 'fields',
    'situs_components': ['situs_hous', 'situs_stre', 'situs_st_1', 'situs_st_2'],
    'city_field': 'situs_city',
    'notes': 'situs_st_1 is the street name, situs_st_2 the type; situs_stre observed empty and kept for safety.',
  },
  # Sonoma — Healdsburg, Windsor.
  '06097': {
    'fips': '06097',
    'name': 'Sonoma',
    'parcel_layer_url': 'https://socogis.sonomacounty.ca.gov/map/rest/services/OWTSPublic/Cities_GIS_Parcel_Base/FeatureServer/0',
    'apn_field': 'APN',
    'situs_mode': 'fields',
    'situs_components': ['SitusStreetNo', 'SitusDirection', 'SitusStreetName', 'SitusStreetType'],
    'city_field': 'SitusCity',
    'notes': 'County-hosted; SitusFormatted1 also exists as a pre-composed alternative.',
  },
}


def county_for_fips(fips: Optional[str]) -> Optional[CountyConfig]:
  """Look up the parcel-fabric config for a Census county GEOID.

  @param fips Five-digit state+county FIPS, e.g. '06085' (Santa Clara).
  @return The county config, or None for counties outside the territory.
  """
  return COUNTY_REGISTRY.get(fips or '')


def county_for_name(name: Optional[str]) -> Optional[CountyConfig]:
  """Look up a county config by base name ('Santa Clara') — the fallback key
  when only a Google geocode is available and the Census containment lookup
  failed. Tolerates a trailing ' County'."""
  wanted = (name or '').strip().lower()
  if wanted.endswith(' county'):
    wanted = wanted[:-len(' county')].strip()
  for config in COUNTY_REGISTRY.values():
    if str(config['name']).lower() == wanted:
      return config
  return None


def supported_counties() -> List[str]:
  """Names of the counties the registry can serve, for error messages."""
  return sorted(str(config['name']) for config in COUNTY_REGISTRY.values())
