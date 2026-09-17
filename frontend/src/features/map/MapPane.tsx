import { useEffect, useRef, useState } from "react";
import maplibregl, { type LngLatBoundsLike, type Map as MLMap } from "maplibre-gl";
import { useTrip, selectedDay, selectedEvent, dayEvents } from "@/store/trip";
import { colourFor, styleFor, MAP_COLOURS, type StyleName } from "./styles";
import type { BBox, Trip, TripEvent } from "@/lib/types";
import { TYPE_META, duration } from "@/lib/format";

/**
 * The map pane. Reacts to the scope machine; never owns selection itself.
 *
 * Three scopes, three framings:
 *   trip      the whole route, day markers, clustered photographs
 *   day       fits Day.bbox; that day's legs lit, the rest faded to context
 *   activity  fits the track; trailhead, summit and photographs along the line
 *
 * Geometry is pushed as GeoJSON into a handful of long-lived sources rather than
 * re-created per render. MapLibre keeps the GPU buffers; React only sets data.
 */

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function boundsOf(b: BBox): LngLatBoundsLike {
  return [
    [b.min_lon, b.min_lat],
    [b.max_lon, b.max_lat],
  ];
}

export function MapPane() {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [style, setStyle] = useState<StyleName>("street");
  const [mapKey, setMapKey] = useState<string | null>(null);

  const state = useTrip();
  const { trip, scope } = state;
  const day = selectedDay(state);
  const event = selectedEvent(state);

  // The key lives on the backend so an exported capsule carries no personal quota.
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((h) => setMapKey(h.mapTilerKey ?? ""))
      .catch(() => setMapKey(""));
  }, []);

  useEffect(() => {
    if (!container.current || map.current || mapKey === null) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: styleFor(style, mapKey),
      center: [-8, 53.4],
      zoom: 5.5,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      addLayers(m);
      setReady(true);
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, [mapKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Switching basemap destroys the style, so the layers have to be rebuilt.
  useEffect(() => {
    const m = map.current;
    if (!m || mapKey === null || !ready) return;
    m.setStyle(styleFor(style, mapKey));
    m.once("styledata", () => {
      addLayers(m);
      setReady(true);
    });
  }, [style]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----------------------------------------------------------------- data
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !trip) return;

    const activeIds = new Set(
      day ? dayEvents(trip, day).map((e) => e.id) : trip.events.map((e) => e.id),
    );
    // Narrow the pins as the scope narrows: the whole trip, then a day, then the single
    // activity. Showing a day's 200 photographs while looking at one hike is noise.
    const pinScope =
      scope === "activity" && event
        ? new Set([event.id])
        : day
          ? activeIds
          : null;

    setData(m, "routes", routesGeoJSON(trip, activeIds));
    setData(m, "photos", photosGeoJSON(trip, pinScope));
    setData(m, "places", placesGeoJSON(trip, pinScope));
    setData(m, "highlights", highlightsGeoJSON(event));

    const geom = event?.track_ids[0]
      ? state.trackGeometry[event.track_ids[0]]
      : undefined;
    setData(m, "track", trackGeoJSON(geom?.simplified));
  }, [ready, trip, day, event, scope, state.trackGeometry]);

  // ----------------------------------------------------------------- framing
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !trip) return;
    const padding = { top: 60, bottom: 60, left: 60, right: 60 };

    if (scope === "activity" && event) {
      const track = trip.tracks.find((t) => t.id === event.track_ids[0]);
      if (track?.bbox) {
        m.fitBounds(
          [
            [track.bbox[1], track.bbox[0]],
            [track.bbox[3], track.bbox[2]],
          ],
          { padding, duration: 900 },
        );
        return;
      }
    }
    if (scope === "day" && day?.bbox) {
      m.fitBounds(boundsOf(day.bbox), { padding, duration: 900 });
      return;
    }
    if (trip.bbox) m.fitBounds(boundsOf(trip.bbox), { padding, duration: 900 });
  }, [ready, scope, day?.id, event?.id, trip?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----------------------------------------------------------------- cursor marker
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const geom = event?.track_ids[0] ? state.trackGeometry[event.track_ids[0]] : undefined;
    const p = geom && state.cursorIndex !== null ? geom.profile[state.cursorIndex] : null;
    setData(
      m,
      "cursor",
      p
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: {},
                geometry: { type: "Point", coordinates: [p.lon, p.lat] },
              },
            ],
          }
        : EMPTY,
    );
  }, [ready, state.cursorIndex, event?.id, state.trackGeometry]);

  return (
    <div className="relative h-full w-full">
      <div ref={container} className="h-full w-full" />

      <div className="absolute left-4 top-4 flex gap-1 rounded-lg bg-white/95 p-1 shadow-lg ring-1 ring-black/5">
        {(["street", "satellite"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStyle(s)}
            className={`rounded px-3 py-1.5 text-[11px] font-medium capitalize ${
              style === s ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {scope !== "trip" && (
        <button
          onClick={state.back}
          className="absolute bottom-4 left-4 rounded-lg bg-white/95 px-3 py-2 text-xs font-medium text-zinc-700 shadow-lg ring-1 ring-black/5 hover:bg-white"
        >
          &larr; {scope === "activity" ? "Back to the day" : "Whole trip"}
        </button>
      )}

      {mapKey === "" && (
        <div className="absolute bottom-4 right-4 rounded bg-amber-50 px-2.5 py-1.5 text-[10px] text-amber-800 ring-1 ring-amber-200">
          No MAPTILER_KEY &mdash; raster fallback
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------- layers

function setData(m: MLMap, id: string, data: GeoJSON.FeatureCollection) {
  const src = m.getSource(id) as maplibregl.GeoJSONSource | undefined;
  if (src) src.setData(data);
}

function addLayers(m: MLMap) {
  for (const id of ["routes", "track", "photos", "places", "highlights", "cursor"]) {
    if (!m.getSource(id)) {
      m.addSource(id, {
        type: "geojson",
        data: EMPTY,
        ...(id === "photos" ? { cluster: true, clusterRadius: 45, clusterMaxZoom: 13 } : {}),
      });
    }
  }

  // Route legs. Reliability drives the dash pattern, so a crossing reconstructed from two
  // breadcrumbs can never be mistaken for a measured line (ADR-0007).
  m.addLayer({
    id: "routes-casing",
    type: "line",
    source: "routes",
    paint: {
      "line-color": "#ffffff",
      "line-width": ["case", ["get", "active"], 6, 4],
      "line-opacity": ["case", ["get", "active"], 0.9, 0.25],
    },
    layout: { "line-cap": "round", "line-join": "round" },
  });
  m.addLayer({
    id: "routes-line",
    type: "line",
    source: "routes",
    paint: {
      "line-color": ["get", "colour"],
      "line-width": ["case", ["get", "active"], 3, 2],
      "line-opacity": ["case", ["get", "active"], 1, 0.3],
      "line-dasharray": [
        "case",
        ["==", ["get", "reliability"], "measured"],
        ["literal", [1]],
        ["literal", [2, 2]],
      ],
    },
    layout: { "line-cap": "round", "line-join": "round" },
  });

  m.addLayer({
    id: "track-line",
    type: "line",
    source: "track",
    paint: { "line-color": MAP_COLOURS.track, "line-width": 4 },
    layout: { "line-cap": "round", "line-join": "round" },
  });

  m.addLayer({
    id: "places",
    type: "circle",
    source: "places",
    paint: {
      "circle-radius": ["get", "radius"],
      "circle-color": ["get", "colour"],
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
    },
  });

  // Summits and passes get a label, because the name is the point.
  m.addLayer({
    id: "highlights",
    type: "circle",
    source: "highlights",
    paint: {
      "circle-radius": 6,
      "circle-color": "#ffffff",
      "circle-stroke-width": 3,
      "circle-stroke-color": MAP_COLOURS.track,
    },
  });
  m.addLayer({
    id: "highlights-label",
    type: "symbol",
    source: "highlights",
    layout: {
      "text-field": ["get", "label"],
      "text-size": 11,
      "text-offset": [0, -1.4],
      "text-anchor": "bottom",
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#18181b",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1.6,
    },
  });

  m.addLayer({
    id: "photo-clusters",
    type: "circle",
    source: "photos",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": MAP_COLOURS.photo,
      "circle-radius": ["step", ["get", "point_count"], 12, 10, 16, 40, 22],
      "circle-opacity": 0.85,
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
    },
  });
  m.addLayer({
    id: "photo-cluster-count",
    type: "symbol",
    source: "photos",
    filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 11 },
    paint: { "text-color": "#ffffff" },
  });
  m.addLayer({
    id: "photo-point",
    type: "circle",
    source: "photos",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-radius": 4,
      "circle-color": MAP_COLOURS.photo,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#ffffff",
    },
  });

  m.addLayer({
    id: "cursor",
    type: "circle",
    source: "cursor",
    paint: {
      "circle-radius": 7,
      "circle-color": MAP_COLOURS.selected,
      "circle-stroke-width": 3,
      "circle-stroke-color": "#ffffff",
    },
  });

  // Clicking the map drives selection, closing the loop with the timeline.
  m.on("click", "places", (e) => {
    const id = e.features?.[0]?.properties?.event_id;
    if (typeof id === "string") useTrip.getState().selectEvent(id);
  });

  // A cluster you cannot open is just a number. Zoom to the point where it splits.
  m.on("click", "photo-clusters", (e) => {
    const feature = e.features?.[0];
    const clusterId = feature?.properties?.cluster_id;
    if (clusterId == null) return;
    const src = m.getSource("photos") as maplibregl.GeoJSONSource;
    void src.getClusterExpansionZoom(clusterId).then((zoom) => {
      const [lng, lat] = (feature!.geometry as GeoJSON.Point).coordinates as [
        number,
        number,
      ];
      m.easeTo({ center: [lng, lat], zoom: Math.min(zoom + 0.4, 18), duration: 500 });
    });
  });

  // A lone photograph opens in the viewer, so a pin on the map is a way into the album.
  m.on("click", "photo-point", (e) => {
    const id = e.features?.[0]?.properties?.media_id;
    if (typeof id !== "string") return;
    const { trip, openLightbox } = useTrip.getState();
    if (!trip) return;
    const nearby = trip.media.filter((x) => x.thumb_ref && x.lat !== null);
    const idx = nearby.findIndex((x) => x.id === id);
    if (idx >= 0) openLightbox(nearby, idx);
  });

  // Hover tells you what a pin IS -- a photograph, a summit, a visit -- without a click.
  attachHoverPopup(m, "photo-point", (props) => {
    const thumb = props.thumb as string | undefined;
    const time = (props.time as string) ?? "";
    return `<div class="w-40">
      ${thumb ? `<img src="/${thumb}" class="h-28 w-full rounded-t-lg object-cover" />` : ""}
      <div class="px-2.5 py-1.5 text-[11px] text-zinc-600">Photograph${
        time ? ` &middot; ${time}` : ""
      }</div></div>`;
  });

  attachHoverPopup(m, "photo-clusters", (props) => {
    const n = props.point_count as number;
    return `<div class="px-3 py-2 text-[11px] text-zinc-700">
      <b>${n}</b> photographs &middot; click to zoom in</div>`;
  });

  attachHoverPopup(m, "places", (props) => {
    const name = (props.name as string) ?? "";
    const label = (props.type_label as string) ?? "";
    const icon = (props.icon as string) ?? "";
    const meta = (props.meta as string) ?? "";
    const thumb = props.thumb as string | undefined;
    return `<div class="w-44">
      ${thumb ? `<img src="/${thumb}" class="h-24 w-full rounded-t-lg object-cover" />` : ""}
      <div class="px-2.5 py-2">
        <div class="text-xs font-semibold text-zinc-900">${escapeHtml(name)}</div>
        <div class="mt-0.5 text-[10px] text-zinc-500">${icon} ${label}${
          meta ? ` &middot; ${meta}` : ""
        }</div>
      </div></div>`;
  });

  attachHoverPopup(m, "highlights", (props) => {
    const name = (props.name as string) ?? "";
    const kind = (props.kind as string) ?? "";
    const ele = props.ele as number | undefined;
    const noun = kind.includes("peak")
      ? "Summit"
      : kind.includes("water")
        ? "Lake"
        : "Pass";
    return `<div class="px-3 py-2">
      <div class="text-xs font-semibold text-zinc-900">${escapeHtml(name)}</div>
      <div class="mt-0.5 text-[10px] text-zinc-500">${noun}${
        ele ? ` &middot; ${Math.round(ele)} m` : ""
      }</div></div>`;
  });

  for (const layer of ["places", "photo-clusters", "photo-point", "highlights"]) {
    m.on("mouseenter", layer, () => (m.getCanvas().style.cursor = "pointer"));
    m.on("mouseleave", layer, () => (m.getCanvas().style.cursor = ""));
  }
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c,
  );
}

/** A pin that does not say what it is may as well not be there. */
function attachHoverPopup(
  m: MLMap,
  layer: string,
  render: (props: Record<string, unknown>) => string,
) {
  const popup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 12,
    maxWidth: "none",
  });
  m.on("mousemove", layer, (e) => {
    const f = e.features?.[0];
    if (!f) return;
    const coords =
      f.geometry.type === "Point"
        ? (f.geometry.coordinates as [number, number])
        : [e.lngLat.lng, e.lngLat.lat];
    popup.setLngLat(coords as [number, number]).setHTML(render(f.properties ?? {})).addTo(m);
  });
  m.on("mouseleave", layer, () => popup.remove());
}

// --------------------------------------------------------------------- geojson

function routesGeoJSON(trip: Trip, active: Set<string>): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: trip.route
      .filter((s) => s.points.length >= 2)
      .map((s) => ({
        type: "Feature" as const,
        properties: {
          colour: colourFor(s.kind),
          reliability: s.reliability,
          active: active.has(s.event_id),
          event_id: s.event_id,
        },
        geometry: {
          type: "LineString" as const,
          coordinates: s.points.map(([lat, lon]) => [lon, lat]),
        },
      })),
  };
}

function trackGeoJSON(points?: [number, number][]): GeoJSON.FeatureCollection {
  if (!points || points.length < 2) return EMPTY;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: points.map(([lat, lon]) => [lon, lat]),
        },
      },
    ],
  };
}

function photosGeoJSON(trip: Trip, limitTo: Set<string> | null): GeoJSON.FeatureCollection {
  const allowed = limitTo
    ? new Set(
        trip.events.filter((e) => limitTo.has(e.id)).flatMap((e) => e.media_ids),
      )
    : null;
  return {
    type: "FeatureCollection",
    features: trip.media
      .filter(
        (m) =>
          m.lat !== null &&
          m.lon !== null &&
          m.thumb_ref &&
          (!allowed || allowed.has(m.id)),
      )
      .map((m) => ({
        type: "Feature" as const,
        properties: {
          media_id: m.id,
          thumb: m.thumb_ref,
          time: m.captured_at ? m.captured_at.slice(11, 16) : "",
        },
        geometry: { type: "Point" as const, coordinates: [m.lon!, m.lat!] },
      })),
  };
}

function placesGeoJSON(trip: Trip, limitTo: Set<string> | null): GeoJSON.FeatureCollection {
  const byId = new Map(trip.media.map((m) => [m.id, m]));
  return {
    type: "FeatureCollection",
    features: trip.events
      .filter(
        (e) =>
          e.status === "active" &&
          e.place?.lat != null &&
          e.type !== "unknown" &&
          !["drive", "flight", "ferry"].includes(e.type) &&
          (!limitTo || limitTo.has(e.id)),
      )
      .map((e) => {
        const meta = TYPE_META[e.type];
        // The first suggested photograph doubles as a preview, so hovering a pin shows
        // what the place actually looked like.
        const preview = e.selected_media_ids
          .map((id) => byId.get(id))
          .find((m) => m?.thumb_ref);
        const seconds =
          (new Date(e.end).getTime() - new Date(e.start).getTime()) / 1000;
        return {
          type: "Feature" as const,
          properties: {
            event_id: e.id,
            name: e.place!.name,
            type_label: meta.label,
            icon: meta.icon,
            meta:
              e.media_ids.length > 0
                ? `${duration(seconds)} \u00b7 ${e.media_ids.length} photos`
                : duration(seconds),
            thumb: preview?.thumb_ref ?? undefined,
            colour: e.type === "overnight" ? "#a78bfa" : "#38bdf8",
            radius: e.type === "overnight" ? 7 : 5,
          },
          geometry: {
            type: "Point" as const,
            coordinates: [e.place!.lon!, e.place!.lat!],
          },
        };
      }),
  };
}

function highlightsGeoJSON(event: TripEvent | null): GeoJSON.FeatureCollection {
  if (!event || event.detail.kind !== "activity") return EMPTY;
  return {
    type: "FeatureCollection",
    features: event.detail.highlights.map((h) => ({
      type: "Feature" as const,
      properties: {
        label: h.ele_m ? `${h.name} \u00b7 ${Math.round(h.ele_m)} m` : h.name,
        kind: h.kind,
      },
      geometry: { type: "Point" as const, coordinates: [h.lon, h.lat] },
    })),
  };
}
