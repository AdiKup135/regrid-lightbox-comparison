import { useState, useEffect, useRef, useMemo } from 'react';
import Split from 'react-split';
import Map, { Source, Layer } from 'react-map-gl';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

interface RegridSuggestion {
  type: 'Feature';
  properties: {
    address: string;
    ll_uuid: string;
    score: number;
    context: string;
    path: string;
  };
  geometry: {
    type: 'Point';
    coordinates: [number, number]; // [lon, lat]
  };
}

interface RegridParcel {
  parcels?: { features: Array<{ properties: Record<string, unknown>; geometry: unknown }> };
}

interface LightboxSuggestion {
  id: string;
  label: string;
  location?: {
    streetAddress?: string;
    locality?: string;
    regionCode?: string;
    postalCode?: string;
    representativePoint?: { longitude: number; latitude: number };
  };
  parcels?: Array<{ id: string }>;
}

type GeoJsonFC = { type: 'FeatureCollection'; features: Array<{ type: 'Feature'; geometry: unknown; properties?: Record<string, unknown> }> };

function wktToGeoJson(wkt: string): GeoJsonFC | null {
  if (!wkt || typeof wkt !== 'string') return null;
  const polyMatch = wkt.match(/POLYGON\s*\(\(([^()]+)\)\)/);
  const multiMatch = wkt.match(/MULTIPOLYGON\s*\(((?:\(\([^()]+\)\),?)+)\)/);
  const parseRing = (s: string): number[][] => {
    const coords = s.split(/,\s*/).map((p) => {
      const [lon, lat] = p.trim().split(/\s+/).map(Number);
      return [lon, lat];
    });
    if (coords.length < 3) return [];
    if (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1]) {
      coords.push(coords[0]);
    }
    return coords;
  };
  if (polyMatch) {
    const ring = parseRing(polyMatch[1]);
    if (ring.length < 3) return null;
    return {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [ring] }, properties: {} }],
    };
  }
  if (multiMatch) {
    const polygons = multiMatch[1].match(/\(\([^()]+\)\)/g) ?? [];
    const features = polygons
      .map((p) => {
        const ring = parseRing(p.replace(/^\(\(|\)\)$/g, ''));
        return ring.length >= 3 ? { type: 'Feature' as const, geometry: { type: 'Polygon' as const, coordinates: [ring] }, properties: {} as Record<string, unknown> } : null;
      })
      .filter((x): x is NonNullable<typeof x> => x != null);
    return features.length ? { type: 'FeatureCollection', features } : null;
  }
  return null;
}

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';

/** Compute bbox from view center and zoom (degrees). Used for transmission lines fetch. */
function viewStateBbox(vs: { longitude: number; latitude: number; zoom: number }, bufferMultiplier = 2): [number, number, number, number] {
  const degPerTile = 360 / Math.pow(2, vs.zoom);
  const buffer = degPerTile * bufferMultiplier;
  return [vs.longitude - buffer, vs.latitude - buffer, vs.longitude + buffer, vs.latitude + buffer];
}

/** Extract [minLon, minLat, maxLon, maxLat] from GeoJSON with buffer (degrees). */
function geoJsonBbox(fc: GeoJsonFC | null, bufferDeg = 0.02): [number, number, number, number] | null {
  if (!fc?.features?.length) return null;
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  const collect = (coords: number[][]) => {
    for (const [lon, lat] of coords) {
      if (lon < minLon) minLon = lon;
      if (lat < minLat) minLat = lat;
      if (lon > maxLon) maxLon = lon;
      if (lat > maxLat) maxLat = lat;
    }
  };
  for (const f of fc.features) {
    const g = (f as { geometry?: { type?: string; coordinates?: unknown } }).geometry;
    if (!g?.coordinates) continue;
    if (g.type === 'Point') collect([g.coordinates as number[]]);
    else if (g.type === 'LineString') collect(g.coordinates as number[][]);
    else if (g.type === 'Polygon') for (const ring of g.coordinates as number[][][]) collect(ring);
    else if (g.type === 'MultiPolygon') for (const poly of g.coordinates as number[][][][]) for (const ring of poly) collect(ring);
  }
  if (minLon === Infinity) return null;
  return [minLon - bufferDeg, minLat - bufferDeg, maxLon + bufferDeg, maxLat + bufferDeg];
}

function haversineMeters(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function allEdgesFt(geom: unknown): number[] {
  const rings: number[][][] = [];
  const pushRing = (coords: number[][]) => { if (coords.length >= 2) rings.push(coords); };
  const g = geom as { type?: string; coordinates?: unknown };
  if (g?.type === 'Polygon' && Array.isArray(g.coordinates)) {
    for (const ring of g.coordinates as number[][][]) pushRing(ring);
  } else if (g?.type === 'MultiPolygon' && Array.isArray(g.coordinates)) {
    for (const poly of g.coordinates as number[][][][]) for (const ring of poly) pushRing(ring);
  }
  const edges: number[] = [];
  for (const ring of rings) {
    for (let i = 0; i < ring.length - 1; i++) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[i + 1];
      const m = haversineMeters(lon1, lat1, lon2, lat2);
      const ft = m * 3.28084;
      if (ft > 0) edges.push(ft);
    }
  }
  return edges;
}

function shortestEdgeFt(geom: unknown): number | null {
  const edges = allEdgesFt(geom);
  if (!edges.length) return null;
  return Math.min(...edges);
}

/** Shortest parcel edge that is >= minFt (excludes edges smaller than largest building edge). */
function shortestEdgeFtWithMin(geom: unknown, minFt: number): number | null {
  const edges = allEdgesFt(geom).filter((e) => e >= minFt);
  if (!edges.length) return null;
  return Math.min(...edges);
}

/** Longest edge of a polygon (used to get largest building edge). */
function longestEdgeFt(geom: unknown): number | null {
  const edges = allEdgesFt(geom);
  if (!edges.length) return null;
  return Math.max(...edges);
}

const SECTION_HEADER: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem', marginTop: '0.75rem' };

function LightboxDetailedReview({ data, femaData, riskIndexData, wetlandsData }: {
  data: unknown;
  femaData: { nfhls?: Array<Record<string, unknown>> } | null;
  riskIndexData: Record<string, unknown> | null;
  wetlandsData: Record<string, unknown> | null;
}) {
  if (!data || typeof data !== 'object') return null;
  const parcels = (data as { parcels?: Array<Record<string, unknown>> }).parcels;
  const p = parcels?.[0];
  if (!p) return null;

  const s = (v: unknown): string => (v != null && v !== '' ? String(v) : '—');
  const money = (v: unknown): string => {
    if (typeof v !== 'number') return '—';
    return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  };
  const pct = (v: unknown): string => (typeof v === 'number' ? `${v}%` : '—');

  const owner = p.owner as { names?: Array<{ fullName?: string }>; streetAddress?: string; ownershipStatus?: { code?: string; description?: string } } | undefined;
  const occupant = p.occupant as { owner?: boolean; company?: boolean } | undefined;
  const assessment = p.assessment as Record<string, unknown> | undefined;
  const lot = assessment?.lot as { lotNumber?: string; blockNumber?: string; size?: number } | undefined;
  const av = assessment?.assessedValue as { total?: number; land?: number; improvements?: number; year?: string } | undefined;
  const transaction = p.transaction as { lastMarketSale?: Record<string, unknown> } | undefined;
  const sale = transaction?.lastMarketSale as Record<string, unknown> | undefined;
  const loan = p.lastLoan as Record<string, unknown> | undefined;
  const legal = p.legalDescription as string[] | undefined;
  const census = p.census as { blockGroup?: string; tract?: string } | undefined;
  const derived = p.derived as { calculatedLotArea?: number } | undefined;
  const primary = p.primaryStructure as { yearBuilt?: string; yearRenovated?: string; livingArea?: number; units?: number } | undefined;

  const nfhl = (femaData?.nfhls as Array<Record<string, unknown>> | undefined)?.[0];
  const zones = nfhl?.zones as Array<{ zone?: string; description?: string; subtype?: string }> | undefined;
  const panel = nfhl?.panel as Record<string, unknown> | undefined;

  const nri = ((riskIndexData as Record<string, unknown>)?.nris as Array<Record<string, unknown>> | undefined)?.[0];
  const eal = nri?.expectedAnnualLoss as Record<string, unknown> | undefined;
  const sv = nri?.socialVulnerability as Record<string, unknown> | undefined;
  const cr = nri?.communityResilience as Record<string, unknown> | undefined;

  const hazardNames: [string, string][] = [
    ['earthquake', 'Earthquake'], ['lightning', 'Lightning'], ['tornado', 'Tornado'],
    ['heatWave', 'Heat Wave'], ['hail', 'Hail'], ['strongWind', 'Strong Wind'],
    ['landslide', 'Landslide'], ['coastalFlooding', 'Coastal Flooding'], ['drought', 'Drought'],
    ['riverineFlooding', 'Riverine Flooding'], ['tsunami', 'Tsunami'], ['wildfire', 'Wildfire'],
    ['winterWeather', 'Winter Weather'], ['coldWave', 'Cold Wave'], ['avalanche', 'Avalanche'],
    ['hurricane', 'Hurricane'], ['iceStorm', 'Ice Storm'], ['volcanicActivity', 'Volcanic Activity'],
  ];

  const wetlands = (wetlandsData as Record<string, unknown>)?.wetlands as Array<Record<string, unknown>> | undefined;

  return (
    <>
      {/* Ownership */}
      <div style={SECTION_HEADER}>Ownership</div>
      <ExpandableField label="Owner(s)" value={owner?.names?.map((n) => n.fullName).filter(Boolean).join(' & ') || '—'} detail="From parcels[0].owner.names[].fullName" />
      <ExpandableField label="Ownership status" value={owner?.ownershipStatus ? `${owner.ownershipStatus.description} (${owner.ownershipStatus.code})` : '—'} detail="From parcels[0].owner.ownershipStatus" />
      <ExpandableField label="Owner-occupied" value={occupant?.owner != null ? (occupant.owner ? 'Yes' : 'No') : '—'} detail="From parcels[0].occupant.owner" />
      <ExpandableField label="Company-owned" value={occupant?.company != null ? (occupant.company ? 'Yes' : 'No') : '—'} detail="From parcels[0].occupant.company" />

      {/* Lot & Site */}
      <div style={SECTION_HEADER}>Lot & Site</div>
      <ExpandableField label="Lot / Block" value={lot?.lotNumber || lot?.blockNumber ? `Lot ${s(lot?.lotNumber)}, Block ${s(lot?.blockNumber)}` : '—'} detail="From assessment.lot.lotNumber / blockNumber" />
      <ExpandableField label="Assessed lot size" value={lot?.size != null ? `${lot.size.toLocaleString()} sqm (${Math.round(lot.size * 10.7639).toLocaleString()} sqft)` : '—'} detail="From assessment.lot.size (in square meters)" />
      <ExpandableField label="Calculated lot area" value={derived?.calculatedLotArea != null ? `${derived.calculatedLotArea.toLocaleString()} sqm (${Math.round(derived.calculatedLotArea * 10.7639).toLocaleString()} sqft)` : '—'} detail="From derived.calculatedLotArea" />
      <ExpandableField label="Legal description" value={legal?.length ? legal.join('; ') : '—'} detail="From parcels[0].legalDescription" />
      <ExpandableField label="Census tract / block group" value={census ? `${s(census.tract)} / ${s(census.blockGroup)}` : '—'} detail="From parcels[0].census" />
      {primary?.yearBuilt && <ExpandableField label="Year built" value={s(primary.yearBuilt)} detail="From primaryStructure.yearBuilt" />}
      {primary?.yearRenovated && <ExpandableField label="Year renovated" value={s(primary.yearRenovated)} detail="From primaryStructure.yearRenovated" />}

      {/* Valuation & Assessment */}
      {av && (
        <>
          <div style={SECTION_HEADER}>Valuation & Assessment {av.year ? `(${av.year})` : ''}</div>
          <ExpandableField label="Total assessed value" value={money(av.total)} detail="From assessment.assessedValue.total" />
          <ExpandableField label="Land value" value={money(av.land)} detail="From assessment.assessedValue.land" />
          <ExpandableField label="Improvements" value={money(av.improvements)} detail="From assessment.assessedValue.improvements" />
          <ExpandableField label="Improvement %" value={pct(assessment?.improvementPercent)} detail="From assessment.improvementPercent" />
          {assessment?.avm && <ExpandableField label="AVM (Automated Valuation)" value={money(Number(assessment.avm))} detail="From assessment.avm" />}
          {(p.tax as Record<string, unknown>)?.amount != null && <ExpandableField label="Annual tax" value={`${money((p.tax as Record<string, unknown>).amount)} (${s((p.tax as Record<string, unknown>).year)})`} detail="From parcels[0].tax.amount / year" />}
        </>
      )}

      {/* Transaction History */}
      {sale && (
        <>
          <div style={SECTION_HEADER}>Last Sale</div>
          <ExpandableField label="Sale date" value={sale.transferDate ? new Date(String(sale.transferDate)).toLocaleDateString() : '—'} detail="From transaction.lastMarketSale.transferDate" />
          <ExpandableField label="Sale price" value={money(sale.value)} detail="From transaction.lastMarketSale.value" />
          <ExpandableField label="Seller" value={s(sale.seller)} detail="From transaction.lastMarketSale.seller" />
          <ExpandableField label="Buyer" value={s(sale.buyer)} detail="From transaction.lastMarketSale.buyer" />
          <ExpandableField label="Document type" value={s(sale.documentTypeDescription)} detail="From transaction.lastMarketSale.documentTypeDescription" />
          {sale.titleCompany && <ExpandableField label="Title company" value={s(sale.titleCompany)} detail="From transaction.lastMarketSale.titleCompany" />}
        </>
      )}

      {/* Last Loan */}
      {loan && (loan.lender || loan.value) && (
        <>
          <div style={SECTION_HEADER}>Last Recorded Loan</div>
          <ExpandableField label="Lender" value={s(loan.lender)} detail="From lastLoan.lender" />
          <ExpandableField label="Loan amount" value={money(loan.value)} detail="From lastLoan.value" />
          {loan.recordingDate && <ExpandableField label="Recording date" value={new Date(String(loan.recordingDate)).toLocaleDateString()} detail="From lastLoan.recordingDate" />}
          {loan.dueDate && <ExpandableField label="Due date" value={new Date(String(loan.dueDate)).toLocaleDateString()} detail="From lastLoan.dueDate" />}
        </>
      )}

      {/* Flood Hazard */}
      {nfhl && (
        <>
          <div style={SECTION_HEADER}>Flood Hazard (FEMA NFHL)</div>
          <ExpandableField label="Special Flood Hazard Area" value={nfhl.sfha != null ? (nfhl.sfha ? 'Yes' : 'No') : '—'} detail="SFHA designation. From nfhls[0].sfha" alwaysShow />
          <ExpandableField label="In 100-year flood zone" value={nfhl.isIn100Year != null ? (nfhl.isIn100Year ? 'Yes' : 'No') : '—'} detail="From nfhls[0].isIn100Year" alwaysShow />
          {zones?.[0] && <ExpandableField label="Flood zone" value={`${zones[0].zone} — ${zones[0].description ?? ''}${zones[0].subtype ? ` (${zones[0].subtype})` : ''}`} detail="From nfhls[0].zones[0]" />}
          <ExpandableField label="Effective date" value={nfhl.effectiveDate ? new Date(String(nfhl.effectiveDate)).toLocaleDateString() : '—'} detail="DFIRM effective date" />
          {panel?.panelId && <ExpandableField label="Panel / DFIRM" value={`${s(panel.panelId)} / ${s(nfhl.dfirmId)}`} detail="From nfhls[0].panel.panelId and dfirmId" />}
        </>
      )}

      {/* FEMA Risk Index */}
      {nri && (
        <>
          <div style={SECTION_HEADER}>Natural Hazard Risk (FEMA NRI)</div>
          <ExpandableField label="Overall risk" value={`${s(nri.rating)} — Score ${s(nri.score)}`} detail={`National percentile: ${s(nri.nationalPercentile)}. State percentile: ${s(nri.statePercentile)}. County score: ${s(nri.countyScore)} (${s(nri.countyRating)}).`} alwaysShow />
          {eal && <ExpandableField label="Expected annual loss" value={`${money(eal.total)} (${s(eal.rating)})`} detail={`EAL score: ${s(eal.score)}. National percentile: ${s(eal.nationalPercentile)}. State percentile: ${s(eal.statePercentile)}. County total: ${money(eal.countyTotal)}.`} />}
          {sv && <ExpandableField label="Social vulnerability" value={`${s(sv.rating)} — Score ${s(sv.score)}`} detail={`National percentile: ${s(sv.nationalPercentile)}. State percentile: ${s(sv.statePercentile)}.`} />}
          {cr && <ExpandableField label="Community resilience" value={`${s(cr.rating)} — Score ${s(cr.score)}`} detail={`National percentile: ${s(cr.nationalPercentile)}. State percentile: ${s(cr.statePercentile)}.`} />}
          <ExpandableField label="Population (census tract)" value={typeof nri.population === 'number' ? nri.population.toLocaleString() : '—'} detail="From riskindexes.nris[0].population" />

          <div style={{ ...SECTION_HEADER, fontSize: '0.75rem', marginTop: '0.5rem' }}>Hazard Breakdown</div>
          <div style={{ fontSize: '0.75rem', lineHeight: 1.4, marginBottom: '0.5rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                  <th style={{ padding: '2px 4px' }}>Hazard</th>
                  <th style={{ padding: '2px 4px' }}>Risk Rating</th>
                  <th style={{ padding: '2px 4px', textAlign: 'right' }}>Annual Loss</th>
                </tr>
              </thead>
              <tbody>
                {hazardNames.map(([key, label]) => {
                  const h = nri[key] as { annualLoss?: { total?: number; rating?: string }; hazardTypeRiskIndex?: { rating?: string } } | undefined;
                  if (!h) return null;
                  const rating = h.hazardTypeRiskIndex?.rating ?? h.annualLoss?.rating ?? '—';
                  if (rating === 'Not Applicable') return null;
                  const loss = h.annualLoss?.total;
                  return (
                    <tr key={key} style={{ borderBottom: '1px solid #f0f0f0' }}>
                      <td style={{ padding: '2px 4px' }}>{label}</td>
                      <td style={{ padding: '2px 4px', color: rating === 'Very High' ? '#c62828' : rating?.includes('High') ? '#e65100' : '#555' }}>{rating}</td>
                      <td style={{ padding: '2px 4px', textAlign: 'right' }}>{loss != null ? money(loss) : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Wetlands */}
      <div style={SECTION_HEADER}>Wetlands</div>
      {wetlands && wetlands.length > 0 ? (
        wetlands.map((w, i) => (
          <ExpandableField key={i} label={`Wetland ${i + 1}`} value={`${s(w.type)} — ${s(w.classificationCode)}`} detail={`Area: ${typeof w.wetlandArea === 'number' ? `${w.wetlandArea.toLocaleString()} sqm` : '—'}. Classification code: ${s(w.classificationCode)}.`} />
        ))
      ) : (
        <ExpandableField label="Wetlands" value="None recorded" detail="No wetlands found on or intersecting this parcel (from LightBox Wetlands API)." alwaysShow />
      )}
    </>
  );
}

function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function ExpandableField({ label, value, detail, highlight, multiline }: { label: string; value: string; detail: string; highlight?: boolean; multiline?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.35rem',
          padding: '0.2rem 0.3rem',
          margin: '-0.2rem -0.3rem',
          border: 'none',
          background: highlight ? 'rgba(255, 200, 200, 0.5)' : 'transparent',
          borderRadius: '3px',
          cursor: 'pointer',
          fontSize: '0.9rem',
          textAlign: 'left',
        }}
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span><strong>{label}:</strong> {multiline ? (expanded ? value : 'View list') : value}</span>
      </button>
      {expanded && (
        <div style={{ margin: '0.25rem 0 0 1.25rem', color: '#555', fontSize: '0.85rem', lineHeight: 1.4 }}>
          {multiline ? (
            <>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>{value}</pre>
              {detail && <p style={{ margin: '0.5rem 0 0 0' }}>{detail}</p>}
            </>
          ) : (
            <p style={{ margin: 0 }}>{detail}</p>
          )}
        </div>
      )}
    </div>
  );
}

const APN_DETAIL = "County assessor's ID for a parcel—used for taxation and assessment (ownership, value, lot size). Unique within a county; format varies by jurisdiction. Also called Parcel Number, Assessor Parcel ID, or PIN.";

const REGRID_STRUCTURES_SOURCE_DETAIL = `Regrid Matched Building Footprints are derived from aerial and satellite imagery. Each building includes:
• ed_source: Source of the footprint (e.g., "Aerial Imagery")
• ed_source_date: Imagery date (MM/DD/YYYY)
• ed_bldg_footprint_sqft: Footprint area in sqft

Buildings are matched to parcels via a join file (ll_uuid ↔ ed_bld_uuid). An optional "With Heights" product adds height, elevation, roof slope, and story estimates. Accuracy varies by imagery source and date—newer, higher-resolution imagery yields more precise footprints.`;

const LIGHTBOX_STRUCTURES_SOURCE_DETAIL = `LightBox National Structure database is part of the SmartFabric™ data product. Structure boundaries provide precise location awareness of the built world. Each structure includes:
• location.geometry: Footprint in WKT format
• physicalFeatures: height, groundElevation, footprintArea, numberOfStories
• Linkage to parcels, addresses, and assessments via LightBox ID

The dataset is a foundational layer for property intelligence. Structures are linked to parcels for geocoding and analysis.`;

function formatPermittedLandUses(raw: string | undefined): string {
  if (!raw || raw === '') return '—';
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (parsed == null || typeof parsed !== 'object') return raw;
    const lines: string[] = [];
    for (const [category, items] of Object.entries(parsed)) {
      const arr = Array.isArray(items)
        ? items.flatMap((x) => (Array.isArray(x) ? x : [x]))
        : [items];
      const list = arr.map((x) => (typeof x === 'string' ? x : String(x))).filter(Boolean).join(', ');
      if (list) lines.push(`${category}:\n  ${list}`);
    }
    return lines.length ? lines.join('\n\n') : raw;
  } catch {
    return raw;
  }
}

function formatPermittedFlags(raw: string | undefined): string {
  if (!raw || raw === '') return '—';
  const parts = raw.split(/[,\s]+/).map((s) => s.trim().replace(/_/g, ' ')).filter(Boolean);
  return parts.map((p) => `• ${p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()}`).join('\n');
}

function ZoningReviewSection({ zoning, compareWith }: { zoning: ZoningFields | null; compareWith?: ZoningFields | null }) {
  if (!zoning && !compareWith) return null;
  const z = zoning ?? {};
  const c = compareWith ?? {};
  const diff = (a: string | number | null | undefined, b: string | number | null | undefined) =>
    (a != null && a !== '' && a !== '—') || (b != null && b !== '' && b !== '—') ? String(a ?? '—') !== String(b ?? '—') : false;
  const diffNum = (a: number | null | undefined, b: number | null | undefined) =>
    (a != null || b != null) && a !== b;
  const rows: Array<{ label: string; value: string; detail: string; highlight: boolean; multiline?: boolean; alwaysShow?: boolean }> = [];
  const add = (label: string, val: string | number | null | undefined, detail: string, comp?: string | number | null | undefined, multiline?: boolean, alwaysShow?: boolean) => {
    const v = val != null && val !== '' ? String(val) : '—';
    rows.push({ label, value: v, detail, highlight: comp !== undefined ? diff(v, comp) : false, multiline, alwaysShow });
  };
  const addNum = (label: string, val: number | null | undefined, detail: string, comp?: number | null | undefined, alwaysShow?: boolean) => {
    const v = val != null ? String(val) : '—';
    rows.push({ label, value: v, detail, highlight: comp !== undefined ? diffNum(val ?? undefined, comp ?? undefined) : false, alwaysShow });
  };
  add('Jurisdiction', z.jurisdiction, 'Municipality or locality for zoning. Regrid: zoning.municipality_name; Lightbox: parcels[0].location.locality, regionCode.', c.jurisdiction);
  add('Zoning code', z.zoningCode, 'City/county zoning classification code.', c.zoningCode);
  add('Zoning description', z.zoningDescription, 'Human-readable zoning district name.', c.zoningDescription);
  add('Zoning type', z.zoningType, 'High-level type: Residential, Commercial, Industrial, Mixed, Planned, etc.', c.zoningType);
  add('Zoning subtype', z.zoningSubtype, 'Specific subtype within the zoning type.', c.zoningSubtype);
  const landUseDetail = 'The data indicates how the parcel is classified/used for assessment (what it is rather than what it\'s allowed to be) — land use not zoning.';
  add('Land use code', z.landUseCode ?? z.landUse, 'Assessment land use code. ' + landUseDetail, c.landUseCode ?? c.landUse);
  add('Land use description', z.landUseDescription ?? z.landUse, 'Assessment land use description. ' + landUseDetail, c.landUseDescription ?? c.landUse);
  add('Land use (normalized) code', z.landUseNormalizedCode, 'Normalized land use code. ' + landUseDetail, c.landUseNormalizedCode);
  add('Land use (normalized) description', z.landUseNormalizedDescription, 'Normalized land use description. ' + landUseDetail, c.landUseNormalizedDescription);
  add('Land use category', z.landUseCategoryDescription, 'Land use category (e.g. RESIDENTIAL). ' + landUseDetail, c.landUseCategoryDescription);
  // Setbacks, heights, FAR, coverage — fall back to description text when numeric is null
  const numOrDesc = (num: number | null | undefined, desc: string | undefined, suffix = '') => {
    if (num != null) return `${num}${suffix}`;
    if (desc) return desc;
    return null;
  };
  add('Front setback', numOrDesc(z.minFrontSetbackFt, z.minFrontSetbackDesc, ' ft'), 'Required distance from front lot line.', numOrDesc(c.minFrontSetbackFt, c.minFrontSetbackDesc, ' ft'));
  add('Side setback', numOrDesc(z.minSideSetbackFt, z.minSideSetbackDesc, ' ft'), 'Required distance from side lot line.', numOrDesc(c.minSideSetbackFt, c.minSideSetbackDesc, ' ft'));
  add('Rear setback', numOrDesc(z.minRearSetbackFt, z.minRearSetbackDesc, ' ft'), 'Required distance from rear lot line.', numOrDesc(c.minRearSetbackFt, c.minRearSetbackDesc, ' ft'));
  add('Max FAR', numOrDesc(z.maxFar, z.maxFarDesc), 'Maximum floor area ratio.', numOrDesc(c.maxFar, c.maxFarDesc), false, true);
  add('Max building height', numOrDesc(z.maxBuildingHeightFt, z.maxBuildingHeightDesc, ' ft'), 'Maximum building height allowed.', numOrDesc(c.maxBuildingHeightFt, c.maxBuildingHeightDesc, ' ft'));
  add('Max site coverage', numOrDesc(z.maxCoveragePct, z.maxCoverageDesc, '%'), 'Maximum percent of lot that can be covered by buildings.', numOrDesc(c.maxCoveragePct, c.maxCoverageDesc, '%'));
  add('Min lot area', numOrDesc(z.minLotAreaSqFt, z.minLotAreaDesc, ' sqft'), 'Minimum lot size.', numOrDesc(c.minLotAreaSqFt, c.minLotAreaDesc, ' sqft'));
  if (z.maxDensityDesc || z.maxDensityDuPerAcre != null) {
    add('Residential density', numOrDesc(z.maxDensityDuPerAcre, z.maxDensityDesc, ' du/acre'), 'Maximum dwelling units per acre.', numOrDesc(c.maxDensityDuPerAcre, c.maxDensityDesc, ' du/acre'));
  }
  addNum('Min open space (%)', z.minOpenSpacePct, 'Minimum percent of lot as open space.', c.minOpenSpacePct);
  addNum('Min landscaped space (%)', z.minLandscapedSpacePct, 'Minimum percent of lot as landscaped.', c.minLandscapedSpacePct);
  addNum('Max impervious coverage (%)', z.maxImperviousCoveragePct, 'Maximum percent covered by buildings and impervious surfaces.', c.maxImperviousCoveragePct);
  addNum('Min lot width (ft)', z.minLotWidthFt, 'Minimum lot width for subdivision.', c.minLotWidthFt);
  add('Zoning objective', z.zoningObjective, 'Textual description of zone character and objectives.', c.zoningObjective);
  const zoningLink = z.zoningCodeLink ?? c.zoningCodeLink;
  if (zoningLink) {
    rows.push({
      label: 'Zoning code link',
      value: 'View ordinance',
      detail: 'Link to full zoning ordinance.',
      highlight: diff(z.zoningCodeLink, c.zoningCodeLink),
    });
  }
  const permittedFormatted = formatPermittedLandUses(z.permittedLandUses);
  const permittedCompFormatted = formatPermittedLandUses(c.permittedLandUses);
  if (permittedFormatted !== '—' || permittedCompFormatted !== '—') {
    rows.push({
      label: 'Permitted land uses',
      value: permittedFormatted,
      detail: 'Permitted use classes and subclasses by category.',
      highlight: diff(z.permittedLandUses, c.permittedLandUses),
      multiline: true,
    });
  } else if (c.permittedLandUses) {
    rows.push({ label: 'Permitted land uses', value: '—', detail: 'Permitted use classes and subclasses by category.', highlight: true });
  }
  const asOfRightFormatted = formatPermittedFlags(z.permittedLandUsesAsOfRight);
  const asOfRightCompFormatted = formatPermittedFlags(c.permittedLandUsesAsOfRight);
  if (asOfRightFormatted !== '—' || asOfRightCompFormatted !== '—') {
    rows.push({
      label: 'Permitted uses (as of right)',
      value: asOfRightFormatted,
      detail: 'Uses permitted by right in this zoning district.',
      highlight: diff(z.permittedLandUsesAsOfRight, c.permittedLandUsesAsOfRight),
      multiline: true,
    });
  } else if (c.permittedLandUsesAsOfRight) {
    rows.push({ label: 'Permitted uses (as of right)', value: '—', detail: 'Uses permitted by right in this zoning district.', highlight: true });
  }
  const conditionalFormatted = formatPermittedFlags(z.permittedLandUsesConditional);
  const conditionalCompFormatted = formatPermittedFlags(c.permittedLandUsesConditional);
  if (conditionalFormatted !== '—' || conditionalCompFormatted !== '—') {
    rows.push({
      label: 'Permitted uses (conditional)',
      value: conditionalFormatted,
      detail: 'Uses permitted by conditional use permit in this zoning district.',
      highlight: diff(z.permittedLandUsesConditional, c.permittedLandUsesConditional),
      multiline: true,
    });
  } else if (c.permittedLandUsesConditional) {
    rows.push({ label: 'Permitted uses (conditional)', value: '—', detail: 'Uses permitted by conditional use permit in this zoning district.', highlight: true });
  }
  add('Zoning data date', z.zoningDataDate, 'Date zoning data was processed.', c.zoningDataDate);
  const hasAny = rows.some((r) => r.value !== '—');
  if (!hasAny) return null;
  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Zoning</div>
      <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>
        {rows.filter((r) => r.value !== '—' || r.highlight || r.alwaysShow).map((r) =>
          r.label === 'Zoning code link' ? (
            <div key={r.label} style={{ marginBottom: '0.5rem' }}>
              <a href={(z.zoningCodeLink ?? c.zoningCodeLink) ?? '#'} target="_blank" rel="noopener noreferrer" style={{ color: '#007bff', fontSize: '0.9rem' }}>View zoning ordinance →</a>
            </div>
          ) : (
            <ExpandableField key={r.label} label={r.label} value={r.value} detail={r.detail} highlight={r.highlight} multiline={r.multiline} />
          )
        )}
      </div>
    </div>
  );
}

function ExpandableStructuresSource({ label, value, detail, docUrl }: { label: string; value: string; detail: string; docUrl: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.35rem',
          padding: '0.2rem 0.3rem',
          margin: '-0.2rem -0.3rem',
          border: 'none',
          background: 'transparent',
          borderRadius: '3px',
          cursor: 'pointer',
          fontSize: '0.9rem',
          textAlign: 'left',
        }}
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span><strong>{label}:</strong> {value}</span>
      </button>
      {expanded && (
        <div style={{ margin: '0.25rem 0 0 1.25rem', color: '#555', fontSize: '0.85rem', lineHeight: 1.5 }}>
          <p style={{ margin: '0 0 0.5rem 0', whiteSpace: 'pre-line' }}>{detail}</p>
          <a href={docUrl} target="_blank" rel="noopener noreferrer" style={{ color: '#007bff', fontSize: '0.8rem' }}>View documentation →</a>
        </div>
      )}
    </div>
  );
}

function ReviewDataIdentifier({ apn, lotArea, fips, parcelId, fipsLabel = 'FIPS code', fipsDetail, parcelIdDetail, apnDetail = APN_DETAIL, lotAreaDetail, compareWith }: {
  apn?: string; lotArea?: string; fips?: string; parcelId?: string; fipsLabel?: string; fipsDetail: string; parcelIdDetail: string; apnDetail?: string; lotAreaDetail: string;
  compareWith?: { apn?: string; lotArea?: string; fips?: string; parcelId?: string };
}) {
  const apnDiff = compareWith && apn != null && apn !== '' && compareWith.apn != null && compareWith.apn !== '' && apn !== compareWith.apn;
  const lotAreaDiff = compareWith && lotArea != null && lotArea !== '' && compareWith.lotArea != null && compareWith.lotArea !== '' && lotArea !== compareWith.lotArea;
  const fipsDiff = compareWith && fips != null && fips !== '' && compareWith.fips != null && compareWith.fips !== '' && fips !== compareWith.fips;
  const parcelIdDiff = compareWith && parcelId != null && parcelId !== '' && compareWith.parcelId != null && compareWith.parcelId !== '' && parcelId !== compareWith.parcelId;
  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Parcel identifier</div>
      <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>
        {apn != null && apn !== '' && (
          <ExpandableField label="APN (Assessor's Parcel Number)" value={apn} detail={apnDetail} highlight={apnDiff} />
        )}
        {fips != null && fips !== '' && (
          <ExpandableField label={fipsLabel} value={fips} detail={fipsDetail} highlight={fipsDiff} />
        )}
        {parcelId != null && parcelId !== '' && (
          <ExpandableField label="Unique parcel ID" value={parcelId} detail={parcelIdDetail} highlight={parcelIdDiff} />
        )}
        {lotArea != null && lotArea !== '' && (
          <ExpandableField label="Lot area" value={lotArea} detail={lotAreaDetail} highlight={lotAreaDiff} />
        )}
      </div>
    </div>
  );
}

type ViewState = { longitude: number; latitude: number; zoom: number };

function MapPanel({ id, geoJson, buildingsGeoJson, transmissionLinesGeoJson, showTransmissionLines, fireSafetyGeoJson, viewState, onViewStateChange }: {
  id: string; geoJson?: GeoJsonFC | null; buildingsGeoJson?: GeoJsonFC | null; transmissionLinesGeoJson?: GeoJsonFC | null; showTransmissionLines?: boolean;
  fireSafetyGeoJson?: GeoJsonFC | null;
  viewState: ViewState; onViewStateChange: (vs: ViewState) => void;
}) {
  return (
    <div style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
      <Map
        id={id}
        mapLib={mapboxgl}
        mapboxAccessToken={MAPBOX_TOKEN}
        {...viewState}
        onMove={(evt) => onViewStateChange({ longitude: evt.viewState.longitude, latitude: evt.viewState.latitude, zoom: evt.viewState.zoom })}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/streets-v12"
      >
        {geoJson?.features?.length ? (
          <Source id="parcel-source" type="geojson" data={geoJson as GeoJSON.FeatureCollection} />
        ) : null}
        {geoJson?.features?.length ? (
          <Layer
            id="parcel-fill"
            type="fill"
            source="parcel-source"
            paint={{ 'fill-color': '#088', 'fill-opacity': 0.4 }}
          />
        ) : null}
        {geoJson?.features?.length ? (
          <Layer
            id="parcel-line"
            type="line"
            source="parcel-source"
            paint={{ 'line-color': '#088', 'line-width': 2 }}
          />
        ) : null}
        {buildingsGeoJson?.features?.length ? (
          <>
            <Source id="buildings-source" type="geojson" data={buildingsGeoJson as GeoJSON.FeatureCollection} />
            <Layer
              id="buildings-fill"
              type="fill"
              source="buildings-source"
              paint={{ 'fill-color': '#c44', 'fill-opacity': 0.5 }}
            />
            <Layer
              id="buildings-line"
              type="line"
              source="buildings-source"
              paint={{ 'line-color': '#c44', 'line-width': 1.5 }}
            />
            <Layer
              id="buildings-labels"
              type="symbol"
              source="buildings-source"
              minzoom={15.5}
              filter={['!=', ['get', 'mapLabel'], '']}
              layout={{
                'text-field': ['get', 'mapLabel'],
                'text-size': 11,
                'text-anchor': 'center',
                'text-allow-overlap': false,
              }}
              paint={{ 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1.5 }}
            />
          </>
        ) : null}
        {showTransmissionLines && transmissionLinesGeoJson?.features?.length ? (
          <>
            <Source id="transmission-source" type="geojson" data={transmissionLinesGeoJson as GeoJSON.FeatureCollection} />
            <Layer
              id="transmission-lines"
              type="line"
              source="transmission-source"
              paint={{ 'line-color': '#f90', 'line-width': 2.5 }}
            />
          </>
        ) : null}
        {fireSafetyGeoJson?.features?.length ? (
          <>
            <Source id="fire-safety-source" type="geojson" data={fireSafetyGeoJson as GeoJSON.FeatureCollection} />
            <Layer
              id="fire-safety-circles"
              type="circle"
              source="fire-safety-source"
              paint={{
                'circle-radius': 6,
                'circle-color': ['match', ['get', 'emergency'], 'fire_extinguisher', '#f57c00', '#d32f2f'],
                'circle-stroke-color': '#fff',
                'circle-stroke-width': 1.5,
                'circle-opacity': 0.9,
              }}
            />
            <Layer
              id="fire-safety-labels"
              type="symbol"
              source="fire-safety-source"
              minzoom={15}
              layout={{
                'text-field': ['match', ['get', 'emergency'], 'fire_extinguisher', 'EXT', 'FH'],
                'text-size': 9,
                'text-offset': [0, 1.5],
                'text-allow-overlap': false,
              }}
              paint={{ 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1 }}
            />
          </>
        ) : null}
      </Map>
    </div>
  );
}

function extractLightboxReviewFields(data: unknown, structuresData?: LightboxStructuresData): { apn?: string; lotArea?: string; fips?: string; parcelId?: string; totalFootprint?: number; maxHeight?: number; minGroundElev?: number; maxGroundElev?: number; slopePct?: number } | null {
  const parcels = data && typeof data === 'object' ? (data as { parcels?: Array<{
    fips?: string; id?: string; parcelApn?: string; assessment?: { apn?: string; lot?: { size?: number } };
    derived?: { calculatedLotArea?: number };
  }> }).parcels : undefined;
  const p = parcels?.[0];
  let out: { apn?: string; lotArea?: string; fips?: string; parcelId?: string; totalFootprint?: number; maxHeight?: number; minGroundElev?: number; maxGroundElev?: number; slopePct?: number } | null = null;
  if (p) {
    const apn = typeof p.parcelApn === 'string' ? p.parcelApn : (typeof p.assessment?.apn === 'string' ? p.assessment.apn : undefined);
    const lotSqm = typeof p.derived?.calculatedLotArea === 'number' ? p.derived.calculatedLotArea
      : (typeof p.assessment?.lot?.size === 'number' ? p.assessment.lot.size : undefined);
    const lotArea = lotSqm != null ? `${lotSqm.toLocaleString()} sqm` : undefined;
    out = { apn: apn ?? undefined, lotArea, fips: typeof p.fips === 'string' ? p.fips : undefined, parcelId: typeof p.id === 'string' ? p.id : undefined };
  }
  const structures = structuresData?.structures ?? [];
  if (structures.length) {
    let totalFootprint = 0;
    let maxHeight = -Infinity;
    let minElev = Infinity;
    let maxElev = -Infinity;
    for (const s of structures) {
      const pf = s?.physicalFeatures;
      totalFootprint += typeof pf?.area?.footprintArea === 'number' ? pf.area.footprintArea : 0;
      const h = typeof pf?.height?.max === 'number' ? pf.height.max : undefined;
      if (h != null && h > maxHeight) maxHeight = h;
      const emin = typeof pf?.groundElevation?.min === 'number' ? pf.groundElevation.min : undefined;
      if (emin != null && emin < minElev) minElev = emin;
      const emax = typeof pf?.groundElevation?.max === 'number' ? pf.groundElevation.max : undefined;
      if (emax != null && emax > maxElev) maxElev = emax;
    }
    out = out ?? {};
    out = { ...out, totalFootprint: totalFootprint || undefined, maxHeight: maxHeight === -Infinity ? undefined : maxHeight, minGroundElev: minElev === Infinity ? undefined : minElev, maxGroundElev: maxElev === -Infinity ? undefined : maxElev };
  }
  const elevDiff = out?.maxGroundElev != null && out?.minGroundElev != null ? out.maxGroundElev - out.minGroundElev : null;
  const p0 = parcels?.[0] as { location?: { geometry?: { wkt?: string } | string } } | undefined;
  const wkt = p0?.location?.geometry;
  const wktStr = typeof wkt === 'string' ? wkt : (wkt as { wkt?: string })?.wkt;
  const parsed = wktStr ? wktToGeoJson(wktStr) : null;
  const firstGeom = parsed?.features?.[0]?.geometry;
  const minRunFt = structures.reduce((max, s) => {
    const geom = s?.location?.geometry;
    const w = typeof geom === 'string' ? geom : (geom as { wkt?: string })?.wkt;
    if (!w) return max;
    const p = wktToGeoJson(w);
    const longest = p?.features?.[0]?.geometry ? longestEdgeFt(p.features[0].geometry) : null;
    return longest != null && longest > max ? longest : max;
  }, 0);
  const edgeFt = firstGeom ? shortestEdgeFtWithMin(firstGeom, minRunFt) : null;
  if (elevDiff != null && elevDiff > 0 && edgeFt != null && edgeFt > 0 && out) {
    out = { ...out, slopePct: (elevDiff / edgeFt) * 100 };
  }
  return out;
}

type LightboxStructuresData = { structures?: Array<{
  location?: { geometry?: { wkt?: string } | string };
  physicalFeatures?: { height?: { average?: number; max?: number; min?: number }; groundElevation?: { average?: number; max?: number; min?: number }; area?: { footprintArea?: number } };
}> } | null;

type ZoningFields = {
  jurisdiction?: string;
  zoningCode?: string;
  zoningDescription?: string;
  zoningType?: string;
  zoningSubtype?: string;
  minFrontSetbackFt?: number | null;
  minFrontSetbackDesc?: string;
  minRearSetbackFt?: number | null;
  minRearSetbackDesc?: string;
  minSideSetbackFt?: number | null;
  minSideSetbackDesc?: string;
  maxFar?: number | null;
  maxFarDesc?: string;
  maxBuildingHeightFt?: number | null;
  maxBuildingHeightDesc?: string;
  minOpenSpacePct?: number | null;
  minLandscapedSpacePct?: number | null;
  maxCoveragePct?: number | null;
  maxCoverageDesc?: string;
  maxImperviousCoveragePct?: number | null;
  maxDensityDuPerAcre?: number | null;
  maxDensityDesc?: string;
  minLotAreaSqFt?: number | null;
  minLotAreaDesc?: string;
  minLotWidthFt?: number | null;
  zoningObjective?: string;
  zoningCodeLink?: string;
  permittedLandUses?: string;
  permittedLandUsesAsOfRight?: string;
  permittedLandUsesConditional?: string;
  zoningDataDate?: string;
  landUse?: string;
  landUseCode?: string;
  landUseDescription?: string;
  landUseNormalizedCode?: string;
  landUseNormalizedDescription?: string;
  landUseCategoryDescription?: string;
};

type FederalDataFields = {
  // Opportunity Zone
  federalQualifiedOpportunityZone?: string;
  qualifiedOpportunityZoneTractNumber?: string;
  // FEMA
  femaFloodZone?: string;
  femaFloodZoneSubtype?: string;
  femaFloodZoneDataDate?: string;
  femaNriRiskRating?: string;
  femaSpecialFloodHazardArea?: boolean;
  femaIn100Year?: boolean;
  femaPanelId?: string;
  femaEffectiveDate?: string;
};

function extractRegridFederalData(data: RegridParcel | null): FederalDataFields | null {
  if (!data) return null;
  const d = data as Record<string, unknown>;
  const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const parcelCentroids = d.parcel_centroids as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const features = parcels?.features ?? parcelCentroids?.features ?? (d.features as Array<{ properties?: Record<string, unknown> }>);
  const parcel = d.parcel as { properties?: Record<string, unknown> } | undefined;
  const props = features?.[0]?.properties ?? parcel?.properties ?? (d.properties as Record<string, unknown>);
  if (!props) return null;
  const fields = (props.fields ?? props) as Record<string, unknown> | undefined;
  const qoz = typeof fields?.qoz === 'string' ? fields.qoz : undefined;
  const qozTract = typeof fields?.qoz_tract === 'string' ? fields.qoz_tract : undefined;
  const femaZone = typeof fields?.fema_flood_zone === 'string' ? fields.fema_flood_zone : undefined;
  const femaSubtype = typeof fields?.fema_flood_zone_subtype === 'string' ? fields.fema_flood_zone_subtype : undefined;
  const femaDate = typeof fields?.fema_flood_zone_data_date === 'string' ? fields.fema_flood_zone_data_date : undefined;
  const femaNri = typeof fields?.fema_nri_risk_rating === 'string' ? fields.fema_nri_risk_rating : undefined;
  const hasAny = qoz ?? qozTract ?? femaZone ?? femaSubtype ?? femaDate ?? femaNri;
  if (!hasAny) return null;
  return {
    federalQualifiedOpportunityZone: qoz,
    qualifiedOpportunityZoneTractNumber: qozTract,
    femaFloodZone: femaZone,
    femaFloodZoneSubtype: femaSubtype,
    femaFloodZoneDataDate: femaDate,
    femaNriRiskRating: femaNri,
  };
}

function extractLightboxFederalData(femaData: { nfhls?: Array<Record<string, unknown>> } | null): FederalDataFields | null {
  if (!femaData?.nfhls?.length) return null;
  const n = femaData.nfhls[0] as Record<string, unknown>;
  const zones = n.zones as { zone?: string; description?: string; subtype?: string } | undefined;
  const panel = n.panel as { firmId?: string; effectiveDate?: string; panelId?: string } | undefined;
  const zone = typeof zones?.zone === 'string' ? zones.zone : undefined;
  const subtype = typeof zones?.subtype === 'string' ? zones.subtype : undefined;
  const sfha = typeof n.sfha === 'boolean' ? n.sfha : undefined;
  const isIn100 = typeof n.isIn100Year === 'boolean' ? n.isIn100Year : undefined;
  const effectiveDate = typeof n.effectiveDate === 'string' ? n.effectiveDate : (typeof panel?.effectiveDate === 'string' ? panel.effectiveDate : undefined);
  const panelId = typeof panel?.panelId === 'string' ? panel.panelId : undefined;
  return {
    femaFloodZone: zone,
    femaFloodZoneSubtype: subtype,
    femaSpecialFloodHazardArea: sfha,
    femaIn100Year: isIn100,
    femaPanelId: panelId,
    femaEffectiveDate: effectiveDate,
  };
}

function FederalDataReviewSection({ federal, compareWith }: { federal: FederalDataFields | null; compareWith?: FederalDataFields | null }) {
  const f = federal ?? {};
  const c = compareWith ?? {};
  const diff = (a: string | number | boolean | null | undefined, b: string | number | boolean | null | undefined) =>
    (a != null && a !== '' && a !== '—') || (b != null && b !== '' && b !== '—') ? String(a ?? '—') !== String(b ?? '—') : false;
  const rows: Array<{ label: string; value: string; detail: string; highlight: boolean; alwaysShow?: boolean }> = [];
  const add = (label: string, val: string | number | boolean | null | undefined, detail: string, comp?: string | number | boolean | null | undefined, alwaysShow?: boolean) => {
    const v = val != null && val !== '' ? (typeof val === 'boolean' ? (val ? 'Yes' : 'No') : String(val)) : '—';
    rows.push({ label, value: v, detail, highlight: comp !== undefined ? diff(val, comp) : false, alwaysShow });
  };
  add('Federal Qualified Opportunity Zone', f.federalQualifiedOpportunityZone, 'Is this parcel in a US Federal Qualified Opportunity Zone (Yes/No).', c.federalQualifiedOpportunityZone, true);
  add('Qualified Opportunity Zone Tract Number', f.qualifiedOpportunityZoneTractNumber, 'Census tract number as defined when QOZs were designated (Dec 2018).', c.qualifiedOpportunityZoneTractNumber, true);
  add('FEMA Flood Zone', f.femaFloodZone, 'FEMA flood zone classification (e.g. X, AE, VE).', c.femaFloodZone, true);
  add('FEMA Flood Zone Subtype', f.femaFloodZoneSubtype, 'FEMA flood zone subtype or modifier.', c.femaFloodZoneSubtype, true);
  add('FEMA Flood Zone Data Date', f.femaFloodZoneDataDate ?? f.femaEffectiveDate, 'Effective date of FEMA flood zone data.', c.femaFloodZoneDataDate ?? c.femaEffectiveDate, true);
  add('FEMA NRI Risk Rating', f.femaNriRiskRating, 'FEMA National Risk Index rating (Very Low to Very High).', c.femaNriRiskRating, true);
  add('Special Flood Hazard Area', f.femaSpecialFloodHazardArea != null ? f.femaSpecialFloodHazardArea : undefined, 'Property in Special Flood Hazard Area (SFHA).', c.femaSpecialFloodHazardArea != null ? c.femaSpecialFloodHazardArea : undefined, true);
  add('In 100-Year Flood Zone', f.femaIn100Year != null ? f.femaIn100Year : undefined, 'Property in or out of 100-year flood zone.', c.femaIn100Year != null ? c.femaIn100Year : undefined, true);
  add('FEMA Panel ID', f.femaPanelId, 'FEMA FIRM panel identifier.', c.femaPanelId, true);
  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Federal Data</div>
      <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>
        {rows.filter((r) => r.value !== '—' || r.highlight || r.alwaysShow).map((r) => (
          <ExpandableField key={r.label} label={r.label} value={r.value} detail={r.detail} highlight={r.highlight} />
        ))}
      </div>
    </div>
  );
}

function extractRegridZoning(data: RegridParcel | null): ZoningFields | null {
  if (!data) return null;
  const d = data as Record<string, unknown>;
  const zoning = d.zoning as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const z0 = zoning?.features?.[0]?.properties as Record<string, unknown> | undefined;
  const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const p0 = parcels?.features?.[0]?.properties;
  const fields = (p0?.fields ?? p0) as Record<string, unknown> | undefined;
  const jurisdiction = typeof z0?.municipality_name === 'string' ? z0.municipality_name
    : (typeof fields?.city === 'string' ? fields.city : undefined)
    ?? (typeof fields?.county === 'string' ? fields.county : undefined);
  const zoningCode = typeof z0?.zoning === 'string' ? z0.zoning : (typeof fields?.zoning === 'string' ? fields.zoning : undefined);
  const zoningDescription = typeof z0?.zoning_description === 'string' ? z0.zoning_description : (typeof fields?.zoning_description === 'string' ? fields.zoning_description : undefined);
  const zoningType = typeof z0?.zoning_type === 'string' ? z0.zoning_type : (typeof fields?.zoning_type === 'string' ? fields.zoning_type : undefined);
  const zoningSubtype = typeof z0?.zoning_subtype === 'string' ? z0.zoning_subtype : (typeof fields?.zoning_subtype === 'string' ? fields.zoning_subtype : undefined);
  const num = (val: unknown): number | null => (typeof val === 'number' ? val : null);
  const sentinelOk = (v: number | null) => (v != null && v !== -9999 && v !== -5555 ? v : null);
  const landUse = typeof fields?.usedesc === 'string' ? fields.usedesc : (typeof fields?.usecode === 'string' ? fields.usecode : undefined);
  const landUseCode = typeof fields?.usecode === 'string' ? fields.usecode : undefined;
  const landUseDescription = typeof fields?.usedesc === 'string' ? fields.usedesc : undefined;
  return {
    jurisdiction,
    zoningCode,
    zoningDescription,
    zoningType,
    zoningSubtype,
    minFrontSetbackFt: sentinelOk(num(z0?.min_front_setback_ft ?? fields?.min_front_setback_ft)),
    minRearSetbackFt: sentinelOk(num(z0?.min_rear_setback_ft ?? fields?.min_rear_setback_ft)),
    minSideSetbackFt: sentinelOk(num(z0?.min_side_setback_ft ?? fields?.min_side_setback_ft)),
    maxFar: sentinelOk(num(z0?.max_far ?? fields?.max_far)),
    maxBuildingHeightFt: sentinelOk(num(z0?.max_building_height_ft ?? fields?.max_building_height_ft)),
    minOpenSpacePct: sentinelOk(num(z0?.min_open_space_pct ?? fields?.min_open_space_pct)),
    minLandscapedSpacePct: sentinelOk(num(z0?.min_landscaped_space_pct ?? fields?.min_landscaped_space_pct)),
    maxCoveragePct: sentinelOk(num(z0?.max_coverage_pct ?? fields?.max_coverage_pct)),
    maxImperviousCoveragePct: sentinelOk(num(z0?.max_impervious_coverage_pct ?? fields?.max_impervious_coverage_pct)),
    maxDensityDuPerAcre: sentinelOk(num(z0?.max_density_du_per_acre ?? fields?.max_density_du_per_acre)),
    minLotAreaSqFt: sentinelOk(num(z0?.min_lot_area_sq_ft ?? fields?.min_lot_area_sq_ft)),
    minLotWidthFt: sentinelOk(num(z0?.min_lot_width_ft ?? fields?.min_lot_width_ft)),
    zoningObjective: typeof z0?.zoning_objective === 'string' ? z0.zoning_objective : undefined,
    zoningCodeLink: typeof z0?.zoning_code_link === 'string' ? z0.zoning_code_link : (typeof fields?.zoning_code_link === 'string' ? fields.zoning_code_link : undefined),
    permittedLandUses: z0?.permitted_land_uses != null ? (typeof z0.permitted_land_uses === 'string' ? z0.permitted_land_uses : JSON.stringify(z0.permitted_land_uses)) : undefined,
    permittedLandUsesAsOfRight: typeof z0?.permitted_land_uses_as_of_right === 'string' ? z0.permitted_land_uses_as_of_right : undefined,
    permittedLandUsesConditional: typeof z0?.permitted_land_uses_conditional === 'string' ? z0.permitted_land_uses_conditional : undefined,
    zoningDataDate: typeof z0?.zoning_data_date === 'string' ? z0.zoning_data_date : undefined,
    landUse,
    landUseCode,
    landUseDescription,
  };
}

function extractLightboxZoning(data: unknown, zoningApiData?: { zonings?: Array<Record<string, unknown>> } | null): ZoningFields | null {
  if (!data || typeof data !== 'object') return null;
  const parcels = (data as { parcels?: Array<{ location?: { locality?: string; regionCode?: string }; county?: string; assessment?: { zoning?: unknown }; zoning?: { assessment?: string }; landUse?: { code?: string; description?: string; normalized?: { code?: string; description?: string; categoryDescription?: string } } }> }).parcels;
  const p0 = parcels?.[0];
  if (!p0) return null;
  const loc = p0.location;
  const parcelJurisdiction = typeof loc?.locality === 'string' ? loc.locality : undefined;
  const regionCode = typeof loc?.regionCode === 'string' ? loc.regionCode : undefined;
  const county = typeof p0.county === 'string' ? p0.county : undefined;
  const jurisdictionStr = [parcelJurisdiction, county, regionCode].filter(Boolean).join(', ') || undefined;

  // Land use from parcel response (always available)
  const lu = p0.landUse as { code?: string; description?: string; normalized?: { code?: string; description?: string; categoryDescription?: string } } | undefined;
  const landUseDesc = typeof lu?.description === 'string' ? lu.description : undefined;
  const landUseNorm = lu?.normalized;

  // Dedicated Zoning API data (rich fields)
  const zr = zoningApiData?.zonings?.[0] as Record<string, unknown> | undefined;
  if (zr) {
    const jur = zr.jurisdiction as { name?: string; type?: string } | undefined;
    const code = zr.code as { value?: string } | undefined;
    const district = zr.district as { value?: string; label?: string } | undefined;
    const desc = zr.description as { value?: string; label?: string } | undefined;
    const summary = zr.summary as { value?: string; label?: string } | undefined;
    const front = zr.frontSetback as { distance?: number; description?: string } | undefined;
    const side = zr.sideSetback as { distance?: number; description?: string } | undefined;
    const rear = zr.rearSetback as { distance?: number; description?: string } | undefined;
    const far = zr.densityFloorArea as { value?: string; description?: string } | undefined;
    const height = zr.maximumBuildingHeight as { height?: number; maxStories?: string; description?: string } | undefined;
    const coverage = zr.maximumSiteCoverage as { percent?: number; description?: string } | undefined;
    const lotArea = zr.minimumLotArea as { perUnit?: number; perLot?: number; description?: string } | undefined;
    const meta = zr.$metadata as { ordinanceUrl?: string; vintage?: { ordinance?: string; zoning?: string } } | undefined;
    const farVal = far?.value != null && far.value !== '' ? parseFloat(String(far.value)) : null;
    return {
      jurisdiction: typeof jur?.name === 'string' ? `${jur.name}${jur.type ? ` (${jur.type})` : ''}` : jurisdictionStr,
      zoningCode: typeof code?.value === 'string' ? code.value : undefined,
      zoningDescription: typeof desc?.value === 'string' ? desc.value : (typeof district?.value === 'string' ? district.value : undefined),
      zoningType: typeof zr.category === 'string' ? zr.category : (typeof zr.type === 'string' ? String(zr.type) : undefined),
      zoningSubtype: typeof zr.subcategory === 'string' ? zr.subcategory : undefined,
      minFrontSetbackFt: typeof front?.distance === 'number' ? front.distance : null,
      minFrontSetbackDesc: typeof front?.description === 'string' ? front.description : undefined,
      minRearSetbackFt: typeof rear?.distance === 'number' ? rear.distance : null,
      minRearSetbackDesc: typeof rear?.description === 'string' ? rear.description : undefined,
      minSideSetbackFt: typeof side?.distance === 'number' ? side.distance : null,
      minSideSetbackDesc: typeof side?.description === 'string' ? side.description : undefined,
      maxFar: farVal != null && !isNaN(farVal) ? farVal : null,
      maxFarDesc: typeof far?.description === 'string' ? far.description : undefined,
      maxBuildingHeightFt: typeof height?.height === 'number' ? height.height : null,
      maxBuildingHeightDesc: typeof height?.description === 'string' ? height.description : undefined,
      minOpenSpacePct: null,
      minLandscapedSpacePct: null,
      maxCoveragePct: typeof coverage?.percent === 'number' ? coverage.percent * 100 : null,
      maxCoverageDesc: typeof coverage?.description === 'string' ? coverage.description : undefined,
      maxImperviousCoveragePct: null,
      maxDensityDuPerAcre: null,
      maxDensityDesc: typeof far?.description === 'string' && far.description.toLowerCase().includes('density') ? far.description : undefined,
      minLotAreaSqFt: typeof lotArea?.perLot === 'number' ? lotArea.perLot : null,
      minLotAreaDesc: typeof lotArea?.description === 'string' ? lotArea.description : undefined,
      minLotWidthFt: null,
      zoningObjective: typeof summary?.value === 'string' ? summary.value : undefined,
      zoningCodeLink: typeof meta?.ordinanceUrl === 'string' ? meta.ordinanceUrl : undefined,
      permittedLandUses: typeof zr.permittedUse === 'string' ? zr.permittedUse : undefined,
      permittedLandUsesAsOfRight: undefined,
      permittedLandUsesConditional: undefined,
      zoningDataDate: typeof meta?.vintage?.zoning === 'string' ? meta.vintage.zoning : (typeof meta?.vintage?.ordinance === 'string' ? meta.vintage.ordinance : undefined),
      landUse: landUseDesc ?? (landUseNorm ? [landUseNorm.description, landUseNorm.categoryDescription].filter(Boolean).join(' — ') || undefined : undefined),
      landUseCode: typeof lu?.code === 'string' ? lu.code : undefined,
      landUseDescription: landUseDesc,
      landUseNormalizedCode: typeof landUseNorm?.code === 'string' ? landUseNorm.code : undefined,
      landUseNormalizedDescription: typeof landUseNorm?.description === 'string' ? landUseNorm.description : undefined,
      landUseCategoryDescription: typeof landUseNorm?.categoryDescription === 'string' ? landUseNorm.categoryDescription : undefined,
    };
  }

  // Fallback: parcel-embedded zoning fields
  const parcelZoning = p0.zoning as { assessment?: string } | undefined;
  const assessment = p0.assessment as { zoning?: { zoning?: string; zoningDescription?: string; assessment?: string } } | undefined;
  const z = assessment?.zoning;
  const zoningCode = typeof parcelZoning?.assessment === 'string' ? parcelZoning.assessment
    : (typeof z?.assessment === 'string' ? z.assessment : undefined)
    ?? (typeof z?.zoning === 'string' ? z.zoning : undefined);
  const zoningDescription = typeof z?.zoningDescription === 'string' ? z.zoningDescription : undefined;
  return {
    jurisdiction: jurisdictionStr ?? regionCode,
    zoningCode,
    zoningDescription,
    zoningType: undefined,
    zoningSubtype: undefined,
    minFrontSetbackFt: null,
    minRearSetbackFt: null,
    minSideSetbackFt: null,
    maxFar: null,
    maxBuildingHeightFt: null,
    minOpenSpacePct: null,
    minLandscapedSpacePct: null,
    maxCoveragePct: null,
    maxImperviousCoveragePct: null,
    maxDensityDuPerAcre: null,
    minLotAreaSqFt: null,
    minLotWidthFt: null,
    zoningObjective: undefined,
    zoningCodeLink: undefined,
    permittedLandUses: undefined,
    permittedLandUsesAsOfRight: undefined,
    permittedLandUsesConditional: undefined,
    zoningDataDate: undefined,
    landUse: landUseDesc ?? (landUseNorm ? [landUseNorm.description, landUseNorm.categoryDescription].filter(Boolean).join(' — ') || undefined : undefined),
    landUseCode: typeof lu?.code === 'string' ? lu.code : undefined,
    landUseDescription: landUseDesc,
    landUseNormalizedCode: typeof landUseNorm?.code === 'string' ? landUseNorm.code : undefined,
    landUseNormalizedDescription: typeof landUseNorm?.description === 'string' ? landUseNorm.description : undefined,
    landUseCategoryDescription: typeof landUseNorm?.categoryDescription === 'string' ? landUseNorm.categoryDescription : undefined,
  };
}

function findElevInObj(obj: unknown, path: string): { highest?: number; lowest?: number; path: string } | null {
  if (obj == null || typeof obj !== 'object') return null;
  const o = obj as Record<string, unknown>;
  const h = typeof o.highest_parcel_elevation === 'number' ? o.highest_parcel_elevation : undefined;
  const l = typeof o.lowest_parcel_elevation === 'number' ? o.lowest_parcel_elevation : undefined;
  if (h != null || l != null) return { highest: h, lowest: l, path };
  return null;
}
function extractRegridReviewFields(data: RegridParcel | null): { apn?: string; lotArea?: string; fips?: string; parcelId?: string; totalFootprint?: number; maxHeight?: number; minGroundElev?: number; maxGroundElev?: number; slopePct?: number; transmissionLineDistanceM?: number } | null {
  if (!data) return null;
  const d = data as Record<string, unknown>;
  // #region agent log
  (() => {
    const found: Array<{ path: string; highest?: number; lowest?: number }> = [];
    const check = (o: unknown, p: string) => { const r = findElevInObj(o, p); if (r) found.push({ path: r.path, highest: r.highest, lowest: r.lowest }); };
    const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const f0 = parcels?.features?.[0];
    check(f0?.properties, 'parcels.features[0].properties');
    check((f0?.properties as Record<string, unknown>)?.fields, 'parcels.features[0].properties.fields');
    const parcel = d.parcel as { properties?: Record<string, unknown> } | undefined;
    check(parcel?.properties, 'parcel.properties');
    check((parcel?.properties as Record<string, unknown>)?.fields, 'parcel.properties.fields');
    check(d.properties, 'data.properties');
    check((d.properties as Record<string, unknown>)?.fields, 'data.properties.fields');
    fetch('http://127.0.0.1:7243/ingest/4a8aba0b-6ab5-4d83-94b8-8f39b144cc00',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'App.tsx:extractRegridScan',message:'Scan for elevation',data:{found},timestamp:Date.now(),hypothesisId:'E2'})}).catch(()=>{});
  })();
  // #endregion
  const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const parcelCentroids = d.parcel_centroids as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
  const features = parcels?.features ?? parcelCentroids?.features ?? (d.features as Array<{ properties?: Record<string, unknown> }>);
  const parcel = d.parcel as { properties?: Record<string, unknown> } | undefined;
  const props = features?.[0]?.properties ?? parcel?.properties ?? (d.properties as Record<string, unknown>);
  if (!props) return null;
  const fields = props.fields as Record<string, unknown> | undefined;
  // #region agent log
  fetch('http://127.0.0.1:7243/ingest/4a8aba0b-6ab5-4d83-94b8-8f39b144cc00',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'App.tsx:extractRegridReviewFields',message:'Regrid parcel elevation lookup',data:{propsKeys:props?Object.keys(props):[],fieldsKeys:fields?Object.keys(fields):[],highestInProps:props?.highest_parcel_elevation,lowestInProps:props?.lowest_parcel_elevation,highestInFields:fields?.highest_parcel_elevation,lowestInFields:fields?.lowest_parcel_elevation,topLevelKeys:d?Object.keys(d):[]},timestamp:Date.now(),hypothesisId:'E1'})}).catch(()=>{});
  // #endregion
  const apn = (typeof fields?.parcelnumb === 'string' ? fields.parcelnumb : undefined)
    ?? (typeof fields?.parcelnumb_no_formatting === 'string' ? fields.parcelnumb_no_formatting : undefined)
    ?? (typeof props.parcelnumb === 'string' ? props.parcelnumb : undefined);
  const llGissqft = typeof fields?.ll_gissqft === 'number' ? fields.ll_gissqft : undefined;
  const llGisacre = typeof fields?.ll_gisacre === 'number' ? fields.ll_gisacre : undefined;
  const lotArea = llGissqft != null ? `${llGissqft.toLocaleString()} sqft`
    : llGisacre != null ? `${llGisacre.toLocaleString()} acres` : undefined;
  const geoid = (typeof props.geoid === 'string' ? props.geoid : undefined)
    ?? (typeof fields?.geoid === 'string' ? fields.geoid : undefined)
    ?? (typeof props.fips === 'string' ? props.fips : undefined);
  const llUuid = typeof props.ll_uuid === 'string' ? props.ll_uuid : undefined;
  const transmissionLineDistanceM = typeof fields?.transmission_line_distance === 'number' ? fields.transmission_line_distance : undefined;
  let out: { apn?: string; lotArea?: string; fips?: string; parcelId?: string; totalFootprint?: number; maxHeight?: number; minGroundElev?: number; maxGroundElev?: number; slopePct?: number; transmissionLineDistanceM?: number } = { apn: apn ?? undefined, lotArea, fips: geoid, parcelId: llUuid, transmissionLineDistanceM };
  const highestParcel = typeof props?.highest_parcel_elevation === 'number' ? props.highest_parcel_elevation : (typeof fields?.highest_parcel_elevation === 'number' ? fields.highest_parcel_elevation : undefined);
  const lowestParcel = typeof props?.lowest_parcel_elevation === 'number' ? props.lowest_parcel_elevation : (typeof fields?.lowest_parcel_elevation === 'number' ? fields.lowest_parcel_elevation : undefined);
  const buildings = (d.buildings as { features?: Array<{ geometry?: unknown; properties?: Record<string, unknown> }> })?.features ?? [];
  const firstParcelGeom = (features?.[0] as { geometry?: unknown })?.geometry ?? (parcel as { geometry?: unknown })?.geometry ?? (d.geometry as unknown);
  const minRunFt = buildings.reduce((max, b) => {
    const geom = b?.geometry;
    const longest = geom ? longestEdgeFt(geom) : null;
    return longest != null && longest > max ? longest : max;
  }, 0);
  if (highestParcel != null || lowestParcel != null) {
    out = { ...out, minGroundElev: lowestParcel ?? out.minGroundElev, maxGroundElev: highestParcel ?? out.maxGroundElev };
  }
  if (buildings.length) {
    let totalFootprint = 0;
    let maxHeight = -Infinity;
    let minLag = Infinity;
    let maxHag = -Infinity;
    for (const b of buildings) {
      const p = b?.properties ?? {};
      const fields = p.fields as Record<string, unknown> | undefined;
      totalFootprint += typeof p?.ed_bldg_footprint_sqft === 'number' ? p.ed_bldg_footprint_sqft : 0;
      const h = typeof p?.ed_max_height === 'number' ? p.ed_max_height : (typeof p?.ed_mean_height === 'number' ? p.ed_mean_height : undefined);
      if (h != null && h > maxHeight) maxHeight = h;
      const lag = typeof p?.ed_lag === 'number' ? p.ed_lag : (typeof fields?.ed_lag === 'number' ? fields.ed_lag : undefined);
      if (lag != null && lag < minLag) minLag = lag;
      const hag = typeof p?.ed_hag === 'number' ? p.ed_hag : (typeof fields?.ed_hag === 'number' ? fields.ed_hag : undefined);
      if (hag != null && hag > maxHag) maxHag = hag;
    }
    let minGE = minLag === Infinity ? lowestParcel : minLag;
    let maxGE = maxHag === -Infinity ? highestParcel : maxHag;
    if (minGE == null && maxGE == null) {
      for (const b of buildings) {
        const p = b?.properties ?? {};
        const m = typeof p?.ed_mean_elevation === 'number' ? p.ed_mean_elevation : (typeof (p.fields as Record<string, unknown>)?.ed_mean_elevation === 'number' ? (p.fields as Record<string, unknown>).ed_mean_elevation : undefined);
        if (m != null) { minGE = m; maxGE = m; break; }
      }
    }
    out = { ...out, totalFootprint: totalFootprint || undefined, maxHeight: maxHeight === -Infinity ? undefined : maxHeight, minGroundElev: minGE, maxGroundElev: maxGE };
  }
  const elevDiff = out.maxGroundElev != null && out.minGroundElev != null ? out.maxGroundElev - out.minGroundElev : null;
  const edgeFt = firstParcelGeom ? shortestEdgeFtWithMin(firstParcelGeom, minRunFt) : null;
  if (elevDiff != null && elevDiff > 0 && edgeFt != null && edgeFt > 0) {
    out = { ...out, slopePct: (elevDiff / edgeFt) * 100 };
  }
  return out;
}

function RegridPanel({ data, setData, lightboxData, lightboxStructuresData, lightboxFemaData, lightboxZoningData, viewState, setViewState, transmissionLinesGeoJson, showTransmissionLines, fireSafetyGeoJson }: {
  data: RegridParcel | null; setData: (d: RegridParcel | null) => void; lightboxData: unknown;
  lightboxStructuresData: LightboxStructuresData;
  lightboxFemaData: { nfhls?: Array<Record<string, unknown>> } | null;
  lightboxZoningData: { zonings?: Array<Record<string, unknown>> } | null;
  viewState: ViewState; setViewState: (vs: ViewState | ((prev: ViewState) => ViewState)) => void;
  transmissionLinesGeoJson: GeoJsonFC | null; showTransmissionLines: boolean;
  fireSafetyGeoJson: (GeoJsonFC & { nearestDistanceM?: number | null }) | null;
}) {
  const [address, setAddress] = useState('');
  const [suggestions, setSuggestions] = useState<RegridSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState<RegridSuggestion | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const [autocompleteError, setAutocompleteError] = useState<string | null>(null);
  const [dataTab, setDataTab] = useState<'raw' | 'review'>('raw');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const mapCenter = useMemo((): [number, number] | null => {
    if (!selectedSuggestion) return null;
    return selectedSuggestion.geometry.coordinates;
  }, [selectedSuggestion]);

  useEffect(() => {
    if (mapCenter) setViewState((s) => ({ ...s, longitude: mapCenter[0], latitude: mapCenter[1] }));
  }, [mapCenter, setViewState]);

  const geoJson = useMemo((): GeoJsonFC | null => {
    if (!data) return null;
    const d = data as Record<string, unknown>;
    let features = (d.parcels as { features?: unknown[] })?.features
      ?? (d.parcel_centroids as { features?: unknown[] })?.features
      ?? (d.features as unknown[]);
    if (!features?.length && d.geometry) {
      features = [{ geometry: d.geometry, properties: d.properties ?? {} }];
    }
    if (!features?.length) return null;
    const fc = (features as Array<{ geometry?: unknown; properties?: unknown }>)
      .map((f) => f?.geometry ? { type: 'Feature' as const, geometry: f.geometry, properties: (f.properties ?? {}) as Record<string, unknown> } : null)
      .filter((x): x is NonNullable<typeof x> => x != null);
    return fc.length ? { type: 'FeatureCollection', features: fc } : null;
  }, [data]);

  const regridBuildingsGeoJson = useMemo((): GeoJsonFC | null => {
    if (!data) return null;
    const buildings = (data as { buildings?: { features?: Array<{ geometry?: unknown; properties?: Record<string, unknown> }> } }).buildings;
    const features = buildings?.features ?? [];
    if (!features?.length) return null;
    const fc = (features as Array<{ geometry?: unknown; properties?: Record<string, unknown> }>)
      .map((f) => {
        if (!f?.geometry) return null;
        const props = f.properties ?? {};
        const sqft = typeof props.ed_bldg_footprint_sqft === 'number' ? props.ed_bldg_footprint_sqft : undefined;
        const h = typeof props.ed_max_height === 'number' ? props.ed_max_height : (typeof props.ed_mean_height === 'number' ? props.ed_mean_height : undefined);
        const areaLabel = sqft != null ? `${Math.round(sqft)} sqft` : '';
        const heightLabel = h != null ? `h=${Math.round(h)} ft` : '';
        const mapLabel = [heightLabel, areaLabel].filter(Boolean).join('\n') || '';
        return {
          type: 'Feature' as const,
          geometry: f.geometry,
          properties: { ...props, areaLabel, heightLabel, mapLabel } as Record<string, unknown>,
        };
      })
      .filter((x): x is NonNullable<typeof x> => x != null);
    return fc.length ? { type: 'FeatureCollection', features: fc } : null;
  }, [data]);

  const regridStructuresSource = useMemo(() => {
    const buildings = (data as { buildings?: { features?: Array<{ properties?: Record<string, unknown> }> } })?.buildings;
    const first = buildings?.features?.[0]?.properties;
    const edSource = typeof first?.ed_source === 'string' ? first.ed_source : undefined;
    return edSource ?? 'Matched Building Footprints';
  }, [data]);

  const regridBuildingAttrs = useMemo(() => {
    if (!data) return null;
    const d = data as Record<string, unknown>;
    const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const parcelCentroids = d.parcel_centroids as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const features = parcels?.features ?? parcelCentroids?.features ?? (d.features as Array<{ properties?: Record<string, unknown> }>);
    const parcel = d.parcel as { properties?: Record<string, unknown> } | undefined;
    const parcelProps = features?.[0]?.properties ?? parcel?.properties ?? (d.properties as Record<string, unknown>);
    const parcelFields = parcelProps?.fields as Record<string, unknown> | undefined;
    const highestParcel = typeof parcelProps?.highest_parcel_elevation === 'number' ? parcelProps.highest_parcel_elevation
      : (typeof parcelFields?.highest_parcel_elevation === 'number' ? parcelFields.highest_parcel_elevation : undefined);
    const lowestParcel = typeof parcelProps?.lowest_parcel_elevation === 'number' ? parcelProps.lowest_parcel_elevation
      : (typeof parcelFields?.lowest_parcel_elevation === 'number' ? parcelFields.lowest_parcel_elevation : undefined);
    const buildings = d.buildings as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const bldgs = buildings?.features ?? [];
    if (!bldgs.length && highestParcel == null && lowestParcel == null) return null;
    let totalFootprint = 0;
    let maxH = -Infinity;
    let minLag = Infinity;
    let maxHag = -Infinity;
    for (const b of bldgs) {
      const p = b?.properties ?? {};
      const fields = p.fields as Record<string, unknown> | undefined;
      const sqft = typeof p?.ed_bldg_footprint_sqft === 'number' ? p.ed_bldg_footprint_sqft : 0;
      totalFootprint += sqft;
      const h = typeof p?.ed_max_height === 'number' ? p.ed_max_height : (typeof p?.ed_mean_height === 'number' ? p.ed_mean_height : undefined);
      if (h != null && h > maxH) maxH = h;
      const lag = typeof p?.ed_lag === 'number' ? p.ed_lag : (typeof fields?.ed_lag === 'number' ? fields.ed_lag : undefined);
      if (lag != null && lag < minLag) minLag = lag;
      const hag = typeof p?.ed_hag === 'number' ? p.ed_hag : (typeof fields?.ed_hag === 'number' ? fields.ed_hag : undefined);
      if (hag != null && hag > maxHag) maxHag = hag;
    }
    let minGroundElev = minLag === Infinity ? lowestParcel : minLag;
    let maxGroundElev = maxHag === -Infinity ? highestParcel : maxHag;
    if (minGroundElev == null && lowestParcel != null) minGroundElev = lowestParcel;
    if (maxGroundElev == null && highestParcel != null) maxGroundElev = highestParcel;
    if (minGroundElev == null && maxGroundElev == null && bldgs.length) {
      const meanElev = (() => { for (const b of bldgs) { const p = b?.properties ?? {}; const m = typeof p?.ed_mean_elevation === 'number' ? p.ed_mean_elevation : (typeof (p.fields as Record<string, unknown>)?.ed_mean_elevation === 'number' ? (p.fields as Record<string, unknown>).ed_mean_elevation : undefined); if (m != null) return m; } return undefined; })();
      if (meanElev != null) { minGroundElev = meanElev; maxGroundElev = meanElev; }
    }
    const maxHeight = maxH === -Infinity ? undefined : maxH;
    if (maxHeight == null && minGroundElev == null && maxGroundElev == null && totalFootprint === 0) return null;
    return { maxHeight, minGroundElev, maxGroundElev, totalFootprint, buildingCount: bldgs.length };
  }, [data]);

  const regridSlope = useMemo(() => {
    const attrs = regridBuildingAttrs;
    const elevDiff = attrs?.maxGroundElev != null && attrs?.minGroundElev != null ? attrs.maxGroundElev - attrs.minGroundElev : null;
    const parcelGeom = geoJson?.features?.[0]?.geometry;
    // Min run: exclude parcel edges smaller than the largest edge of the largest building
    const minRunFt = regridBuildingsGeoJson?.features?.reduce((max, f) => {
      const longest = f?.geometry ? longestEdgeFt(f.geometry) : null;
      return longest != null && longest > max ? longest : max;
    }, 0) ?? 0;
    const edgeFt = parcelGeom ? shortestEdgeFtWithMin(parcelGeom, minRunFt) : null;
    if (elevDiff != null && elevDiff > 0 && edgeFt != null && edgeFt > 0) {
      const slope = elevDiff / edgeFt;
      return { slope, slopePct: slope * 100, elevDiff, edgeFt };
    }
    return null;
  }, [regridBuildingAttrs, geoJson, regridBuildingsGeoJson]);

  const regridReviewFields = useMemo(() => {
    if (!data) return null;
    const d = data as Record<string, unknown>;
    const parcels = d.parcels as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const parcelCentroids = d.parcel_centroids as { features?: Array<{ properties?: Record<string, unknown> }> } | undefined;
    const features = parcels?.features ?? parcelCentroids?.features ?? (d.features as Array<{ properties?: Record<string, unknown> }>);
    const parcel = d.parcel as { properties?: Record<string, unknown> } | undefined;
    const props = features?.[0]?.properties ?? parcel?.properties ?? (d.properties as Record<string, unknown>);
    if (!props) return null;
    const fields = props.fields as Record<string, unknown> | undefined;
    const apn = (typeof fields?.parcelnumb === 'string' ? fields.parcelnumb : undefined)
      ?? (typeof fields?.parcelnumb_no_formatting === 'string' ? fields.parcelnumb_no_formatting : undefined)
      ?? (typeof props.parcelnumb === 'string' ? props.parcelnumb : undefined);
    const llGissqft = typeof fields?.ll_gissqft === 'number' ? fields.ll_gissqft : undefined;
    const llGisacre = typeof fields?.ll_gisacre === 'number' ? fields.ll_gisacre : undefined;
    const lotArea = llGissqft != null ? `${llGissqft.toLocaleString()} sqft`
      : llGisacre != null ? `${llGisacre.toLocaleString()} acres` : undefined;
    const geoid = (typeof props.geoid === 'string' ? props.geoid : undefined)
      ?? (typeof fields?.geoid === 'string' ? fields.geoid : undefined)
      ?? (typeof props.fips === 'string' ? props.fips : undefined);
    const llUuid = typeof props.ll_uuid === 'string' ? props.ll_uuid : undefined;
    return { apn: apn ?? undefined, lotArea, fips: geoid, parcelId: llUuid };
  }, [data]);

  useEffect(() => {
    if (!selectedSuggestion) return;
    if (address.trim() === selectedSuggestion.properties.address) return;
    setSelectedSuggestion(null);
  }, [address, selectedSuggestion]);

  useEffect(() => {
    if (!address.trim()) {
      setSuggestions([]);
      setAutocompleteError(null);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setAutocompleteError(null);
      try {
        const r = await fetch(`/api/regrid/parcels/typeahead?query=${encodeURIComponent(address.trim())}`);
        const resData = await r.json();
        if (!r.ok) {
          const msg = r.status === 401
            ? 'Regrid token rejected (401). Verify REGRID_TOKEN at regrid.com.'
            : (resData?.message || resData?.error || `Request failed (${r.status})`);
          setAutocompleteError(msg);
          setSuggestions([]);
          return;
        }
        if (resData?.status === 'error' || resData?.message) {
          const msg = resData?.message === 'Access denied'
            ? 'Regrid token rejected (401). Verify REGRID_TOKEN at regrid.com.'
            : (resData.message || 'Regrid API error');
          setAutocompleteError(msg);
          setSuggestions([]);
          return;
        }
        const features = resData?.parcel_centroids?.features ?? [];
        setSuggestions(features);
        setShowDropdown(true);
      } catch {
        setAutocompleteError('Cannot reach Regrid backend. Is it running on port 3001?');
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [address]);

  const onSelect = (s: RegridSuggestion) => {
    setAddress(s.properties.address);
    setSelectedSuggestion(s);
    setSuggestions([]);
    setShowDropdown(false);
  };

  const onLoad = async () => {
    if (!selectedSuggestion) return;
    const { ll_uuid } = selectedSuggestion.properties;
    const [lon, lat] = selectedSuggestion.geometry.coordinates;

    setData(null);
    setDataError(null);
    setDataLoading(true);

    try {
      let res = await fetch(`/api/regrid/parcel/${ll_uuid}`);
      if (!res.ok && res.status === 404) {
        res = await fetch(`/api/regrid/parcels/point?lat=${lat}&lon=${lon}`);
      }
      if (res.ok) {
        const d = await res.json();
        setData(d);
      } else {
        const errBody = await res.json().catch(() => ({}));
        setDataError(`Regrid: ${res.status} ${errBody?.message || ''}`.trim());
      }
    } catch (err) {
      setDataError(String(err));
    } finally {
      setDataLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
      <div style={{ position: 'sticky', top: 0, zIndex: 10, padding: '0.75rem 1rem', background: '#fafafa', borderBottom: '1px solid #eee' }}>
        <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem' }}>Regrid</h2>
        <div style={{ position: 'relative', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
            <input
              type="text"
              placeholder="Type address (Regrid autocomplete)..."
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              style={{ width: '100%', padding: '0.5rem 1rem', border: '1px solid #ccc', borderRadius: '4px' }}
            />
            {loading && !selectedSuggestion && (
              <span style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', fontSize: '0.8rem', color: '#666' }}>...</span>
            )}
            {showDropdown && suggestions.length > 0 && (
              <div
                ref={dropdownRef}
                style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '2px',
                  background: 'white', border: '1px solid #ccc', borderRadius: '4px',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)', maxHeight: '200px', overflowY: 'auto', zIndex: 100,
                }}
              >
                {suggestions.map((s, i) => (
                  <button
                    key={s.properties.ll_uuid ?? `r-${i}`}
                    type="button"
                    onClick={() => onSelect(s)}
                    onMouseDown={(e) => e.preventDefault()}
                    style={{ display: 'block', width: '100%', padding: '0.6rem 1rem', textAlign: 'left', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.9rem' }}
                  >
                    <strong>{s.properties.address}</strong>
                    {s.properties.context && <><br /><span style={{ color: '#666', fontSize: '0.8rem' }}>{s.properties.context}</span></>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onLoad}
            disabled={!selectedSuggestion || dataLoading}
            style={{
              padding: '0.5rem 1rem', background: selectedSuggestion && !dataLoading ? '#007bff' : '#ccc',
              color: 'white', border: 'none', borderRadius: '4px', cursor: selectedSuggestion && !dataLoading ? 'pointer' : 'not-allowed', fontSize: '0.9rem',
            }}
          >
            {dataLoading ? 'Loading…' : 'Load'}
          </button>
        </div>
        {autocompleteError && <div style={{ marginTop: '4px', fontSize: '0.8rem', color: '#856404' }}>{autocompleteError}</div>}
        {dataError && <div style={{ marginTop: '4px', fontSize: '0.8rem', color: '#721c24' }}>{dataError}</div>}
      </div>
      <Split direction="vertical" sizes={[50, 50]} minSize={120} style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }} className="split-vertical">
        <div style={{ position: 'relative', minHeight: 200, flex: 1, background: '#e8e8e8' }}>
          <MapPanel id="regrid-map" geoJson={geoJson} buildingsGeoJson={regridBuildingsGeoJson} transmissionLinesGeoJson={transmissionLinesGeoJson} showTransmissionLines={showTransmissionLines} fireSafetyGeoJson={fireSafetyGeoJson} viewState={viewState} onViewStateChange={setViewState} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 120, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #ddd', background: '#eee', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => setDataTab('raw')}
              style={{
                padding: '0.5rem 1rem', fontSize: '0.85rem', border: 'none', background: dataTab === 'raw' ? '#fafafa' : 'transparent',
                cursor: 'pointer', borderBottom: dataTab === 'raw' ? '2px solid #007bff' : '2px solid transparent',
              }}
            >
              Raw
            </button>
            <button
              type="button"
              onClick={() => setDataTab('review')}
              style={{
                padding: '0.5rem 1rem', fontSize: '0.85rem', border: 'none', background: dataTab === 'review' ? '#fafafa' : 'transparent',
                cursor: 'pointer', borderBottom: dataTab === 'review' ? '2px solid #007bff' : '2px solid transparent',
              }}
            >
              Review Data
            </button>
            <button
              type="button"
              onClick={() => data && downloadJson(data, 'regrid-raw.json')}
              disabled={!data}
              style={{
                marginLeft: 'auto',
                marginRight: '0.5rem',
                padding: '0.35rem 0.75rem',
                fontSize: '0.8rem',
                border: '1px solid #ccc',
                borderRadius: '4px',
                background: data ? '#fff' : '#eee',
                cursor: data ? 'pointer' : 'not-allowed',
                color: data ? '#333' : '#999',
              }}
            >
              Download
            </button>
          </div>
          <div style={{ padding: '1rem', overflow: 'auto', background: '#fafafa', flex: 1 }}>
            {dataLoading ? <p>Loading parcel data…</p> : data ? (
              dataTab === 'raw' ? (
                <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>{JSON.stringify(data, null, 2)}</pre>
              ) : (
                <div>
                  {regridReviewFields ? (
                    <>
                      <ReviewDataIdentifier
                        apn={regridReviewFields.apn}
                        lotArea={regridReviewFields.lotArea}
                        fips={regridReviewFields.fips}
                        parcelId={regridReviewFields.parcelId}
                        fipsLabel="FIPS code (geoid)"
                        fipsDetail="Federal standard (geoid in Regrid) used by the US Census Bureau; shared across federal and local government databases to identify the county."
                        parcelIdDetail="Regrid LL-UUID is an internal identifier assigned by Regrid to track parcels across county data refreshes."
                        lotAreaDetail="Geometry-derived from parcel boundary. Regrid provides ll_gissqft (sqft) and ll_gisacre (acres) in properties.fields."
                        compareWith={extractLightboxReviewFields(lightboxData, lightboxStructuresData) ?? undefined}
                      />
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Infrastructure</div>
                      <ExpandableField
                        label="Distance to transmission line"
                        value={regridReviewFields.transmissionLineDistanceM != null ? `${regridReviewFields.transmissionLineDistanceM.toLocaleString()} m (${(regridReviewFields.transmissionLineDistanceM * 3.28084).toLocaleString()} ft)` : '—'}
                        detail="Distance from parcel to nearest electric power transmission line (HIFLD). Regrid provides transmission_line_distance in meters."
                        alwaysShow
                      />
                      <ExpandableField
                        label="Nearest fire hydrant / extinguisher"
                        value={fireSafetyGeoJson?.nearestDistanceM != null ? `${fireSafetyGeoJson.nearestDistanceM.toLocaleString()} m (${Math.round(fireSafetyGeoJson.nearestDistanceM * 3.28084).toLocaleString()} ft)` : '—'}
                        detail={`Distance to nearest fire hydrant or extinguisher from OpenStreetMap (500m search radius). ${fireSafetyGeoJson?.features?.length ?? 0} found nearby.`}
                        alwaysShow
                      />
                      <FederalDataReviewSection federal={extractRegridFederalData(data)} compareWith={extractLightboxFederalData(lightboxFemaData)} />
                      <ZoningReviewSection zoning={extractRegridZoning(data)} compareWith={extractLightboxZoning(lightboxData, lightboxZoningData)} />
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Existing structures</div>
                      <ExpandableStructuresSource
                        label="Source"
                        value={regridStructuresSource}
                        detail={REGRID_STRUCTURES_SOURCE_DETAIL}
                        docUrl="https://support.regrid.com/parcel-data/buildings-schema"
                      />
                      {regridBuildingAttrs && (() => {
                        const lb = extractLightboxReviewFields(lightboxData, lightboxStructuresData);
                        const diff = (a: number | undefined, b: number | undefined) => (a != null || b != null) && a !== b;
                        return (
                          <div style={{ marginTop: '0.5rem' }}>
                            {regridBuildingAttrs.maxHeight != null && (
                              <ExpandableField label="Max height" value={`${regridBuildingAttrs.maxHeight} ft`} detail="Height of the tallest structure on the parcel. Max of ed_max_height across all buildings (fallback to ed_mean_height)." highlight={diff(regridBuildingAttrs.maxHeight, lb?.maxHeight)} />
                            )}
                            <ExpandableField label="Max ground elevation" value={regridBuildingAttrs.maxGroundElev != null ? `${regridBuildingAttrs.maxGroundElev} ft` : '—'} detail="Highest observed ground elevation (ed_hag) across all buildings, in feet above sea level. Fallback: ed_mean_elevation when ed_hag missing." highlight={regridBuildingAttrs.maxGroundElev != null && lb?.maxGroundElev != null && Math.abs(regridBuildingAttrs.maxGroundElev - lb.maxGroundElev) > 1} />
                            <ExpandableField label="Min ground elevation" value={regridBuildingAttrs.minGroundElev != null ? `${regridBuildingAttrs.minGroundElev} ft` : '—'} detail="Lowest observed ground elevation (ed_lag) across all buildings, in feet above sea level. Fallback: ed_mean_elevation when ed_lag missing." highlight={regridBuildingAttrs.minGroundElev != null && lb?.minGroundElev != null && Math.abs(regridBuildingAttrs.minGroundElev - lb.minGroundElev) > 1} />
                            {(regridSlope || (regridBuildingAttrs.minGroundElev != null && regridBuildingAttrs.maxGroundElev != null)) && (
                              <ExpandableField label="Slope (worst case)" value={regridSlope ? `${regridSlope.slopePct.toFixed(2)}%` : '—'} detail={regridSlope ? `Rise/run using shortest parcel edge ≥ largest building edge (${regridSlope.edgeFt.toFixed(0)} ft) as run. Elevation diff: ${regridSlope.elevDiff.toFixed(1)} ft. Excludes parcel edges smaller than largest structure.` : 'Requires parcel polygon geometry and min/max ground elevation.'} highlight={regridSlope ? (() => { const lb = extractLightboxReviewFields(lightboxData, lightboxStructuresData); return lb?.slopePct != null && Math.abs(regridSlope.slopePct - lb.slopePct) > 0.01; })() : false} />
                            )}
                            {regridBuildingAttrs.totalFootprint != null && regridBuildingAttrs.totalFootprint > 0 && (
                              <ExpandableField
                                label="Total footprint"
                                value={regridBuildingAttrs.buildingCount > 1 ? `${regridBuildingAttrs.totalFootprint.toLocaleString()} sqft (${regridBuildingAttrs.buildingCount} buildings)` : `${regridBuildingAttrs.totalFootprint.toLocaleString()} sqft`}
                                detail="Sum of all building footprint areas on the parcel. Each building has ed_bldg_footprint_sqft. Individual areas appear on the map when zoomed in."
                                highlight={diff(regridBuildingAttrs.totalFootprint, lb?.totalFootprint)}
                              />
                            )}
                          </div>
                        );
                      })()}
                    </>
                  ) : (
                    <p style={{ margin: 0, color: '#666' }}>No parcel identifier data available.</p>
                  )}
                </div>
              )
            ) : (
              <p style={{ margin: 0 }}>Type an address, select from Regrid autocomplete, then click Load.</p>
            )}
          </div>
        </div>
      </Split>
    </div>
  );
}

function LightboxPanel({ data, setData, regridData, structuresData, setStructuresData, femaData, setFemaData, zoningData, setZoningData, riskIndexData, setRiskIndexData, wetlandsData, setWetlandsData, viewState, setViewState, transmissionLinesGeoJson, showTransmissionLines, fireSafetyGeoJson }: {
  data: unknown; setData: (d: unknown) => void; regridData: RegridParcel | null;
  structuresData: LightboxStructuresData; setStructuresData: (d: LightboxStructuresData) => void;
  femaData: { nfhls?: Array<Record<string, unknown>> } | null; setFemaData: (d: { nfhls?: Array<Record<string, unknown>> } | null) => void;
  zoningData: { zonings?: Array<Record<string, unknown>> } | null; setZoningData: (d: { zonings?: Array<Record<string, unknown>> } | null) => void;
  riskIndexData: Record<string, unknown> | null; setRiskIndexData: (d: Record<string, unknown> | null) => void;
  wetlandsData: Record<string, unknown> | null; setWetlandsData: (d: Record<string, unknown> | null) => void;
  viewState: ViewState; setViewState: (vs: ViewState | ((prev: ViewState) => ViewState)) => void;
  transmissionLinesGeoJson: GeoJsonFC | null; showTransmissionLines: boolean;
  fireSafetyGeoJson: (GeoJsonFC & { nearestDistanceM?: number | null }) | null;
}) {
  const [address, setAddress] = useState('');
  const [suggestions, setSuggestions] = useState<LightboxSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState<LightboxSuggestion | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const [autocompleteError, setAutocompleteError] = useState<string | null>(null);
  const [dataTab, setDataTab] = useState<'raw' | 'review'>('raw');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const parcelId = useMemo((): string | null => {
    if (!data || typeof data !== 'object') return null;
    const parcels = (data as { parcels?: Array<{ id?: string }> }).parcels;
    const id = parcels?.[0]?.id;
    return typeof id === 'string' ? id : null;
  }, [data]);

  useEffect(() => {
    if (!parcelId) {
      setStructuresData(null);
      setFemaData(null);
      setZoningData(null);
      setRiskIndexData(null);
      setWetlandsData(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`/api/lightbox/structures/_on/parcel/us/${encodeURIComponent(parcelId)}`);
        if (cancelled) return;
        if (!r.ok) {
          setStructuresData(null);
          return;
        }
        const d = await r.json();
        if (cancelled) return;
        setStructuresData(d);
      } catch {
        if (!cancelled) setStructuresData(null);
      }
    })();
    return () => { cancelled = true; };
  }, [parcelId]);

  useEffect(() => {
    if (!parcelId) return;
    let cancelled = false;
    fetch(`/api/lightbox/nfhls/_on/parcel/us/${encodeURIComponent(parcelId)}`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setFemaData(d);
      })
      .catch(() => { if (!cancelled) setFemaData(null); });
    return () => { cancelled = true; };
  }, [parcelId, setFemaData]);

  useEffect(() => {
    if (!parcelId) { setZoningData(null); return; }
    let cancelled = false;
    fetch(`/api/lightbox/zoning/_on/parcel/us/${encodeURIComponent(parcelId)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled) setZoningData(d); })
      .catch(() => { if (!cancelled) setZoningData(null); });
    return () => { cancelled = true; };
  }, [parcelId, setZoningData]);

  useEffect(() => {
    if (!parcelId) { setRiskIndexData(null); return; }
    let cancelled = false;
    fetch(`/api/lightbox/riskindexes/_on/parcel/us/${encodeURIComponent(parcelId)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled) setRiskIndexData(d); })
      .catch(() => { if (!cancelled) setRiskIndexData(null); });
    return () => { cancelled = true; };
  }, [parcelId, setRiskIndexData]);

  useEffect(() => {
    if (!parcelId) { setWetlandsData(null); return; }
    let cancelled = false;
    fetch(`/api/lightbox/wetlands/_on/parcel/us/${encodeURIComponent(parcelId)}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled) setWetlandsData(d); })
      .catch(() => { if (!cancelled) setWetlandsData(null); });
    return () => { cancelled = true; };
  }, [parcelId, setWetlandsData]);

  const lightboxStructureAttrs = useMemo(() => {
    const structures = structuresData?.structures ?? [];
    if (!structures.length) return null;
    let totalFootprint = 0;
    let heightMax = -Infinity;
    let minElev = Infinity;
    let maxElev = -Infinity;
    for (const s of structures) {
      const pf = s?.physicalFeatures;
      const fp = typeof pf?.area?.footprintArea === 'number' ? pf.area.footprintArea : 0;
      totalFootprint += fp;
      const h = typeof pf?.height?.max === 'number' ? pf.height.max : undefined;
      if (h != null && h > heightMax) heightMax = h;
      const emin = typeof pf?.groundElevation?.min === 'number' ? pf.groundElevation.min : undefined;
      if (emin != null && emin < minElev) minElev = emin;
      const emax = typeof pf?.groundElevation?.max === 'number' ? pf.groundElevation.max : undefined;
      if (emax != null && emax > maxElev) maxElev = emax;
    }
    if (heightMax === -Infinity && minElev === Infinity && maxElev === -Infinity && totalFootprint === 0) return null;
    return { heightMax: heightMax === -Infinity ? undefined : heightMax, minGroundElev: minElev === Infinity ? undefined : minElev, maxGroundElev: maxElev === -Infinity ? undefined : maxElev, totalFootprint, structureCount: structures.length };
  }, [structuresData]);

  const lightboxRawData = useMemo(() => {
    const base = data && typeof data === 'object' ? { ...(data as object) } : {};
    return {
      ...base,
      structures: structuresData ?? { structures: [] },
      ...(femaData ? { nfhls: femaData } : {}),
      ...(zoningData ? { zoning: zoningData } : {}),
      ...(riskIndexData ? { riskindexes: riskIndexData } : {}),
      ...(wetlandsData ? { wetlands: wetlandsData } : {}),
    };
  }, [data, structuresData, femaData, zoningData, riskIndexData, wetlandsData]);

  const lightboxBuildingsGeoJson = useMemo((): GeoJsonFC | null => {
    const structures = structuresData?.structures ?? [];
    if (!structures.length) return null;
    const features: GeoJsonFC['features'] = [];
    for (const s of structures) {
      const geom = s?.location?.geometry;
      const wkt = typeof geom === 'string' ? geom : geom?.wkt;
      const footprint = typeof s?.physicalFeatures?.area?.footprintArea === 'number' ? s.physicalFeatures.area.footprintArea : undefined;
      const h = typeof s?.physicalFeatures?.height?.max === 'number' ? s.physicalFeatures.height.max : undefined;
      const areaLabel = footprint != null ? `${Math.round(footprint)} sqft` : '';
      const heightLabel = h != null ? `h=${Math.round(h)} ft` : '';
      const mapLabel = [heightLabel, areaLabel].filter(Boolean).join('\n') || '';
      if (wkt) {
        const parsed = wktToGeoJson(wkt);
        if (parsed?.features?.length) {
          for (const fe of parsed.features) {
            features.push({
              ...fe,
              properties: { ...(fe.properties ?? {}), areaLabel, heightLabel, mapLabel } as Record<string, unknown>,
            });
          }
        }
      }
    }
    return features.length ? { type: 'FeatureCollection', features } : null;
  }, [structuresData]);

  const mapCenter = useMemo((): [number, number] | null => {
    if (!selectedSuggestion?.location?.representativePoint) return null;
    const pt = selectedSuggestion.location.representativePoint;
    return [pt.longitude, pt.latitude];
  }, [selectedSuggestion]);

  useEffect(() => {
    if (mapCenter) setViewState((s) => ({ ...s, longitude: mapCenter[0], latitude: mapCenter[1] }));
  }, [mapCenter, setViewState]);

  const geoJson = useMemo((): GeoJsonFC | null => {
    if (!data || typeof data !== 'object') return null;
    const parcels = (data as { parcels?: Array<{ location?: { geometry?: { wkt?: string } | string } }> }).parcels;
    if (!parcels?.length) return null;
    const features: GeoJsonFC['features'] = [];
    for (const p of parcels) {
      const geom = p?.location?.geometry;
      const wkt = typeof geom === 'string' ? geom : geom?.wkt;
      if (wkt) {
        const parsed = wktToGeoJson(wkt);
        if (parsed?.features?.length) features.push(...parsed.features);
      }
    }
    return features.length ? { type: 'FeatureCollection', features } : null;
  }, [data]);

  const lightboxSlope = useMemo(() => {
    const attrs = lightboxStructureAttrs;
    const elevDiff = attrs?.maxGroundElev != null && attrs?.minGroundElev != null ? attrs.maxGroundElev - attrs.minGroundElev : null;
    const parcelGeom = geoJson?.features?.[0]?.geometry;
    const minRunFt = lightboxBuildingsGeoJson?.features?.reduce((max, f) => {
      const longest = f?.geometry ? longestEdgeFt(f.geometry) : null;
      return longest != null && longest > max ? longest : max;
    }, 0) ?? 0;
    const edgeFt = parcelGeom ? shortestEdgeFtWithMin(parcelGeom, minRunFt) : null;
    if (elevDiff != null && elevDiff > 0 && edgeFt != null && edgeFt > 0) {
      const slope = elevDiff / edgeFt;
      return { slope, slopePct: slope * 100, elevDiff, edgeFt };
    }
    return null;
  }, [lightboxStructureAttrs, geoJson, lightboxBuildingsGeoJson]);

  const lightboxReviewFields = useMemo(() => {
    if (!data || typeof data !== 'object') return null;
    const parcels = (data as { parcels?: Array<{
      fips?: string; id?: string; parcelApn?: string; assessment?: { apn?: string; lot?: { size?: number } };
      derived?: { calculatedLotArea?: number };
    }> }).parcels;
    const p = parcels?.[0];
    if (!p) return null;
    const apn = typeof p.parcelApn === 'string' ? p.parcelApn : (typeof p.assessment?.apn === 'string' ? p.assessment.apn : undefined);
    const lotSqm = typeof p.derived?.calculatedLotArea === 'number' ? p.derived.calculatedLotArea
      : (typeof p.assessment?.lot?.size === 'number' ? p.assessment.lot.size : undefined);
    const lotArea = lotSqm != null ? `${lotSqm.toLocaleString()} sqm` : undefined;
    const fips = typeof p.fips === 'string' ? p.fips : undefined;
    const id = typeof p.id === 'string' ? p.id : undefined;
    return { apn: apn ?? undefined, lotArea, fips, parcelId: id };
  }, [data]);

  useEffect(() => {
    if (!selectedSuggestion) return;
    if (address.trim() === selectedSuggestion.label) return;
    setSelectedSuggestion(null);
  }, [address, selectedSuggestion]);

  useEffect(() => {
    if (!address.trim()) {
      setSuggestions([]);
      setAutocompleteError(null);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setAutocompleteError(null);
      try {
        const r = await fetch(`/api/lightbox/addresses/_autocomplete?text=${encodeURIComponent(address.trim())}&countryCode=US`);
        const resData = await r.json();
        if (!r.ok) {
          const msg = r.status === 401
            ? 'Lightbox API key rejected. Verify LIGHTBOX_API_KEY.'
            : (resData?.error?.message || resData?.message || `Request failed (${r.status})`);
          setAutocompleteError(msg);
          setSuggestions([]);
          return;
        }
        const addrs = (resData?.addresses ?? []).filter(
          (a: unknown) => a != null && (typeof (a as { id?: string }).id === 'string' || typeof (a as { label?: string }).label === 'string')
        );
        setSuggestions(addrs);
        setShowDropdown(true);
      } catch {
        setAutocompleteError('Cannot reach Lightbox backend. Is it running on port 3002?');
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [address]);

  const onSelect = (s: LightboxSuggestion) => {
    setAddress(s.label);
    setSelectedSuggestion(s);
    setSuggestions([]);
    setShowDropdown(false);
  };

  const onLoad = async () => {
    if (!selectedSuggestion) return;

    setData(null);
    setStructuresData(null);
    setDataError(null);
    setDataLoading(true);

    try {
      let res = await fetch(`/api/lightbox/parcels/address?text=${encodeURIComponent(selectedSuggestion.label)}`);
      if (!res.ok && res.status === 404) {
        const pt = selectedSuggestion.location?.representativePoint;
        if (pt) {
          res = await fetch(`/api/lightbox/parcels/us/geometry?wkt=POINT(${pt.longitude}%20${pt.latitude})&bufferDistance=50&bufferUnit=m`);
        }
      }
      if (res.ok) {
        const d = await res.json();
        setData(d);
      } else {
        const errBody = await res.json().catch(() => ({}));
        setDataError(`Lightbox: ${res.status} ${errBody?.error?.message || errBody?.message || ''}`.trim());
      }
    } catch (err) {
      setDataError(String(err));
    } finally {
      setDataLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
      <div style={{ position: 'sticky', top: 0, zIndex: 10, padding: '0.75rem 1rem', background: '#f5f5f5', borderBottom: '1px solid #eee' }}>
        <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem' }}>Lightbox</h2>
        <div style={{ position: 'relative', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
            <input
              type="text"
              placeholder="Type address (Lightbox autocomplete)..."
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              style={{ width: '100%', padding: '0.5rem 1rem', border: '1px solid #ccc', borderRadius: '4px' }}
            />
            {loading && !selectedSuggestion && (
              <span style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', fontSize: '0.8rem', color: '#666' }}>...</span>
            )}
            {showDropdown && suggestions.length > 0 && (
              <div
                ref={dropdownRef}
                style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '2px',
                  background: 'white', border: '1px solid #ccc', borderRadius: '4px',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)', maxHeight: '200px', overflowY: 'auto', zIndex: 100,
                }}
              >
                {suggestions.map((s, i) => (
                  <button
                    key={s.id ?? `lb-${i}`}
                    type="button"
                    onClick={() => onSelect(s)}
                    onMouseDown={(e) => e.preventDefault()}
                    style={{ display: 'block', width: '100%', padding: '0.6rem 1rem', textAlign: 'left', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.9rem' }}
                  >
                    <strong>{s.label}</strong>
                    {s.location?.locality && <><br /><span style={{ color: '#666', fontSize: '0.8rem' }}>{s.location.locality}</span></>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onLoad}
            disabled={!selectedSuggestion || dataLoading}
            style={{
              padding: '0.5rem 1rem', background: selectedSuggestion && !dataLoading ? '#007bff' : '#ccc',
              color: 'white', border: 'none', borderRadius: '4px', cursor: selectedSuggestion && !dataLoading ? 'pointer' : 'not-allowed', fontSize: '0.9rem',
            }}
          >
            {dataLoading ? 'Loading…' : 'Load'}
          </button>
        </div>
        {autocompleteError && <div style={{ marginTop: '4px', fontSize: '0.8rem', color: '#856404' }}>{autocompleteError}</div>}
        {dataError && <div style={{ marginTop: '4px', fontSize: '0.8rem', color: '#721c24' }}>{dataError}</div>}
      </div>
      <Split direction="vertical" sizes={[50, 50]} minSize={120} style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }} className="split-vertical">
        <div style={{ position: 'relative', minHeight: 200, flex: 1, background: '#e0e0e0' }}>
          <MapPanel id="lightbox-map" geoJson={geoJson} buildingsGeoJson={lightboxBuildingsGeoJson} transmissionLinesGeoJson={transmissionLinesGeoJson} showTransmissionLines={showTransmissionLines} fireSafetyGeoJson={fireSafetyGeoJson} viewState={viewState} onViewStateChange={setViewState} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 120, overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #ddd', background: '#eee', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => setDataTab('raw')}
              style={{
                padding: '0.5rem 1rem', fontSize: '0.85rem', border: 'none', background: dataTab === 'raw' ? '#f5f5f5' : 'transparent',
                cursor: 'pointer', borderBottom: dataTab === 'raw' ? '2px solid #007bff' : '2px solid transparent',
              }}
            >
              Raw
            </button>
            <button
              type="button"
              onClick={() => setDataTab('review')}
              style={{
                padding: '0.5rem 1rem', fontSize: '0.85rem', border: 'none', background: dataTab === 'review' ? '#f5f5f5' : 'transparent',
                cursor: 'pointer', borderBottom: dataTab === 'review' ? '2px solid #007bff' : '2px solid transparent',
              }}
            >
              Review Data
            </button>
            <button
              type="button"
              onClick={() => lightboxRawData && downloadJson(lightboxRawData, 'lightbox-raw.json')}
              disabled={!data && !structuresData}
              style={{
                marginLeft: 'auto',
                marginRight: '0.5rem',
                padding: '0.35rem 0.75rem',
                fontSize: '0.8rem',
                border: '1px solid #ccc',
                borderRadius: '4px',
                background: (data || structuresData) ? '#fff' : '#eee',
                cursor: (data || structuresData) ? 'pointer' : 'not-allowed',
                color: (data || structuresData) ? '#333' : '#999',
              }}
            >
              Download
            </button>
          </div>
          <div style={{ padding: '1rem', overflow: 'auto', background: '#f5f5f5', flex: 1 }}>
            {dataLoading ? <p>Loading parcel data…</p> : data ? (
              dataTab === 'raw' ? (
                <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>{JSON.stringify(lightboxRawData, null, 2)}</pre>
              ) : (
                <div>
                  {lightboxReviewFields ? (
                    <>
                      <ReviewDataIdentifier
                        apn={lightboxReviewFields.apn}
                        lotArea={lightboxReviewFields.lotArea}
                        fips={lightboxReviewFields.fips}
                        parcelId={lightboxReviewFields.parcelId}
                        fipsDetail="Federal standard (fips in Lightbox) used by the US Census Bureau; shared across federal and local government databases to identify the county."
                        parcelIdDetail="LightBox Parcel ID is an internal identifier assigned by Lightbox."
                        lotAreaDetail="From derived.calculatedLotArea or assessment.lot.size, in square meters."
                        compareWith={extractRegridReviewFields(regridData) ?? undefined}
                      />
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Infrastructure</div>
                      <ExpandableField
                        label="Nearest fire hydrant / extinguisher"
                        value={fireSafetyGeoJson?.nearestDistanceM != null ? `${fireSafetyGeoJson.nearestDistanceM.toLocaleString()} m (${Math.round(fireSafetyGeoJson.nearestDistanceM * 3.28084).toLocaleString()} ft)` : '—'}
                        detail={`Distance to nearest fire hydrant or extinguisher from OpenStreetMap (500m search radius). ${fireSafetyGeoJson?.features?.length ?? 0} found nearby.`}
                        alwaysShow
                      />
                      <FederalDataReviewSection federal={extractLightboxFederalData(femaData)} compareWith={extractRegridFederalData(regridData)} />
                      <ZoningReviewSection zoning={extractLightboxZoning(data, zoningData)} compareWith={extractRegridZoning(regridData)} />
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#333', marginBottom: '0.35rem' }}>Existing structures</div>
                      <ExpandableStructuresSource
                        label="Source"
                        value="LightBox National Structure DB"
                        detail={LIGHTBOX_STRUCTURES_SOURCE_DETAIL}
                        docUrl="https://lightbox.document360.io/docs/structures-documentation"
                      />
                      {lightboxStructureAttrs && (() => {
                        const rg = extractRegridReviewFields(regridData);
                        const diff = (a: number | undefined, b: number | undefined) => (a != null || b != null) && a !== b;
                        return (
                          <div style={{ marginTop: '0.5rem' }}>
                            {lightboxStructureAttrs.heightMax != null && (
                              <ExpandableField label="Max height" value={`${lightboxStructureAttrs.heightMax} ft`} detail="Height of the tallest structure. Max of physicalFeatures.height.max across all structures." highlight={diff(lightboxStructureAttrs.heightMax, rg?.maxHeight)} />
                            )}
                            <ExpandableField label="Max ground elevation" value={lightboxStructureAttrs.maxGroundElev != null ? `${lightboxStructureAttrs.maxGroundElev} ft` : '—'} detail="Highest ground elevation across all structures. From physicalFeatures.groundElevation.max." highlight={lightboxStructureAttrs.maxGroundElev != null && rg?.maxGroundElev != null && Math.abs(lightboxStructureAttrs.maxGroundElev - rg.maxGroundElev) > 1} />
                            <ExpandableField label="Min ground elevation" value={lightboxStructureAttrs.minGroundElev != null ? `${lightboxStructureAttrs.minGroundElev} ft` : '—'} detail="Lowest ground elevation across all structures. From physicalFeatures.groundElevation.min." highlight={lightboxStructureAttrs.minGroundElev != null && rg?.minGroundElev != null && Math.abs(lightboxStructureAttrs.minGroundElev - rg.minGroundElev) > 1} />
                            {(lightboxSlope || (lightboxStructureAttrs.minGroundElev != null && lightboxStructureAttrs.maxGroundElev != null)) && (
                              <ExpandableField label="Slope (worst case)" value={lightboxSlope ? `${lightboxSlope.slopePct.toFixed(2)}%` : '—'} detail={lightboxSlope ? `Rise/run using shortest parcel edge ≥ largest structure edge (${lightboxSlope.edgeFt.toFixed(0)} ft) as run. Elevation diff: ${lightboxSlope.elevDiff.toFixed(1)} ft. Excludes parcel edges smaller than largest structure.` : 'Requires parcel polygon geometry and min/max ground elevation.'} highlight={lightboxSlope ? (() => { const rg = extractRegridReviewFields(regridData); return rg?.slopePct != null && Math.abs(lightboxSlope.slopePct - rg.slopePct) > 0.01; })() : false} />
                            )}
                            {lightboxStructureAttrs.totalFootprint != null && lightboxStructureAttrs.totalFootprint > 0 && (
                              <ExpandableField
                                label="Total footprint"
                                value={lightboxStructureAttrs.structureCount > 1 ? `${lightboxStructureAttrs.totalFootprint.toLocaleString()} sqft (${lightboxStructureAttrs.structureCount} structures)` : `${lightboxStructureAttrs.totalFootprint.toLocaleString()} sqft`}
                                detail="Sum of all structure footprint areas on the parcel. Each structure has physicalFeatures.area.footprintArea. Individual areas appear on the map when zoomed in."
                                highlight={diff(lightboxStructureAttrs.totalFootprint, rg?.totalFootprint)}
                              />
                            )}
                          </div>
                        );
                      })()}
                      <LightboxDetailedReview data={data} femaData={femaData} riskIndexData={riskIndexData} wetlandsData={wetlandsData} />
                    </>
                  ) : (
                    <p style={{ margin: 0, color: '#666' }}>No parcel identifier data available.</p>
                  )}
                </div>
              )
            ) : (
              <p style={{ margin: 0 }}>Type an address, select from Lightbox autocomplete, then click Load.</p>
            )}
          </div>
        </div>
      </Split>
    </div>
  );
}

const DEFAULT_VIEW: ViewState = { longitude: -95, latitude: 40, zoom: 15 };

export default function App() {
  const [regridData, setRegridData] = useState<RegridParcel | null>(null);
  const [lightboxData, setLightboxData] = useState<unknown>(null);
  const [lightboxStructuresData, setLightboxStructuresData] = useState<LightboxStructuresData>(null);
  const [lightboxFemaData, setLightboxFemaData] = useState<{ nfhls?: Array<Record<string, unknown>> } | null>(null);
  const [lightboxZoningData, setLightboxZoningData] = useState<{ zonings?: Array<Record<string, unknown>> } | null>(null);
  const [lightboxRiskIndexData, setLightboxRiskIndexData] = useState<Record<string, unknown> | null>(null);
  const [lightboxWetlandsData, setLightboxWetlandsData] = useState<Record<string, unknown> | null>(null);
  const [viewState, setViewState] = useState<ViewState>(DEFAULT_VIEW);
  const [transmissionLinesGeoJson, setTransmissionLinesGeoJson] = useState<GeoJsonFC | null>(null);
  const [showTransmissionLines, setShowTransmissionLines] = useState(true);
  const [fireSafetyGeoJson, setFireSafetyGeoJson] = useState<(GeoJsonFC & { nearestDistanceM?: number | null }) | null>(null);

  // Fetch fire hydrants/extinguishers when parcel is loaded (use viewState center as parcel location)
  useEffect(() => {
    const hasParcel = !!(regridData || lightboxData);
    if (!hasParcel) { setFireSafetyGeoJson(null); return; }
    let cancelled = false;
    fetch(`/api/regrid/osm/fire-safety?lat=${viewState.latitude}&lon=${viewState.longitude}&radius=500`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d?.type === 'FeatureCollection') setFireSafetyGeoJson(d);
        else setFireSafetyGeoJson(null);
      })
      .catch(() => { if (!cancelled) setFireSafetyGeoJson(null); });
    return () => { cancelled = true; };
  }, [regridData, lightboxData]);

  useEffect(() => {
    const [minLon, minLat, maxLon, maxLat] = viewStateBbox(viewState);
    let cancelled = false;
    const t = setTimeout(() => {
      fetch(`/api/regrid/hifld/transmission-lines?minLon=${minLon}&minLat=${minLat}&maxLon=${maxLon}&maxLat=${maxLat}`)
        .then((r) => r.json())
        .then((txData) => {
          if (cancelled) return;
          const txFC = txData?.type === 'FeatureCollection';
          setTransmissionLinesGeoJson(txFC ? txData : null);
        })
        .catch(() => {
          if (!cancelled) setTransmissionLinesGeoJson(null);
        });
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [viewState.longitude, viewState.latitude, viewState.zoom]);

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '1rem', borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0, fontSize: '1.25rem' }}>Regrid vs Lightbox</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginLeft: 'auto' }}>
          <span style={{ fontSize: '0.8rem', color: '#666', fontWeight: 500 }}>Map layers</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.9rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={showTransmissionLines} onChange={(e) => setShowTransmissionLines(e.target.checked)} />
            Transmission lines
          </label>
        </div>
      </header>
      <Split sizes={[50, 50]} minSize={200} style={{ flex: 1, display: 'flex', minHeight: 0 }} className="split-container">
        <RegridPanel data={regridData} setData={setRegridData} lightboxData={lightboxData} lightboxStructuresData={lightboxStructuresData} lightboxFemaData={lightboxFemaData} lightboxZoningData={lightboxZoningData} viewState={viewState} setViewState={setViewState} transmissionLinesGeoJson={transmissionLinesGeoJson} showTransmissionLines={showTransmissionLines} fireSafetyGeoJson={fireSafetyGeoJson} />
        <LightboxPanel data={lightboxData} setData={setLightboxData} regridData={regridData} structuresData={lightboxStructuresData} setStructuresData={setLightboxStructuresData} femaData={lightboxFemaData} setFemaData={setLightboxFemaData} zoningData={lightboxZoningData} setZoningData={setLightboxZoningData} riskIndexData={lightboxRiskIndexData} setRiskIndexData={setLightboxRiskIndexData} wetlandsData={lightboxWetlandsData} setWetlandsData={setLightboxWetlandsData} viewState={viewState} setViewState={setViewState} transmissionLinesGeoJson={transmissionLinesGeoJson} showTransmissionLines={showTransmissionLines} fireSafetyGeoJson={fireSafetyGeoJson} />
      </Split>
    </div>
  );
}
