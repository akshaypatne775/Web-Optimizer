import os
from pathlib import Path
from typing import Dict, List

from colorama import Fore, Style, init
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS


APP_HOST = "127.0.0.1"
APP_PORT = 5000
OUTPUT_DIR = Path.cwd() / "survey_outputs"


def ensure_output_directory() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def posix_relative(path: Path) -> str:
    return path.relative_to(OUTPUT_DIR).as_posix()


def detect_datasets() -> Dict[str, List[Dict[str, str]]]:
    cogs: List[Dict[str, str]] = []
    tilesets: List[Dict[str, str]] = []

    for tif_path in OUTPUT_DIR.rglob("*"):
        if tif_path.is_file() and tif_path.suffix.lower() in {".tif", ".tiff"}:
            rel_path = posix_relative(tif_path)
            cogs.append(
                {
                    "name": tif_path.name,
                    "path": rel_path,
                    "url": f"/outputs/{rel_path}",
                    "size_bytes": tif_path.stat().st_size,
                    "type": "cog",
                }
            )

    for tileset_json in OUTPUT_DIR.rglob("tileset.json"):
        if tileset_json.is_file():
            folder = tileset_json.parent
            rel_folder = posix_relative(folder)
            rel_tileset = posix_relative(tileset_json)
            display_name = rel_folder if rel_folder else folder.name
            tilesets.append(
                {
                    "name": display_name,
                    "path": rel_folder,
                    "tileset_url": f"/outputs/{rel_tileset}",
                    "type": "3dtiles",
                }
            )

    cogs.sort(key=lambda d: d["path"].lower())
    tilesets.sort(key=lambda d: d["path"].lower())
    return {"cogs": cogs, "tilesets": tilesets}


app = Flask(__name__)
CORS(app)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Droid Survair - Local Survey Viewer</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="" />
  <link rel="stylesheet" href="https://cesium.com/downloads/cesiumjs/releases/1.119/Build/Cesium/Widgets/widgets.css" />
  <style>
    :root {
      --bg: #0e3e49;
      --bg-panel: #152a31;
      --bg-card: #1e363f;
      --text: #e8f3f7;
      --muted: #97b5be;
      --cyan: #00e5ff;
      --yellow: #ffe45e;
      --border: #2d4b54;
    }

    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text); font-family: "Segoe UI", Tahoma, sans-serif; }

    .app {
      display: grid;
      grid-template-columns: 340px 1fr;
      height: 100vh;
      width: 100%;
    }

    .sidebar {
      background: linear-gradient(180deg, #0f2f38 0%, var(--bg-panel) 100%);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      min-width: 280px;
    }

    .sidebar-header {
      padding: 16px 18px;
      border-bottom: 1px solid var(--border);
    }

    .brand {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0.4px;
      color: var(--cyan);
      font-weight: 700;
    }

    .subtitle {
      margin: 6px 0 0;
      font-size: 12px;
      color: var(--muted);
    }

    .dataset-groups {
      padding: 12px;
      overflow: auto;
      flex: 1;
    }

    .group-title {
      margin: 14px 0 8px;
      font-size: 12px;
      color: var(--yellow);
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .dataset-btn {
      width: 100%;
      text-align: left;
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 10px;
      padding: 10px 12px;
      margin-bottom: 8px;
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.2s ease, box-shadow 0.2s ease;
      font-size: 13px;
      word-break: break-word;
    }

    .dataset-btn:hover {
      transform: translateY(-1px);
      border-color: var(--cyan);
      box-shadow: 0 0 0 1px rgba(0, 229, 255, 0.2);
    }

    .dataset-btn.active {
      border-color: var(--yellow);
      box-shadow: 0 0 0 1px rgba(255, 228, 94, 0.3);
    }

    .viewer-wrap {
      position: relative;
      height: 100%;
      width: 100%;
    }

    #map, #cesiumContainer {
      position: absolute;
      inset: 0;
      display: none;
    }

    #map.active, #cesiumContainer.active {
      display: block;
    }

    .empty-state {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 18px;
      color: var(--muted);
      font-size: 15px;
      background: radial-gradient(circle at center, rgba(0, 229, 255, 0.08), transparent 55%);
    }

    .status {
      border-top: 1px solid var(--border);
      padding: 10px 14px;
      font-size: 12px;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h1 class="brand">Droid Survair - Master Suite</h1>
        <p class="subtitle">Local Survey Viewer</p>
      </div>
      <div id="datasetGroups" class="dataset-groups"></div>
      <div id="status" class="status">Ready. Select a dataset to visualize.</div>
    </aside>

    <main class="viewer-wrap">
      <div id="map"></div>
      <div id="cesiumContainer"></div>
      <div id="emptyState" class="empty-state">
        Place optimized outputs in <strong style="margin:0 4px;">./survey_outputs</strong> and select a dataset from the left panel.
      </div>
    </main>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
  <script src="https://unpkg.com/proj4@2.11.0/dist/proj4.js"></script>
  <script src="https://unpkg.com/proj4leaflet@1.0.2/src/proj4leaflet.js"></script>
  <script src="https://unpkg.com/georaster"></script>
  <script src="https://unpkg.com/georaster-layer-for-leaflet"></script>
  <script src="https://cesium.com/downloads/cesiumjs/releases/1.119/Build/Cesium/Cesium.js"></script>
  <script>
    const statusEl = document.getElementById("status");
    const datasetGroupsEl = document.getElementById("datasetGroups");
    const emptyStateEl = document.getElementById("emptyState");
    const mapEl = document.getElementById("map");
    const cesiumEl = document.getElementById("cesiumContainer");

    let leafletMap = null;
    let georasterLayer = null;
    let cesiumViewer = null;
    let activeTileset = null;
    let activeButton = null;

    function formatBytes(bytes) {
      if (typeof bytes !== "number" || Number.isNaN(bytes)) return "unknown size";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let size = bytes;
      let idx = 0;
      while (size >= 1024 && idx < units.length - 1) {
        size /= 1024;
        idx += 1;
      }
      return size.toFixed(idx === 0 ? 0 : 2) + " " + units[idx];
    }

    function setStatus(message) {
      statusEl.textContent = message;
    }

    function setActiveButton(btn) {
      if (activeButton) activeButton.classList.remove("active");
      activeButton = btn;
      if (activeButton) activeButton.classList.add("active");
    }

    function ensureLeafletMap() {
      if (!leafletMap) {
        leafletMap = L.map("map", { zoomControl: true, preferCanvas: true }).setView([0, 0], 2);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap contributors"
        }).addTo(leafletMap);
      }
      return leafletMap;
    }

    function ensureCesiumViewer() {
      if (!cesiumViewer) {
        Cesium.Ion.defaultAccessToken = "";
        cesiumViewer = new Cesium.Viewer("cesiumContainer", {
          animation: false,
          timeline: false,
          geocoder: false,
          baseLayerPicker: false,
          homeButton: true,
          sceneModePicker: true,
          navigationHelpButton: false,
          fullscreenButton: true,
          infoBox: true,
          selectionIndicator: true,
          shadows: false,
          shouldAnimate: true
        });
        cesiumViewer.imageryLayers.removeAll();
      }
      return cesiumViewer;
    }

    function showLeaflet() {
      mapEl.classList.add("active");
      cesiumEl.classList.remove("active");
      emptyStateEl.style.display = "none";
      setTimeout(() => leafletMap && leafletMap.invalidateSize(), 60);
    }

    function showCesium() {
      cesiumEl.classList.add("active");
      mapEl.classList.remove("active");
      emptyStateEl.style.display = "none";
      setTimeout(() => cesiumViewer && cesiumViewer.resize(), 60);
    }

    function clearViewers() {
      if (georasterLayer && leafletMap) {
        leafletMap.removeLayer(georasterLayer);
        georasterLayer = null;
      }
      if (activeTileset && cesiumViewer) {
        cesiumViewer.scene.primitives.remove(activeTileset);
        activeTileset = null;
      }
    }

    async function forceZoomToRaster(map, layer, georaster) {
      const maxAttempts = 20;
      const delayMs = 120;

      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        map.invalidateSize();
        const layerBounds = layer && layer.getBounds ? layer.getBounds() : null;
        if (layerBounds && layerBounds.isValid && layerBounds.isValid()) {
          map.flyToBounds(layerBounds, { padding: [20, 20], duration: 0.9, maxZoom: 19 });
          return true;
        }
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }

      if (
        typeof georaster.ymin === "number" &&
        typeof georaster.xmin === "number" &&
        typeof georaster.ymax === "number" &&
        typeof georaster.xmax === "number"
      ) {
        const fallbackBounds = L.latLngBounds(
          [georaster.ymin, georaster.xmin],
          [georaster.ymax, georaster.xmax]
        );
        if (fallbackBounds.isValid && fallbackBounds.isValid()) {
          map.flyToBounds(fallbackBounds, { padding: [20, 20], duration: 0.9, maxZoom: 19 });
          return true;
        }
      }

      return false;
    }

    async function loadCOG(url, sizeBytes) {
      setStatus("Loading COG raster...");
      const map = ensureLeafletMap();
      showLeaflet();
      clearViewers();

      if (typeof sizeBytes === "number" && sizeBytes > 700 * 1024 * 1024) {
        setStatus("Large TIFF detected (" + formatBytes(sizeBytes) + "). Loading may take time or fail in browser memory.");
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error("Failed to fetch TIFF (" + response.status + ")");
      }
      const arrayBuffer = await response.arrayBuffer();
      const georaster = await parseGeoraster(arrayBuffer);

      georasterLayer = new GeoRasterLayer({
        georaster: georaster,
        resolution: 256
      });
      georasterLayer.addTo(map);
      const zoomed = await forceZoomToRaster(map, georasterLayer, georaster);
      if (zoomed) {
        setStatus("COG loaded successfully (auto-zoom applied).");
      } else {
        setStatus("COG loaded, but auto-zoom unavailable. TIFF may be missing valid georeference bounds/CRS.");
      }
    }

    async function load3DTiles(tilesetUrl) {
      setStatus("Loading Cesium 3D Tiles...");
      const viewer = ensureCesiumViewer();
      showCesium();
      clearViewers();

      activeTileset = await Cesium.Cesium3DTileset.fromUrl(tilesetUrl);
      viewer.scene.primitives.add(activeTileset);
      await viewer.zoomTo(activeTileset);
      setStatus("3D Tiles loaded successfully.");
    }

    function createDatasetButton(label, onClick) {
      const btn = document.createElement("button");
      btn.className = "dataset-btn";
      btn.textContent = label;
      btn.addEventListener("click", () => {
        setActiveButton(btn);
        onClick();
      });
      return btn;
    }

    function renderGroup(title, items, itemToButton) {
      const heading = document.createElement("h2");
      heading.className = "group-title";
      heading.textContent = title;
      datasetGroupsEl.appendChild(heading);

      if (!items.length) {
        const placeholder = document.createElement("div");
        placeholder.className = "status";
        placeholder.style.border = "1px dashed var(--border)";
        placeholder.style.borderRadius = "10px";
        placeholder.style.marginBottom = "8px";
        placeholder.textContent = "No datasets found.";
        datasetGroupsEl.appendChild(placeholder);
        return;
      }

      items.forEach((item) => datasetGroupsEl.appendChild(itemToButton(item)));
    }

    async function fetchDatasets() {
      datasetGroupsEl.innerHTML = "";
      setStatus("Scanning ./survey_outputs ...");

      const response = await fetch("/api/datasets");
      if (!response.ok) {
        throw new Error("Failed to fetch dataset list.");
      }
      const data = await response.json();

      renderGroup("Cloud Optimized GeoTIFF", data.cogs, (item) =>
        createDatasetButton(item.path + " (" + formatBytes(item.size_bytes) + ")", async () => {
          try {
            await loadCOG(item.url, item.size_bytes);
          } catch (error) {
            setStatus("Failed to load COG: " + error.message);
          }
        })
      );

      renderGroup("Cesium 3D Tiles", data.tilesets, (item) =>
        createDatasetButton(item.path, async () => {
          try {
            await load3DTiles(item.tileset_url);
          } catch (error) {
            setStatus("Failed to load 3D Tiles: " + error.message);
          }
        })
      );

      setStatus("Scan complete. Found " + data.cogs.length + " COG(s) and " + data.tilesets.length + " 3D Tileset(s).");
    }

    fetchDatasets().catch((error) => {
      setStatus("Error: " + error.message);
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/api/datasets")
def list_datasets():
    ensure_output_directory()
    return jsonify(detect_datasets())


@app.route("/outputs/<path:subpath>")
def serve_outputs(subpath: str):
    ensure_output_directory()
    return send_from_directory(OUTPUT_DIR, subpath)


def print_startup_banner() -> None:
    init(autoreset=True)
    line = "=" * 70
    print(Fore.CYAN + line)
    print(Fore.CYAN + Style.BRIGHT + "   Droid Survair - Master Suite | Local Survey Viewer")
    print(Fore.CYAN + line)
    print()
    print(Fore.YELLOW + "Output folder:")
    print(Fore.WHITE + f"  {OUTPUT_DIR}")
    print(Fore.YELLOW + "Place your optimized datasets in this folder:")
    print(Fore.WHITE + "  - Cloud Optimized GeoTIFFs (*.tif, *.tiff)")
    print(Fore.WHITE + "  - Cesium 3D Tiles folders (must contain tileset.json)")
    print()
    print(Fore.GREEN + Style.BRIGHT + f"Open viewer: http://{APP_HOST}:{APP_PORT}")
    print()


if __name__ == "__main__":
    ensure_output_directory()
    print_startup_banner()
    app.run(host=APP_HOST, port=APP_PORT, debug=False)
