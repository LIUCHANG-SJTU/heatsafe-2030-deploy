import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map, MapLayerMouseEvent } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { DemoGridCollection, MetricKey } from "../api/types";
import { fillColorExpression } from "../lib/mapStyles";
import { useI18n } from "../i18n/useI18n";
import { formatGridLabel, formatPopulation } from "../lib/format";
import "maplibre-gl/dist/maplibre-gl.css";
import "../styles/map-tooltip.css";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

type Props = { grids: DemoGridCollection; metric: MetricKey; selectedId: string | null; agentHighlightIds?: string[]; onSelect: (id: string) => void };

export function MapView({ grids, metric, selectedId, agentHighlightIds = [], onSelect }: Props) {
  const { locale, t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const onSelectRef = useRef(onSelect); onSelectRef.current = onSelect;
  const selectedRef = useRef(selectedId); selectedRef.current = selectedId;
  const localeRef = useRef(locale); localeRef.current = locale;
  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: ref.current, style: { version: 8, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe6eb" } }] }, attributionControl: false });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      map.addSource("demo-grids", { type: "geojson", data: grids });
      map.addLayer({ id: "risk-grid-fill", type: "fill", source: "demo-grids", paint: { "fill-color": fillColorExpression("risk_score") as any, "fill-opacity": 0.88 } });
      map.addLayer({ id: "grid-outline", type: "line", source: "demo-grids", paint: { "line-color": "#ffffff", "line-width": 0.45, "line-opacity": 0.75 } });
      map.addLayer({ id: "selected-grid-outline", type: "line", source: "demo-grids", filter: ["==", ["get", "grid_id"], ""], paint: { "line-color": "#102039", "line-width": 3 } });
      map.addLayer({ id: "agent-highlight-outline", type: "line", source: "demo-grids", filter: ["==", ["get", "grid_id"], ""], paint: { "line-color": "#16a6b6", "line-width": 2.2, "line-dasharray": [2, 1] } });
      map.setFilter("selected-grid-outline", ["==", ["get", "grid_id"], selectedRef.current || ""]);
      map.on("click", "risk-grid-fill", (event: MapLayerMouseEvent) => { const feature = event.features?.[0]; const id = feature?.properties?.grid_id; if (id) onSelectRef.current(String(id)); });
      map.on("mouseenter", "risk-grid-fill", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mousemove", "risk-grid-fill", (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        if (!feature) return;
        document.querySelectorAll(".maplibregl-popup").forEach((popup) => popup.remove());
        const properties = feature.properties || {};
        const risk = properties.risk_score == null ? "N/A" : Number(properties.risk_score).toFixed(1);
        const content = document.createElement("div");
        content.className = "map-tooltip";
        const currentLocale = localeRef.current;
        const title = document.createElement("b");
        const fullGridId = String(properties.grid_id || "");
        title.textContent = formatGridLabel(fullGridId, currentLocale);
        title.title = fullGridId;
        const metrics = document.createElement("span");
        metrics.textContent = `${currentLocale === "zh-CN" ? "风险" : "Risk"} ${risk} · ${currentLocale === "zh-CN" ? "人口" : "Population"} ${properties.population_total == null ? "—" : formatPopulation(Number(properties.population_total), currentLocale)}`;
        const status = document.createElement("span");
        status.textContent = properties.analysis_status === "NON_URBAN_WATER" ? (currentLocale === "zh-CN" ? "水域格网 · 不评分" : "Water Grid · Not Scored") : (currentLocale === "zh-CN" ? "有效陆地格网" : "Valid Land Grid");
        content.append(title, metrics, status);
        new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 }).setLngLat(event.lngLat).setDOMContent(content).addTo(map);
      });
      map.on("mouseleave", "risk-grid-fill", () => { map.getCanvas().style.cursor = ""; document.querySelectorAll(".maplibregl-popup").forEach((popup) => popup.remove()); });
      const bounds = new maplibregl.LngLatBounds();
      grids.features.forEach((feature) => feature.geometry.coordinates[0].forEach(([lng, lat]) => bounds.extend([lng, lat])));
      map.fitBounds(bounds, { padding: 30, duration: 0 });
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, [grids]);
  useEffect(() => {
    const map = mapRef.current; if (!map || !map.isStyleLoaded()) return;
    if (map.getLayer("risk-grid-fill")) map.setPaintProperty("risk-grid-fill", "fill-color", fillColorExpression(metric) as any);
  }, [metric]);
  useEffect(() => {
    const map = mapRef.current; if (!map || !map.isStyleLoaded() || !map.getLayer("selected-grid-outline")) return;
    map.setFilter("selected-grid-outline", ["==", ["get", "grid_id"], selectedId || ""]);
  }, [selectedId]);
  useEffect(() => {
    const map = mapRef.current; if (!map || !map.isStyleLoaded() || !map.getLayer("agent-highlight-outline")) return;
    map.setFilter("agent-highlight-outline", agentHighlightIds.length ? ["in", ["get", "grid_id"], ["literal", agentHighlightIds]] : ["==", ["get", "grid_id"], ""]);
  }, [agentHighlightIds]);
  useEffect(() => {
    if (!ref.current) return;
    const labels = locale === "zh-CN" ? ["放大地图", "缩小地图"] : ["Zoom in", "Zoom out"];
    ref.current.querySelectorAll<HTMLButtonElement>(".maplibregl-ctrl-zoom-in, .maplibregl-ctrl-zoom-out").forEach((button, index) => {
      button.setAttribute("aria-label", labels[index]);
      button.title = labels[index];
    });
  }, [locale]);
  return <div ref={ref} className="map-canvas" aria-label={t("map.aria")} />;
}
