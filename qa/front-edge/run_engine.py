"""
run_engine.py
-------------
Phase B of the front-edge QA: the canonical engine run, one per selected lot.

Discovery (find_corner_lots.py) ran the engine in bulk and offline to *find*
corner lots. This runs it the way production will, once per lot:

  address -> fetch_parcel_context (Google geocode, county fabric, CA zoning)
          -> front_rule_for (jurisdiction database)
          -> label_edges WITH the Google Roads street namer

The lookup is by address string alone — no lat/lng shortcut — because that is
what a user does and what FutureLot is given, and because it re-tests the part
of the pipeline discovery skipped: whether a one-line address lands on the
parcel we think it does. The APN is checked against the selected lot and a
mismatch is recorded (``apn_match``), then the run is repeated pinned to the
parcel's own coordinate so a geocode drift costs a flag rather than the case.

Each lot is labeled TWICE, and the distinction matters:

* **census-only** — the corner test. Whether a lot is a corner is a fact about
  the parcel fabric, so this is what decides if the specimen is usable. If the
  production fetch says the lot is not a corner (discovery's 200-record fabric
  can truncate before an abutter), the next-best candidate is tried instead.
* **with the Roads namer** — the canonical labeling, the one compared against
  FutureLot, because it is what production does.

Keeping them apart is what makes ``roads_collapsed_frontage`` visible: on some
corner lots the Google Roads namer returns one street name for both frontages,
which merges them into a single frontage and moves the front onto the wrong
street. That is a finding to report, not a specimen to discard — so the lot is
kept and flagged.

  python3 qa/front-edge/run_engine.py [--jurisdiction NAME] [--no-roads]

Writes data/engine_results.json.
"""
import argparse
import os
import sys

from county_overrides import county_layer_for
from qa_common import (
  DATA_DIR, SESSION, analyze, google_key, read_json, run_labeling, write_json,
)
from services.parcel_data.fetch_parcel_context import fetch_parcel_context
from services.parcel_data.front_rules import front_rule_for


def _address_string(candidate):
  """The one-line address a user would type, from the county situs record."""
  city = candidate['jurisdiction']
  if city.endswith('(unincorporated)'):
    # No incorporated place to name; the situs city column is the postal town.
    # Some fabrics pack the state into it ('BOYES HOT SPRINGS, CA').
    city = (candidate.get('situs_city') or '').split(',')[0]
  parts = [candidate['address'].strip(), city.strip(), 'CA']
  return ', '.join(p for p in parts if p)


def _lookup(address, candidate, use_roads, pin_coordinate):
  """One end-to-end pipeline run; returns the record or {'error': ...}.

  Labels twice — census-only for the corner test, then with the requested
  namer for the canonical result — off ONE provider fetch, so the two views
  differ only in street naming.
  """
  context = fetch_parcel_context(
    address,
    google_api_key=google_key(),
    session=SESSION,
    lat=candidate['lat'] if pin_coordinate else None,
    lng=candidate['lng'] if pin_coordinate else None,
  )
  if context.get('error'):
    return {'error': context['error'], 'error_kind': context.get('error_kind')}

  meta = context.get('meta') or {}
  front_rule = front_rule_for(jurisdiction_name=meta.get('city_name'),
                              county_name=meta.get('county_name')) or {}
  def label(with_roads):
    return run_labeling(context['subject'], context.get('neighbors') or [],
                        front_rule, zone=context.get('zone'),
                        subject_street_name=context.get('subject_street_name'),
                        use_roads_namer=with_roads)

  census_labeled = label(False)
  census_analysis = analyze(census_labeled)
  labeled = label(True) if use_roads else census_labeled
  analysis = analyze(labeled) if use_roads else census_analysis
  return {
    'query_address': address,
    'pinned_to_parcel_coordinate': pin_coordinate,
    'resolved': {
      'apn': context['subject']['apn'],
      'situs': context['subject'].get('address'),
      'lat': context['subject']['lat'],
      'lng': context['subject']['lng'],
      'boundary': context['subject']['boundary'],
      'subject_street_name': context.get('subject_street_name'),
      'city_name': meta.get('city_name'),
      'county_name': meta.get('county_name'),
      'zone': context.get('zone'),
      'neighbor_count': len(context.get('neighbors') or []),
      'provider_flags': context.get('flags') or [],
    },
    'front_rule': {'rule': front_rule.get('rule'), 'citation': front_rule.get('citation'),
                   'has_overrides': bool(front_rule.get('overrides'))},
    'labeled': labeled,
    'analysis': analysis,
    # The corner test and the Roads-vs-census difference.
    'analysis_census': census_analysis,
    'is_corner_census': census_analysis['is_corner'],
    'roads_collapsed_frontage': bool(use_roads and census_analysis['is_corner']
                                     and not analysis['is_corner']),
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--jurisdiction', action='append')
  parser.add_argument('--fallbacks', type=int, default=4,
                      help='ranked candidates to fall through when a lot is not a corner')
  parser.add_argument('--no-roads', action='store_true',
                      help='skip the Google Roads namer (census-only street naming)')
  args = parser.parse_args()

  selected = read_json(os.path.join(DATA_DIR, 'selected.json'), {}) or {}
  candidates = read_json(os.path.join(DATA_DIR, 'candidates.json'), {}) or {}
  results = read_json(os.path.join(DATA_DIR, 'engine_results.json'), {}) or {}
  targets = args.jurisdiction or list(selected.keys())
  use_roads = not args.no_roads and bool(google_key())
  if not use_roads:
    print('note: running census-only (no Roads namer)', file=sys.stderr)

  for jurisdiction in targets:
    candidate = selected.get(jurisdiction)
    if candidate is None:
      print('!! no selected lot for %s' % jurisdiction, file=sys.stderr)
      continue
    # Discovery's fabric is one 200-record envelope; in a dense grid it can
    # truncate before one of a candidate's abutters, so a lot can look like a
    # corner there and not be one under the provider's own fetch. Fall through
    # the ranked candidates until one is a corner on the production path.
    attempts = [candidate] + [c for c in (candidates.get(jurisdiction) or [])
                              if c.get('jurisdiction_ok') and c['apn'] != candidate['apn']]
    record, tried = None, []
    with county_layer_for(jurisdiction) as overridden:
      if overridden:
        print('    NOTE: QA parcel-layer override in effect (see county_overrides.py)')
      for attempt_index, attempt in enumerate(attempts[:1 + args.fallbacks]):
        address = _address_string(attempt)
        print('== %s | %s%s' % (jurisdiction, address,
                                '' if attempt_index == 0 else ' (fallback %d)' % attempt_index))
        record = _lookup(address, attempt, use_roads, pin_coordinate=False)
        record['apn_match'] = (not record.get('error')
                               and record['resolved']['apn'] == attempt['apn'])
        if record.get('error') or not record['apn_match']:
          print('    address lookup %s; repeating pinned to the parcel coordinate'
                % (record.get('error') or 'landed on APN %s (wanted %s)'
                   % (record['resolved']['apn'], attempt['apn'])), file=sys.stderr)
          pinned = _lookup(address, attempt, use_roads, pin_coordinate=True)
          pinned['apn_match'] = (not pinned.get('error')
                                 and pinned['resolved']['apn'] == attempt['apn'])
          record = {'address_lookup': record, **pinned, 'used': 'pinned'}
        else:
          record['used'] = 'address'
        record['county_layer_override'] = overridden
        candidate = attempt
        if record.get('error'):
          tried.append({'address': address, 'reason': record['error']})
          continue
        if record['is_corner_census']:
          break
        tried.append({'address': address, 'reason': 'not a corner on the production path'})
        print('    not a corner under the provider\'s own fetch; trying the next candidate',
              file=sys.stderr)

    record['jurisdiction'] = jurisdiction
    record['rejected_candidates'] = tried
    record['selected'] = {'apn': candidate['apn'], 'address': candidate['address'],
                          'lat': candidate['lat'], 'lng': candidate['lng'],
                          'area_sqft': candidate['area_sqft'],
                          'zone_at_selection': candidate.get('jurisdiction_check', {}).get('zone_code')}
    results[jurisdiction] = record
    analysis = record.get('analysis') or {}
    front = analysis.get('front') or {}
    print('    rule=%s front=%s (%s ft, %s/%s) streets=%s flags=%s%s' % (
      (record.get('front_rule') or {}).get('rule'), front.get('street_name'),
      front.get('length_ft'), front.get('basis'), front.get('confidence'),
      ' + '.join(analysis.get('street_names') or []), analysis.get('lot_flags'),
      '  ROADS COLLAPSED FRONTAGE' if record.get('roads_collapsed_frontage') else ''))
    write_json(os.path.join(DATA_DIR, 'engine_results.json'), results)

  print('\nengine results for %d lots' % len(results))


if __name__ == '__main__':
  main()
