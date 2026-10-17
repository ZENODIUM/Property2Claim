"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Cartesian2,
  Cartesian3,
  Color,
  Credit,
  DistanceDisplayCondition,
  Entity,
  HorizontalOrigin,
  LabelStyle,
  Math as CesiumMath,
  NearFarScalar,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  VerticalOrigin,
  Viewer,
} from "cesium";
import { Crosshair, Globe2, Layers3, Map as MapIcon, Minus, Pause, Play, Plus, RotateCcw, Satellite } from "lucide-react";
import type { Geometry } from "geojson";
import type { Company, Hazard, Property } from "@/lib/types";

type GlobeStatus = "ready" | "degraded" | "error";
type ViewMode = "globe" | "map";

const HOME = { longitude: -96, latitude: 38, height: 7_600_000 };

function imageryDate() {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - 2);
  return date.toISOString().slice(0, 10);
}

const COMPANY_COLORS = ["#38bdf8", "#a78bfa", "#2dd4bf", "#f472b6", "#fb923c", "#a3e635", "#facc15", "#818cf8"];

function companyColor(companyId: number) {
  return Color.fromCssColorString(COMPANY_COLORS[(companyId - 1) % COMPANY_COLORS.length]);
}

function attentionColor(score: number) {
  return score >= 70 ? Color.fromCssColorString("#fb7185") : Color.fromCssColorString("#fbbf24");
}

function hazardColor(severity: string) {
  return /high|severe|extreme|critical/i.test(severity)
    ? Color.fromCssColorString("#fb7185")
    : Color.fromCssColorString("#f59e0b");
}

function polygonRings(geometry: Geometry): number[][][] {
  if (geometry.type === "Polygon") return [geometry.coordinates[0]];
  if (geometry.type === "MultiPolygon") return geometry.coordinates.map((polygon) => polygon[0]);
  return [];
}

function GlobeButton({ label, onClick, children, active = false }: { label: string; onClick: () => void; children: React.ReactNode; active?: boolean }) {
  return <button type="button" aria-label={label} title={label} onClick={onClick} className={`grid size-9 place-items-center rounded-md border text-slate-300 shadow-sm transition hover:border-blue-400/50 hover:bg-blue-400/10 hover:text-blue-200 ${active ? "border-blue-400/50 bg-blue-400/15 text-blue-200" : "border-white/15 bg-[#161d27]/95"}`}>{children}</button>;
}

export function PortfolioMap({ properties, hazards, companies, onSelect }: { properties: Property[]; hazards: Hazard[]; companies: Company[]; onSelect: (property: Property) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const selectRef = useRef(onSelect);
  const propertyEntities = useRef(new Map<string, Property>());
  const autoRotateRef = useRef(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const [showHazards, setShowHazards] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>("globe");
  const [status, setStatus] = useState<GlobeStatus>("ready");
  const date = useMemo(() => imageryDate(), []);

  useEffect(() => { selectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { autoRotateRef.current = autoRotate; }, [autoRotate]);

  const flyHome = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    if (viewMode === "map") {
      viewer.camera.flyTo({ destination: Rectangle.fromDegrees(-127, 22, -65, 52), duration: 1.1 });
      return;
    }
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(HOME.longitude, HOME.latitude, HOME.height),
      orientation: { heading: 0, pitch: CesiumMath.toRadians(-89), roll: 0 },
      duration: 1.4,
    });
  }, [viewMode]);

  const switchView = useCallback((mode: ViewMode) => {
    const viewer = viewerRef.current;
    if (!viewer || mode === viewMode) return;
    setAutoRotate(false);
    setViewMode(mode);
    const removeListener = viewer.scene.morphComplete.addEventListener(() => {
      removeListener();
      if (mode === "map") viewer.camera.flyTo({ destination: Rectangle.fromDegrees(-127, 22, -65, 52), duration: 0.9 });
      else viewer.camera.flyTo({ destination: Cartesian3.fromDegrees(HOME.longitude, HOME.latitude, HOME.height), orientation: { heading: 0, pitch: CesiumMath.toRadians(-89), roll: 0 }, duration: 0.9 });
    });
    if (mode === "map") viewer.scene.morphTo2D(0.65);
    else viewer.scene.morphTo3D(0.65);
  }, [viewMode]);

  const zoom = useCallback((direction: "in" | "out") => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const distance = Math.max(viewer.camera.positionCartographic.height * 0.35, 30_000);
    if (direction === "in") viewer.camera.zoomIn(distance);
    else viewer.camera.zoomOut(distance);
    viewer.scene.requestRender();
  }, []);

  useEffect(() => {
    if (!container.current || viewerRef.current) return;
    (window as typeof window & { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = "/cesium/";

    let viewer: Viewer | undefined;
    let handler: ScreenSpaceEventHandler | undefined;
    try {
      viewer = new Viewer(container.current, {
        animation: false,
        baseLayer: false,
        baseLayerPicker: false,
        fullscreenButton: false,
        geocoder: false,
        homeButton: false,
        infoBox: false,
        navigationHelpButton: false,
        sceneModePicker: false,
        selectionIndicator: false,
        timeline: false,
        useBrowserRecommendedResolution: false,
        requestRenderMode: true,
        maximumRenderTimeChange: Number.POSITIVE_INFINITY,
      });
      viewerRef.current = viewer;

      const nasaFallback = new UrlTemplateImageryProvider({
        url: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
        maximumLevel: 9,
        credit: new Credit("NASA EOSDIS GIBS · VIIRS true color", true),
      });
      const fallbackLayer = viewer.imageryLayers.addImageryProvider(nasaFallback);
      fallbackLayer.show = false;

      const imagery = new UrlTemplateImageryProvider({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maximumLevel: 20,
        credit: new Credit("Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community", true),
      });
      const imageryLayer = viewer.imageryLayers.addImageryProvider(imagery);
      let imageryErrors = 0;
      imagery.errorEvent.addEventListener(() => {
        imageryErrors += 1;
        if (imageryErrors < 3) return;
        setStatus("degraded");
        imageryLayer.show = false;
        fallbackLayer.show = true;
        viewer?.scene.requestRender();
      });

      const scene = viewer.scene;
      scene.backgroundColor = Color.fromCssColorString("#101722");
      scene.globe.baseColor = Color.fromCssColorString("#172132");
      scene.globe.showGroundAtmosphere = true;
      scene.globe.enableLighting = true;
      // Balanced presentation profile: readable satellite detail without
      // aggressively pulling maximum-resolution tiles during navigation.
      scene.globe.maximumScreenSpaceError = 2.2;
      scene.globe.tileCacheSize = 110;
      scene.globe.preloadAncestors = true;
      scene.globe.preloadSiblings = false;
      if (scene.skyBox) scene.skyBox.show = true;
      scene.screenSpaceCameraController.minimumZoomDistance = 800;
      scene.screenSpaceCameraController.maximumZoomDistance = 24_000_000;
      scene.screenSpaceCameraController.enableCollisionDetection = true;
      viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.1);

      viewer.camera.setView({
        destination: Cartesian3.fromDegrees(HOME.longitude, HOME.latitude, HOME.height),
        orientation: { heading: 0, pitch: CesiumMath.toRadians(-89), roll: 0 },
      });

      handler = new ScreenSpaceEventHandler(scene.canvas);
      handler.setInputAction((movement: { position: Cartesian2 }) => {
        const picked = scene.pick(movement.position) as { id?: Entity } | undefined;
        const entityId = picked?.id?.id;
        const property = entityId ? propertyEntities.current.get(entityId) : undefined;
        if (!property) return;
        selectRef.current(property);
        viewer?.camera.flyTo({
          destination: Cartesian3.fromDegrees(property.longitude, property.latitude, 180_000),
          orientation: { heading: 0, pitch: CesiumMath.toRadians(-68), roll: 0 },
          duration: 1.1,
        });
      }, ScreenSpaceEventType.LEFT_CLICK);

      const stopRotation = () => setAutoRotate(false);
      scene.canvas.addEventListener("pointerdown", stopRotation);
      const removeTick = viewer.clock.onTick.addEventListener(() => {
        if (autoRotateRef.current) {
          viewer?.camera.rotate(Cartesian3.UNIT_Z, -0.00022);
          viewer?.scene.requestRender();
        }
      });
      return () => {
        removeTick();
        scene.canvas.removeEventListener("pointerdown", stopRotation);
        handler?.destroy();
        viewer?.destroy();
        viewerRef.current = null;
      };
    } catch {
      queueMicrotask(() => setStatus("error"));
      viewer?.destroy();
      viewerRef.current = null;
    }
  }, [date]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.entities.removeAll();
    propertyEntities.current.clear();
    const companyNames = new Map(companies.map((company) => [company.id, company.name]));
    const affected = new Set(hazards.flatMap((hazard) => hazard.matches.map((match) => match.property_id)));

    properties.forEach((property) => {
      const color = companyColor(property.company_id);
      const needsAttention = property.risk_score >= 45;
      const alertColor = attentionColor(property.risk_score);
      const highlighted = affected.has(property.id);
      const id = `property-${property.id}`;
      propertyEntities.current.set(id, property);
      if (needsAttention || highlighted) {
        const haloId = `${id}-attention`;
        propertyEntities.current.set(haloId, property);
        viewer.entities.add({
          id: haloId,
          position: Cartesian3.fromDegrees(property.longitude, property.latitude, 115),
          point: {
            color: (highlighted ? Color.fromCssColorString("#fb7185") : alertColor).withAlpha(.22),
            pixelSize: highlighted ? 42 : property.risk_score >= 70 ? 36 : 31,
            outlineColor: (highlighted ? Color.fromCssColorString("#fb7185") : alertColor).withAlpha(.38),
            outlineWidth: 8,
            scaleByDistance: new NearFarScalar(100_000, 1.2, 12_000_000, .65),
          },
        });
      }
      viewer.entities.add({
        id,
        name: property.name,
        position: Cartesian3.fromDegrees(property.longitude, property.latitude, 120),
        point: {
          color,
          pixelSize: highlighted ? 16 : 12,
          outlineColor: Color.fromCssColorString("#f8fafc"),
          outlineWidth: highlighted ? 3 : 2,
          scaleByDistance: new NearFarScalar(100_000, 1.25, 12_000_000, 0.7),
        },
        ellipse: needsAttention || highlighted ? {
          semiMajorAxis: highlighted ? 64_000 : property.risk_score >= 70 ? 50_000 : 39_000,
          semiMinorAxis: highlighted ? 64_000 : property.risk_score >= 70 ? 50_000 : 39_000,
          material: (highlighted ? Color.fromCssColorString("#fb7185") : alertColor).withAlpha(highlighted ? 0.18 : 0.12),
          outline: true,
          outlineColor: (highlighted ? Color.fromCssColorString("#fb7185") : alertColor).withAlpha(.9),
          height: 20,
        } : undefined,
        label: {
          text: `${property.name}\n${companyNames.get(property.company_id) ?? "Synthetic insured"}`,
          font: "700 13px Inter, Arial, sans-serif",
          style: LabelStyle.FILL_AND_OUTLINE,
          fillColor: Color.fromCssColorString("#111827"),
          outlineColor: Color.fromCssColorString("#f8fafc"),
          outlineWidth: 2,
          showBackground: true,
          backgroundColor: Color.fromCssColorString("#f8fafc").withAlpha(0.94),
          backgroundPadding: new Cartesian2(9, 7),
          pixelOffset: new Cartesian2(0, -24),
          verticalOrigin: VerticalOrigin.BOTTOM,
          horizontalOrigin: HorizontalOrigin.CENTER,
          distanceDisplayCondition: new DistanceDisplayCondition(0, 2_800_000),
        },
      });
    });

    if (showHazards) {
      hazards.forEach((hazard) => {
        const color = hazardColor(hazard.severity);
        polygonRings(hazard.geometry).forEach((ring, index) => {
          const degrees = ring.flatMap(([longitude, latitude]) => [longitude, latitude]);
          if (degrees.length < 6) return;
          viewer.entities.add({
            id: `hazard-${hazard.id}-${index}`,
            name: hazard.title,
            polygon: {
              hierarchy: Cartesian3.fromDegreesArray(degrees),
              material: color.withAlpha(0.2),
              outline: true,
              outlineColor: color.withAlpha(0.9),
              height: 70,
            },
          });
        });
        if (hazard.geometry.type === "Point") {
          const [longitude, latitude] = hazard.geometry.coordinates;
          viewer.entities.add({
            id: `hazard-${hazard.id}`,
            name: hazard.title,
            position: Cartesian3.fromDegrees(longitude, latitude, 60),
            ellipse: { semiMajorAxis: 120_000, semiMinorAxis: 120_000, material: color.withAlpha(0.22), outline: true, outlineColor: color },
          });
        }
      });
    }
    viewer.scene.requestRender();
  }, [companies, hazards, properties, showHazards, status]);

  return <div className="relative h-[clamp(520px,72vh,780px)] w-full overflow-hidden bg-[#101722]" aria-label="Interactive geographic portfolio viewer">
    <div ref={container} className="absolute inset-0" />

    <div className="absolute left-4 top-4 z-20 flex max-w-[calc(100%-11rem)] items-center gap-2 rounded-md border border-white/15 bg-[#161d27]/95 px-3 py-2 text-[11px] text-slate-300 shadow-md sm:left-5 sm:top-5">
      <Satellite size={15} className="shrink-0 text-blue-300" />
      <div className="min-w-0"><div className="truncate font-semibold text-slate-100">Balanced satellite detail</div><div className="truncate text-[10px] text-slate-400">Esri imagery · NASA fallback</div></div>
      <span className={`ml-1 size-2 shrink-0 rounded-full ${status === "ready" ? "bg-emerald-400" : "bg-amber-400"}`} />
    </div>

    <div className="absolute right-4 top-4 z-20 flex overflow-hidden rounded-md border border-white/15 bg-[#161d27]/95 p-0.5 text-[11px] shadow-md sm:right-5 sm:top-5">
      <button type="button" onClick={() => switchView("globe")} className={`flex h-8 items-center gap-1.5 rounded px-2.5 font-medium transition ${viewMode === "globe" ? "bg-blue-500 text-white" : "text-slate-400 hover:text-slate-100"}`}><Globe2 size={14} />Globe</button>
      <button type="button" onClick={() => switchView("map")} className={`flex h-8 items-center gap-1.5 rounded px-2.5 font-medium transition ${viewMode === "map" ? "bg-blue-500 text-white" : "text-slate-400 hover:text-slate-100"}`}><MapIcon size={14} />Map</button>
    </div>

    <div className="absolute right-4 top-16 z-20 flex flex-col gap-2 sm:right-5 sm:top-[4.25rem]">
      <GlobeButton label="Zoom in" onClick={() => zoom("in")}><Plus size={16} /></GlobeButton>
      <GlobeButton label="Zoom out" onClick={() => zoom("out")}><Minus size={16} /></GlobeButton>
      <GlobeButton label="Reset view" onClick={flyHome}><RotateCcw size={15} /></GlobeButton>
      {viewMode === "globe" && <GlobeButton label={autoRotate ? "Pause globe rotation" : "Rotate globe"} active={autoRotate} onClick={() => setAutoRotate((value) => !value)}>{autoRotate ? <Pause size={14} /> : <Play size={14} />}</GlobeButton>}
      <GlobeButton label={showHazards ? "Hide hazard overlays" : "Show hazard overlays"} active={showHazards} onClick={() => setShowHazards((value) => !value)}><Layers3 size={15} /></GlobeButton>
    </div>

    <div className="absolute bottom-5 right-5 z-20 hidden items-center gap-2 rounded-md border border-white/15 bg-[#161d27]/95 px-3 py-2 text-[10px] text-slate-300 shadow-md sm:flex"><Crosshair size={13} className="text-blue-300" />{viewMode === "globe" ? "Drag to rotate" : "Drag to pan"} · scroll to zoom · click a site</div>
    {status === "error" && <div className="absolute inset-0 z-30 grid place-items-center bg-[#101722]/95 p-8 text-center"><div><div className="text-sm font-semibold text-rose-300">Geographic viewer unavailable</div><p className="mt-2 max-w-sm text-xs leading-5 text-slate-400">WebGL could not initialize in this browser. Property and hazard data remain available in the surrounding dashboard.</p></div></div>}
  </div>;
}
