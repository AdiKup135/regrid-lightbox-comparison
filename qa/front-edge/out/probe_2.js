
// FutureLot front-edge probe — read-only GETs against the report route the
// page itself calls. Returns one record per QA lot.
(async () => {
  const QUERIES = [{"jurisdiction": "Los Altos","params": {"addr_state": "ca","addr_city": "los altos","addr_zip": "","addr_street": "lyell street","addr_num": "58","lat": "37.3753325","lng": "-122.11274900000001","property_id": ""}},{"jurisdiction": "Los Altos Hills","params": {"addr_state": "ca","addr_city": "los altos hills","addr_zip": "","addr_street": "donelson place","addr_num": "14100","lat": "37.3828155","lng": "-122.13540884967321","property_id": ""}},{"jurisdiction": "Mountain View","params": {"addr_state": "ca","addr_city": "mountain view","addr_zip": "","addr_street": "church street","addr_num": "120","lat": "37.385372000000004","lng": "-122.0759211473684","property_id": ""}},{"jurisdiction": "Palo Alto","params": {"addr_state": "ca","addr_city": "palo alto","addr_zip": "","addr_street": "coleridge avenue","addr_num": "589","lat": "37.4408775","lng": "-122.14475001267226","property_id": ""}},{"jurisdiction": "San Jose","params": {"addr_state": "ca","addr_city": "san jose","addr_zip": "","addr_street": "michigan avenue","addr_num": "1098","lat": "37.3030425","lng": "-121.89597972222796","property_id": ""}},{"jurisdiction": "Saratoga","params": {"addr_state": "ca","addr_city": "saratoga","addr_zip": "","addr_street": "braemar drive","addr_num": "19740","lat": "37.271647","lng": "-122.01805469565218","property_id": ""}},{"jurisdiction": "Sunnyvale","params": {"addr_state": "ca","addr_city": "sunnyvale","addr_zip": "","addr_street": "jackson street","addr_num": "274","lat": "37.382249","lng": "-122.02477803647791","property_id": ""}}];
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

