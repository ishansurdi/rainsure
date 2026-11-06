// Basemap style edits for India's official view: drop OpenFreeMap borders and disputed place labels (D32, D41, D63).
import type { StyleSpecification } from "maplibre-gl";
import { HIDDEN_PLACE_NAMES, HIDDEN_STYLE_LAYERS } from "./config";

type Layer = StyleSpecification["layers"][number];

/** Add a filter to OpenMapTiles place-label layers that drops HIDDEN_PLACE_NAMES (any of name, name:en, name:latin). */
export function hideDisputedNames(layer: Layer): Layer {
  if (layer.type !== "symbol" || (layer as { "source-layer"?: string })["source-layer"] !== "place") return layer;
  const names = ["literal", HIDDEN_PLACE_NAMES];
  const hidden = ["any", ...["name", "name:en", "name:latin"].map((k) => ["in", ["coalesce", ["get", k], ""], names])];
  const keep = ["!", hidden];
  const filter = (layer as { filter?: unknown }).filter;
  return { ...layer, filter: (filter ? ["all", filter, keep] : keep) as never };
}

/** The style with border layers removed and disputed place labels filtered out. */
export function indiaView(style: StyleSpecification): StyleSpecification {
  return { ...style, layers: style.layers.filter((l) => !HIDDEN_STYLE_LAYERS.includes(l.id)).map(hideDisputedNames) };
}
