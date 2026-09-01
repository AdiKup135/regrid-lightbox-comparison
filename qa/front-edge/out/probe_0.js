
// FutureLot front-edge probe — read-only GETs against the report route the
// page itself calls. Returns one record per QA lot.
(async () => {
  const QUERIES = [{"jurisdiction": "Lafayette","params": {"addr_state": "ca","addr_city": "lafayette","addr_zip": "","addr_street": "glenside drive","addr_num": "680","lat": "37.8742795","lng": "-122.09515481807512","property_id": ""}},{"jurisdiction": "Moraga","params": {"addr_state": "ca","addr_city": "moraga","addr_zip": "","addr_street": "camino ricardo","addr_num": "838","lat": "37.844348","lng": "-122.13504794104378","property_id": ""}},{"jurisdiction": "Orinda","params": {"addr_state": "ca","addr_city": "orinda","addr_zip": "","addr_street": "northwood drive","addr_num": "9","lat": "37.879032","lng": "-122.18039253897602","property_id": ""}},{"jurisdiction": "Fairfax","params": {"addr_state": "ca","addr_city": "fairfax","addr_zip": "","addr_street": "scenic road","addr_num": "73","lat": "37.990252999999996","lng": "-122.59543035697197","property_id": ""}},{"jurisdiction": "Mill Valley","params": {"addr_state": "ca","addr_city": "mill valley","addr_zip": "","addr_street": "ethel avenue","addr_num": "329","lat": "37.900816000000006","lng": "-122.54340559545456","property_id": ""}},{"jurisdiction": "Sausalito","params": {"addr_state": "ca","addr_city": "sausalito","addr_zip": "","addr_street": "glen drive","addr_num": "299","lat": "37.857106","lng": "-122.48954714161073","property_id": ""}},{"jurisdiction": "Napa","params": {"addr_state": "ca","addr_city": "napa","addr_zip": "","addr_street": "laurel street","addr_num": "1795","lat": "38.292471","lng": "-122.29404648606811","property_id": ""}}];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const out = [];
  for (const q of QUERIES) {
    const url = '/api/street-data?params=' + encodeURIComponent(JSON.stringify(q.params));
    let rec = { jurisdiction: q.jurisdiction, params: q.params };
    try {
      const res = await fetch(url, { credentials: 'include' });
      rec.status = res.status;
      if (res.ok) {
        const j = await res.json();
        const simplified = j.lot_simplified || {};
        rec.lot = (simplified.lot || j.lot || {}).coordinates || null;
        rec.edges = (simplified.lot_edges || []).map(e => ({
          type: e.edge_type,
          len: Math.round(e.length * 10) / 10,
          v: (e.vertexes || []).map(p => [Math.round(p[0] * 1e6) / 1e6, Math.round(p[1] * 1e6) / 1e6]),
        }));
        const a = j.attributes || {};
        rec.attributes = { address: a.address, zone_code: a.zone_code,
                           lot_size: a.lot_size, property_id: a.property_id,
                           parcel_id: a.parcel_id, county: a.county,
                           zoning_jurisdiction: a.zoning_jurisdiction,
                           canonical_url: a.canonical_url };
        // The detached-ADU column of the sidebar the screenshots show:
        // ext_setbacks is the exterior (detached) ADU, int_setbacks the interior.
        const placement = ((j.bylaws || {}).adu || {}).placement || {};
        const pick = s => s ? { front_val: s.front_val, front: s.front,
                                side_val: s.side_val, side: s.side,
                                rear_val: s.rear_val, rear: s.rear } : null;
        rec.adu_setbacks = { ext: pick(placement.ext_setbacks),
                             int: pick(placement.int_setbacks),
                             status: placement.status };
      } else {
        rec.body = (await res.text()).slice(0, 200);
      }
    } catch (e) {
      rec.error = String(e);
    }
    out.push(rec);
    await sleep(1200);
  }
  return JSON.stringify(out);
})()

