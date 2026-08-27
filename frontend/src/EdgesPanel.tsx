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
} from '../../edge-labeling/edge-labeling';
import frontRules from '../../edge-labeling/jurisdiction-front-rules.json';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';

// Live tester for edge-labeling/edge-labeling.ts: type an address, the
// zoneomics-backend pulls subject + neighbor parcels, and the module labels
// the lot's edges client-side. The jurisdiction's front rule comes from
// jurisdiction-front-rules.json, keyed by Zoneomics city_id.

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
  meta: { city_id?: number; city_name?: string; last_updated?: string } | null;
  zone: { zone_code?: string } | null;
  callCount: number;
  droppedStubs: number;
}

type FC = GeoJSON.FeatureCollection;

function lookupFrontRule(cityId: number | undefined): FrontRule | undefined {
  if (cityId == null) return undefined;
  const entry = (frontRules as unknown as Record<string, { front_rule?: FrontRule }>)[String(cityId)];
  return entry?.front_rule;
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

  const search = async () => {
    if (!address.trim() || loading) return;
    setLoading(true);
    setError(null);
    setSelected(-1);
    try {
      const r = await fetch(`/api/zoneomics/edges?address=${encodeURIComponent(address.trim())}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error ?? `HTTP ${r.status}`);
      const data = d as EdgesApiResponse;
      const fr = lookupFrontRule(data.meta?.city_id);
      setApi(data);
      setRule(fr);
      setResult(labelEdges({ subject: data.subject, neighbors: data.neighbors, frontRule: fr }));
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

  const abutsText = (e: EdgeLabelingResult['edges'][number]) =>
    e.abuts.kind === 'street' ? `street: ${e.abuts.streetName ?? '?'}` : `APN ${e.abuts.apns.join(', ')}`;

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
            <div style={{ fontSize: '0.8rem', color: '#666' }}>
              {api.meta?.city_name ?? '?'} · zone {api.zone?.zone_code ?? '?'} · APN {api.subject.apn} · front rule: {rule ?? 'default (shortest)'} ·{' '}
              {api.callCount} API calls · {result.stats.roadGaps} road gap{result.stats.roadGaps === 1 ? '' : 's'}
              {result.stats.streetNames.length > 0 && <> · streets: {result.stats.streetNames.join(', ')}</>}
              {result.flags.length > 0 && <> · flags: {result.flags.join(', ')}</>}
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
            Enter an address to pull the parcel and its neighbors from Zoneomics and label the lot's edges
            (front / street_side / side / rear). Click an edge on the map or in the list to inspect it.
          </div>
        )}
      </div>
    </div>
  );
}
