import { useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl';
import mapboxgl from 'mapbox-gl';
import type { MapLayerMouseEvent } from 'react-map-gl';
import {
  labelEdges,
  parseWktOuterRing,
  type ZoneomicsParcel,
  type EdgeLabelingResult,
  type FrontRule,
  type FrontRuleOverride,
} from '../../edge-labeling/edge-labeling';
import jurisdictionDb from '../../zoning-ordinances/zoning_ordinance_links.json';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';

// Live tester for the edge-labeling pipeline: type an address, the selected
// data provider pulls subject + neighbor parcels, and the engine labels the
// lot's edges. Two providers, same wire shape:
//   zoneomics — the Express zoneomics-backend (quota-limited)
//   opendata  — the free stack (Census/Google geocode + county parcel fabrics
//               + CA statewide zoning), served by gaudi-api-port/app_poc.py
// The jurisdiction's front rule comes from the unified jurisdiction db
// (zoning-ordinances/zoning_ordinance_links.json), matched by Zoneomics
// city_id or by jurisdiction name (opendata payloads).

const TAG_COLORS: Record<string, string> = {
  front: '#CE3A2E',
  street_side: '#EF9F27',
  side: '#5F6E64',
  rear: '#185FA5',
};

interface EdgesApiResponse {
  geocode: { lat: number; lng: number };
  subject: ZoneomicsParcel;
  neighbors: ZoneomicsParcel[];
  meta: {
    city_id?: number; city_name?: string; last_updated?: string;
    // opendata provider only:
    county_name?: string; geocode_source?: string; source?: string; zoning_vintage?: string;
  } | null;
  zone: { zone_code?: string; zone_type?: string } | null;
  callCount: number;
  radius?: number; // zoneomics only
  discovery?: string;
  droppedStubs?: number; // zoneomics only
  subject_street_name?: string | null; // opendata only (Google route)
  flags?: string[]; // opendata only (fetch-side degradation flags)
}

/** POST /edges/label response: the PYTHON engine (the gaudi-api production
 *  port) run server-side. Same wire shape as the TS result, plus
 *  streetNameSource provenance on street edges. */
interface LabelApiResponse {
  result: EdgeLabelingResult & {
    edges: Array<EdgeLabelingResult['edges'][number] & { abuts: { streetNameSource?: string } }>;
  };
  engine: string;
  front_rule_used: string;
  roads_namer: boolean;
}

type Engine = 'ts-client' | 'python-server';
type DataSource = 'opendata' | 'zoneomics';
const FIXTURES = ['corner-san-jose', 'madrono-palo-alto'] as const;

type FC = GeoJSON.FeatureCollection;

type FrontRuleRecord = { rule: FrontRule; overrides?: FrontRuleOverride[] };
type JurisdictionRecord = { jurisdiction: string; zoneomics_city_id: number; front_rule?: FrontRuleRecord };

const normalizeName = (name: string) => name.toLowerCase().split(/\s+/).filter(Boolean).join(' ');

/** Front rule by Zoneomics city_id (zoneomics payloads) or jurisdiction name
 *  (opendata payloads, from the Census place) — the client twin of
 *  gaudi-api-port/services/parcel_data/front_rules.py. */
function lookupFrontRule(cityId: number | undefined, cityName?: string): FrontRuleRecord | undefined {
  const recs = (jurisdictionDb as unknown as { jurisdictions: JurisdictionRecord[] }).jurisdictions;
  if (cityId != null) {
    const byId = recs.find((r) => r.zoneomics_city_id === cityId)?.front_rule;
    if (byId) return byId;
  }
  if (cityName) {
    return recs.find((r) => normalizeName(r.jurisdiction) === normalizeName(cityName))?.front_rule;
  }
  return undefined;
}

function parcelPolygonFeature(p: ZoneomicsParcel, kind: 'subject' | 'neighbor'): GeoJSON.Feature | null {
  try {
    const ring = parseWktOuterRing(p.boundary);
    return {
      type: 'Feature',
      properties: { apn: p.apn, address: p.address, kind },
      geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] },
    };
  } catch {
    return null;
  }
}

export default function EdgesPanel() {
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [api, setApi] = useState<EdgesApiResponse | null>(null);
  const [result, setResult] = useState<EdgeLabelingResult | null>(null);
  const [rule, setRule] = useState<FrontRule | undefined>(undefined);
  const [selected, setSelected] = useState<number>(-1);
  const [vs, setVs] = useState({ longitude: -122.15, latitude: 37.43, zoom: 12 });
  const [engine, setEngine] = useState<Engine>('python-server');
  const [source, setSource] = useState<DataSource>('opendata');
  const [engineInfo, setEngineInfo] = useState<string | null>(null);

  /** Label `data` with the selected engine and push the result into state. */
  const runEngine = async (data: EdgesApiResponse, fixture?: string) => {
    const fr = lookupFrontRule(data.meta?.city_id, data.meta?.city_name);
    setApi(data);
    setRule(fr?.rule);
    let labeled: EdgeLabelingResult;
    if (engine === 'python-server') {
      // The production path: gaudi-api's Python engine, run server-side.
      // Fixtures only exist on the zoneomics backend; live payloads label on
      // the backend that produced them (both routes share the wire contract).
      const labelBase = fixture ? 'zoneomics' : source;
      const r = await fetch(`/api/${labelBase}/edges/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fixture ? { fixture } : {
          subject: data.subject, neighbors: data.neighbors, meta: data.meta, zone: data.zone,
          subject_street_name: data.subject_street_name ?? null,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error ?? `HTTP ${r.status}`);
      const lr = d as LabelApiResponse;
      labeled = lr.result;
      setEngineInfo(`python engine · rule: ${lr.front_rule_used} · roads namer: ${lr.roads_namer ? 'on' : 'off (census only)'}`);
    } else {
      labeled = labelEdges({
        subject: data.subject,
        neighbors: data.neighbors,
        frontRule: fr?.rule,
        frontRuleOverrides: fr?.overrides,
        zone: data.zone ?? undefined,
      });
      setEngineInfo('typescript engine (client, reference)');
    }
    setResult(labeled);
    return labeled;
  };

  /** Offline path: a canned fixture labeled by the server-side Python engine. */
  const runFixture = async (name: string) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    setSelected(-1);
    try {
      const r = await fetch('/api/zoneomics/edges/label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fixture: name }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error ?? `HTTP ${r.status}`);
      // Fixtures embed the /edges wire shape; fetch it for the map layers.
      const fx = await (await fetch(`/api/zoneomics/edges/fixture/${name}`)).json();
      const lr = d as LabelApiResponse;
      setApi(fx);
      setRule(undefined);
      setResult(lr.result);
      setEngineInfo(`python engine · fixture ${name} · rule: ${lr.front_rule_used} · roads namer: ${lr.roads_namer ? 'on' : 'off (census only)'}`);
      setVs({ longitude: fx.subject.lng, latitude: fx.subject.lat, zoom: 17.5 });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'fixture failed');
    } finally {
      setLoading(false);
    }
  };

  const search = async () => {
    if (!address.trim() || loading) return;
    setLoading(true);
    setError(null);
    setSelected(-1);
    try {
      const r = await fetch(`/api/${source}/edges?address=${encodeURIComponent(address.trim())}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error ?? `HTTP ${r.status}`);
      const data = d as EdgesApiResponse;
      const labeled = await runEngine(data);
      const fr = lookupFrontRule(data.meta?.city_id, data.meta?.city_name);
      // One greppable summary line per lookup (mirrors the UI status line),
      // plus the labeled edges as a table.
      console.info(
        `[edge-labeling] ${data.meta?.city_name ?? '?'} · zone ${data.zone?.zone_code ?? '?'} (${data.zone?.zone_type ?? '?'}) · APN ${data.subject.apn} · ` +
        `front rule: ${fr?.rule ?? 'default (address_street)'} · source: ${source}${data.meta?.geocode_source ? ` (geocode: ${data.meta.geocode_source})` : ''} · engine: ${engine} · ` +
        `${data.callCount} API calls · discovery ${data.discovery ?? 'radius'} · ` +
        `${labeled.stats.roadGaps} road gap(s) · streets: ${labeled.stats.streetNames.join(', ') || '(unnamed)'} · ` +
        `flags: ${[...(data.flags ?? []), ...labeled.flags].join(', ') || '(none)'}`,
      );
      console.table(labeled.edges.map((e) => ({
        tag: e.tag,
        lengthFt: e.lengthFt,
        abuts: e.abuts.kind === 'street' ? `street: ${e.abuts.streetName ?? '?'}` : `APN ${e.abuts.apns.join(', ')}`,
        basis: e.basis,
        confidence: e.confidence,
        flags: e.flags.join(', '),
      })));
      setVs({ longitude: data.subject.lng, latitude: data.subject.lat, zoom: 17.5 });
    } catch (e) {
      setApi(null);
      setResult(null);
      setError(e instanceof Error ? e.message : 'request failed');
    } finally {
      setLoading(false);
    }
  };

  const parcelsFC: FC = {
    type: 'FeatureCollection',
    features: api
      ? [parcelPolygonFeature(api.subject, 'subject'), ...api.neighbors.map((n) => parcelPolygonFeature(n, 'neighbor'))].filter(
          (f): f is GeoJSON.Feature => f !== null,
        )
      : [],
  };

  const edgesFC: FC = {
    type: 'FeatureCollection',
    features: (result?.edges ?? []).map((e, idx) => ({
      type: 'Feature' as const,
      properties: { idx, tag: e.tag, color: TAG_COLORS[e.tag] ?? '#000' },
      geometry: { type: 'LineString' as const, coordinates: e.pts },
    })),
  };

  const labelsFC: FC = {
    type: 'FeatureCollection',
    features: (result?.edges ?? []).map((e, idx) => ({
      type: 'Feature' as const,
      properties: { idx, label: e.tag.toUpperCase() },
      geometry: { type: 'Point' as const, coordinates: e.pts[Math.floor(e.pts.length / 2)] },
    })),
  };

  const onMapClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (f?.properties && typeof f.properties.idx === 'number') {
      setSelected((cur) => (cur === f.properties!.idx ? -1 : (f.properties!.idx as number)));
    }
  };

  const abutsText = (e: EdgeLabelingResult['edges'][number]) => {
    if (e.abuts.kind !== 'street') return `APN ${e.abuts.apns.join(', ')}`;
    const src = (e.abuts as { streetNameSource?: string }).streetNameSource;
    return `street: ${e.abuts.streetName ?? '?'}${src ? ` (${src})` : ''}`;
  };

  return (
    <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
      <div style={{ flex: 1.7, position: 'relative', minWidth: 0 }}>
        <Map
          id="edges-map"
          mapLib={mapboxgl}
          mapboxAccessToken={MAPBOX_TOKEN}
          {...vs}
          onMove={(evt) => setVs({ longitude: evt.viewState.longitude, latitude: evt.viewState.latitude, zoom: evt.viewState.zoom })}
          style={{ width: '100%', height: '100%' }}
          mapStyle="mapbox://styles/mapbox/streets-v12"
          interactiveLayerIds={['edge-hit']}
          onClick={onMapClick}
        >
          {parcelsFC.features.length > 0 && (
            <Source id="edges-parcels" type="geojson" data={parcelsFC}>
              <Layer
                id="edges-parcels-fill"
                type="fill"
                paint={{ 'fill-color': ['match', ['get', 'kind'], 'subject', '#f7faf5', '#dfe6df'], 'fill-opacity': 0.55 }}
              />
              <Layer id="edges-parcels-line" type="line" paint={{ 'line-color': '#9aa79b', 'line-width': 1 }} />
              <Layer
                id="edges-parcels-apn"
                type="symbol"
                minzoom={16.5}
                layout={{ 'text-field': ['get', 'apn'], 'text-size': 10 }}
                paint={{ 'text-color': '#667066', 'text-halo-color': '#fff', 'text-halo-width': 1 }}
              />
            </Source>
          )}
          {edgesFC.features.length > 0 && (
            <Source id="edges-lines" type="geojson" data={edgesFC}>
              <Layer
                id="edge-lines"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{
                  'line-color': ['case', ['==', ['get', 'idx'], selected], '#CE3A2E', ['get', 'color']],
                  'line-width': ['case', ['==', ['get', 'idx'], selected], 7, 3.5],
                }}
              />
              <Layer id="edge-hit" type="line" paint={{ 'line-color': '#000', 'line-opacity': 0, 'line-width': 18 }} />
            </Source>
          )}
          {labelsFC.features.length > 0 && (
            <Source id="edges-labels" type="geojson" data={labelsFC}>
              <Layer
                id="edge-labels"
                type="symbol"
                layout={{ 'text-field': ['get', 'label'], 'text-size': 11, 'text-offset': [0, -1] }}
                paint={{ 'text-color': '#24312B', 'text-halo-color': '#fff', 'text-halo-width': 1.6 }}
              />
            </Source>
          )}
        </Map>
      </div>
      <div style={{ flex: 1, minWidth: 340, maxWidth: 460, overflowY: 'auto', borderLeft: '1px solid #eee', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.8rem', flexWrap: 'wrap' }}>
          <span style={{ color: '#888' }}>source:</span>
          {(['opendata', 'zoneomics'] as DataSource[]).map((src) => (
            <button
              key={src}
              onClick={() => setSource(src)}
              style={{
                padding: '0.25rem 0.6rem', borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem',
                border: source === src ? '1.5px solid #24312B' : '1px solid #ccc',
                background: source === src ? '#24312B' : '#fff', color: source === src ? '#fff' : '#444',
              }}
            >
              {src === 'opendata' ? 'Open data (free)' : 'Zoneomics (quota)'}
            </button>
          ))}
          <span style={{ color: '#888', marginLeft: '0.5rem' }}>engine:</span>
          {(['python-server', 'ts-client'] as Engine[]).map((eng) => (
            <button
              key={eng}
              onClick={() => setEngine(eng)}
              style={{
                padding: '0.25rem 0.6rem', borderRadius: 6, cursor: 'pointer', fontSize: '0.78rem',
                border: engine === eng ? '1.5px solid #24312B' : '1px solid #ccc',
                background: engine === eng ? '#24312B' : '#fff', color: engine === eng ? '#fff' : '#444',
              }}
            >
              {eng === 'python-server' ? 'Python (server, production port)' : 'TypeScript (client, reference)'}
            </button>
          ))}
          <span style={{ color: '#888', marginLeft: '0.5rem' }}>offline fixtures:</span>
          {FIXTURES.map((fx) => (
            <button
              key={fx}
              onClick={() => runFixture(fx)}
              disabled={loading}
              style={{ padding: '0.25rem 0.6rem', borderRadius: 6, border: '1px dashed #999', background: '#fff', color: '#444', cursor: 'pointer', fontSize: '0.78rem' }}
            >
              {fx}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') search(); }}
            placeholder="Address, e.g. 804 Lennox Ct, Sunnyvale, CA"
            style={{ flex: 1, padding: '0.5rem 0.6rem', border: '1px solid #ccc', borderRadius: 6, fontSize: '0.9rem' }}
          />
          <button onClick={search} disabled={loading} style={{ padding: '0.5rem 0.9rem', borderRadius: 6, border: '1px solid #24312B', background: '#24312B', color: '#fff', cursor: 'pointer', fontSize: '0.9rem' }}>
            {loading ? 'Loading…' : 'Label edges'}
          </button>
        </div>
        {error && <div style={{ color: '#CE3A2E', fontSize: '0.85rem' }}>{error}</div>}
        {api && result && (
          <>
            {engineInfo && <div style={{ fontSize: '0.78rem', color: '#24312B', background: '#eef2ee', borderRadius: 6, padding: '0.3rem 0.6rem' }}>{engineInfo}</div>}
            <div style={{ fontSize: '0.8rem', color: '#666' }}>
              {api.meta?.city_name ?? '?'} · zone {api.zone?.zone_code ?? '?'} · APN {api.subject.apn} · front rule: {rule ?? 'default (address_street)'} ·{' '}
              {api.callCount} API calls · discovery {api.discovery ?? 'radius'}
              {api.meta?.geocode_source && <> · geocode: {api.meta.geocode_source}</>}
              {' '}· {result.stats.roadGaps} road gap{result.stats.roadGaps === 1 ? '' : 's'}
              {result.stats.streetNames.length > 0 && <> · streets: {result.stats.streetNames.join(', ')}</>}
              {((api.flags?.length ?? 0) > 0 || result.flags.length > 0) && (
                <> · flags: {[...(api.flags ?? []), ...result.flags].join(', ')}</>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {result.edges.map((e, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelected(selected === idx ? -1 : idx)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem', textAlign: 'left', cursor: 'pointer',
                    padding: '0.5rem 0.6rem', borderRadius: 6, fontSize: '0.85rem', background: '#fff',
                    border: selected === idx ? '1.5px solid #CE3A2E' : '1px solid #ddd',
                  }}
                >
                  <span style={{ background: TAG_COLORS[e.tag], color: '#fff', borderRadius: 4, padding: '1px 7px', fontSize: '0.7rem', letterSpacing: '0.06em', textTransform: 'uppercase', minWidth: 78, textAlign: 'center' }}>
                    {e.tag}
                  </span>
                  {e.flags.includes('second_front') && (
                    <span style={{ background: '#E8A33D', color: '#fff', borderRadius: 4, padding: '1px 7px', fontSize: '0.7rem', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                      also front
                    </span>
                  )}
                  <span style={{ flex: 1 }}>{abutsText(e)}</span>
                  <span style={{ color: '#888', fontVariantNumeric: 'tabular-nums' }}>{Math.round(e.lengthFt)} ft</span>
                </button>
              ))}
            </div>
            {selected >= 0 && result.edges[selected] && (
              <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: '0.6rem 0.75rem', fontSize: '0.82rem', lineHeight: 1.6 }}>
                <div><strong style={{ color: '#CE3A2E', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{result.edges[selected].tag}</strong></div>
                <div>abuts: {abutsText(result.edges[selected])}</div>
                <div>length: {result.edges[selected].lengthFt} ft</div>
                <div>basis: {result.edges[selected].basis} · confidence: {result.edges[selected].confidence}</div>
                {result.edges[selected].flags.length > 0 && <div>flags: {result.edges[selected].flags.join(', ')}</div>}
              </div>
            )}
          </>
        )}
        {!api && !error && (
          <div style={{ color: '#888', fontSize: '0.85rem' }}>
            Enter an address to pull the parcel and its neighbors from the selected source and label the lot's
            edges (front / street_side / side / rear). Click an edge on the map or in the list to inspect it.
          </div>
        )}
      </div>
    </div>
  );
}
