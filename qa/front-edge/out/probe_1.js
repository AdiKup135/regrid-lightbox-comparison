
// FutureLot front-edge probe — read-only GETs against the report route the
// page itself calls. Returns one record per QA lot.
(async () => {
  const QUERIES = [{"jurisdiction": "Atherton","params": {"addr_state": "ca","addr_city": "atherton","addr_zip": "","addr_street": "prior lane","addr_num": "256","lat": "37.465787500000005","lng": "-122.18717946814894","property_id": ""}},{"jurisdiction": "Hillsborough","params": {"addr_state": "ca","addr_city": "hillsborough","addr_zip": "","addr_street": "homeplace court","addr_num": "5","lat": "37.564085000000006","lng": "-122.36243805604988","property_id": ""}},{"jurisdiction": "Menlo Park","params": {"addr_state": "ca","addr_city": "menlo park","addr_zip": "","addr_street": "oak grove avenue","addr_num": "385","lat": "37.457300000000004","lng": "-122.18180236173913","property_id": ""}},{"jurisdiction": "Portola Valley","params": {"addr_state": "ca","addr_city": "portola valley","addr_zip": "","addr_street": "echo lane","addr_num": "247","lat": "37.3712855","lng": "-122.2092626072853","property_id": ""}},{"jurisdiction": "San Carlos","params": {"addr_state": "ca","addr_city": "san carlos","addr_zip": "","addr_street": "birch avenue","addr_num": "2000","lat": "37.495593","lng": "-122.26240003571428","property_id": ""}},{"jurisdiction": "San Mateo","params": {"addr_state": "ca","addr_city": "san mateo","addr_zip": "","addr_street": "barneson avenue","addr_num": "550","lat": "37.5490395","lng": "-122.32465650699815","property_id": ""}},{"jurisdiction": "San Mateo County (unincorporated)","params": {"addr_state": "ca","addr_city": "redwood city","addr_zip": "","addr_street": "6th avenue","addr_num": "843","lat": "37.481102","lng": "-122.19806842619747","property_id": ""}}];
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

