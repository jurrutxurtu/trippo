import type { StyleSpecification } from "maplibre-gl";

/**
 * Tile styles. ADR-0006: MapLibre with swappable sources, chosen so viewing a trip never
 * incurs map billing.
 *
 * The key is read from the backend at runtime rather than baked in at build time, so a
 * capsule exported for someone else does not carry a personal quota with it.
 */

const OSM_RASTER: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

/**
 * Esri World Imagery, free for personal use with attribution, plus a transparent label
 * layer on top. This is the trick behind a Google-Hybrid look: imagery underneath, vector
 * labels above, nothing in between.
 */
const SATELLITE_RASTER: StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery &copy; Esri",
    },
  },
  layers: [{ id: "imagery", type: "raster", source: "imagery" }],
};

export type StyleName = "street" | "satellite";

export function styleFor(name: StyleName, maptilerKey: string): string | StyleSpecification {
  if (maptilerKey) {
    return name === "street"
      ? `https://api.maptiler.com/maps/streets-v2/style.json?key=${maptilerKey}`
      : `https://api.maptiler.com/maps/hybrid/style.json?key=${maptilerKey}`;
  }
  // No key: fall back to raster tiles. Uglier, unrestylable, but the app still works.
  return name === "street" ? OSM_RASTER : SATELLITE_RASTER;
}

/** Data colours, matching the tokens in index.css. Never the indigo UI accent. */
export const MAP_COLOURS = {
  track: "#0f9d76",
  ferry: "#22b8d4",
  drive: "#71717a",
  walk: "#2dd4bf",
  gap: "#f0a11e",
  selected: "#6366f1",
  photo: "#6366f1",
} as const;

export function colourFor(kind: string): string {
  switch (kind) {
    case "hike":
    case "bike":
      return MAP_COLOURS.track;
    case "walk":
      return MAP_COLOURS.walk;
    case "ferry":
      return MAP_COLOURS.ferry;
    case "flight":
      return MAP_COLOURS.ferry;
    case "unknown":
      return MAP_COLOURS.gap;
    default:
      return MAP_COLOURS.drive;
  }
}
