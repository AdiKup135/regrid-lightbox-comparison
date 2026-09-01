
// FutureLot front-edge probe — read-only GETs against the report route the
// page itself calls. Returns one record per QA lot.
(async () => {
  const QUERIES = [{"jurisdiction": "Healdsburg","params": {"addr_state": "ca","addr_city": "healdsburg","addr_zip": "","addr_street": "matheson street","addr_num": "407","lat": "38.6115055","lng": "-122.864658901203","property_id": ""}},{"jurisdiction": "Windsor","params": {"addr_state": "ca","addr_city": "windsor","addr_zip": "","addr_street": "mallory avenue","addr_num": "491","lat": "38.558955","lng": "-122.8111195","property_id": ""}},{"jurisdiction": "Contra Costa County (unincorporated)","params": {"addr_state": "ca","addr_city": "kensington","addr_zip": "","addr_street": "coventry road","addr_num": "845","lat": "37.9038705","lng": "-122.2787994744898","property_id": ""}},{"jurisdiction": "Marin County (unincorporated)","params": {"addr_state": "ca","addr_city": "kentfield","addr_zip": "","addr_street": "woodland road","addr_num": "233","lat": "37.9491115","lng": "-122.55792849997277","property_id": ""}},{"jurisdiction": "Napa County (unincorporated)","params": {"addr_state": "ca","addr_city": "ang","addr_zip": "","addr_street": "newton way","addr_num": "481","lat": "38.5813835","lng": "-122.44882493021989","property_id": ""}},{"jurisdiction": "Santa Clara County (unincorporated)","params": {"addr_state": "ca","addr_city": "san jose","addr_zip": "","addr_street": "cleveland avenue","addr_num": "99","lat": "37.325179000000006","lng": "-121.93019850571875","property_id": ""}},{"jurisdiction": "Sonoma County (unincorporated)","params": {"addr_state": "ca","addr_city": "boyes hot springs, ca","addr_zip": "","addr_street": "calle del monte","addr_num": "365","lat": "38.313581","lng": "-122.47897099496583","property_id": ""}}];
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

