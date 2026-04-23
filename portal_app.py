from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict

from flask import Flask, jsonify, render_template_string, request
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
SURVEY_OUTPUTS_DIR = BASE_DIR / "survey_outputs"
VENV_PYTHON = BASE_DIR / "venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
ALLOWED_EXTENSIONS = {".tif", ".tiff"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10 GB

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SURVEY_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

jobs: Dict[str, Dict[str, str]] = {}
processes: Dict[str, subprocess.Popen] = {}


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Droid Survair Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" />
  <style>
    :root {
      --bg: #0e3e49;
      --panel: #133845;
      --panel-2: #174553;
      --text: #eaf6f8;
      --muted: #b9d4db;
      --accent-cyan: #00e5ff;
      --accent-yellow: #ffe45e;
      --border: #2f6271;
      --ok: #5bf59e;
      --warn: #ffd166;
      --err: #ff6b6b;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at 20% 20%, #124b58 0%, var(--bg) 48%, #0a2f37 100%);
      color: var(--text);
      font-family: "Montserrat", sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }

    .fa, .fas, .far, .fal, .fab, [class^="fa-"], [class*=" fa-"] {
      font-weight: 900 !important;
    }

    .portal {
      width: min(980px, 100%);
      background: linear-gradient(180deg, var(--panel) 0%, #102f39 100%);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
      overflow: hidden;
    }

    .header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      background: rgba(0, 0, 0, 0.12);
    }

    .title { margin: 0; font-size: 22px; color: var(--accent-cyan); font-weight: 700; }
    .subtitle { margin: 6px 0 0; font-size: 13px; color: var(--muted); }

    .viewer-link {
      color: var(--accent-yellow);
      text-decoration: none;
      font-size: 13px;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 12px;
      background: rgba(255, 255, 255, 0.03);
    }

    .content {
      padding: 26px;
      display: grid;
      gap: 18px;
    }

    .dropzone {
      border: 2px dashed #3f7383;
      border-radius: 14px;
      background: var(--panel-2);
      min-height: 230px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 20px;
      transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
      cursor: pointer;
    }

    .dropzone.dragover {
      border-color: var(--accent-cyan);
      background: #1a5262;
      transform: translateY(-2px);
    }

    .drop-icon { font-size: 34px; color: var(--accent-cyan); margin-bottom: 12px; }
    .drop-title { font-size: 18px; margin: 0 0 6px; }
    .drop-caption { color: var(--muted); margin: 0; font-size: 13px; }

    .status-list {
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(0, 0, 0, 0.15);
      overflow: hidden;
    }

    .status-head {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      color: var(--accent-yellow);
      font-weight: 600;
    }

    .job {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
    }
    .job:last-child { border-bottom: none; }
    .pill { padding: 4px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; }
    .queued { color: #1d2f1f; background: #9fe7b7; }
    .running { color: #433400; background: #ffe08a; }
    .success { color: #10311f; background: #7df0ac; }
    .error { color: #3b1010; background: #ff9f9f; }

    input[type=file] { display: none; }
  </style>
</head>
<body>
  <div class="portal">
    <div class="header">
      <div>
        <h1 class="title">Droid Survair - Web Portal</h1>
        <p class="subtitle">Upload GeoTIFF, process XYZ tiles in background, view in Local Survey Viewer.</p>
      </div>
      <a class="viewer-link" href="http://127.0.0.1:5000" target="_blank" rel="noreferrer">
        <i class="fa-solid fa-map-location-dot"></i> Open Viewer
      </a>
    </div>

    <div class="content">
      <label id="dropzone" class="dropzone">
        <input id="fileInput" type="file" accept=".tif,.tiff" />
        <div>
          <div class="drop-icon"><i class="fa-solid fa-cloud-arrow-up"></i></div>
          <h2 class="drop-title">Drag & drop TIFF here</h2>
          <p class="drop-caption">or click to browse .tif/.tiff files</p>
        </div>
      </label>

      <div class="status-list">
        <div class="status-head"><i class="fa-solid fa-gears"></i> Processing Jobs</div>
        <div id="jobs"></div>
      </div>
    </div>
  </div>

  <script>
    const dropzone = document.getElementById("dropzone");
    const input = document.getElementById("fileInput");
    const jobsBox = document.getElementById("jobs");
    const jobs = new Map();

    function pillClass(status) {
      if (status === "queued") return "pill queued";
      if (status === "running") return "pill running";
      if (status === "success") return "pill success";
      return "pill error";
    }

    function renderJobs() {
      if (!jobs.size) {
        jobsBox.innerHTML = '<div class="job"><span>No jobs started yet.</span><span class="pill queued">idle</span></div>';
        return;
      }
      jobsBox.innerHTML = "";
      [...jobs.values()].reverse().forEach((job) => {
        const row = document.createElement("div");
        row.className = "job";
        row.innerHTML = `<span>${job.filename} - ${job.message || ""}</span><span class="${pillClass(job.status)}">${job.status}</span>`;
        jobsBox.appendChild(row);
      });
    }

    async function startUpload(file) {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/upload", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      jobs.set(data.job_id, { job_id: data.job_id, filename: data.filename, status: data.status, message: data.message });
      renderJobs();
    }

    async function refreshJobs() {
      for (const [jobId, j] of jobs.entries()) {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) continue;
        const data = await res.json();
        jobs.set(jobId, data);
      }
      renderJobs();
    }

    function handleFiles(files) {
      if (!files || !files.length) return;
      const file = files[0];
      const lower = file.name.toLowerCase();
      if (!(lower.endsWith(".tif") || lower.endsWith(".tiff"))) {
        alert("Please upload a .tif or .tiff file.");
        return;
      }
      startUpload(file).catch((err) => alert(err.message));
    }

    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      handleFiles(e.dataTransfer.files);
    });
    input.addEventListener("change", (e) => handleFiles(e.target.files));

    renderJobs();
    setInterval(refreshJobs, 2500);
  </script>
</body>
</html>
"""


def _job_script() -> str:
    return r"""
import sys
from pathlib import Path
import web_optimizer_tool as w

src = Path(sys.argv[1]).resolve()
out_root = w.ensure_output_root()
dataset_dir = out_root / f"{src.stem}_tiles"
dataset_dir.mkdir(parents=True, exist_ok=True)

with w.prepare_wgs84_source(src) as wgs84_src:
    w.convert_tiff_to_xyz_tiles(wgs84_src, dataset_dir)

zoom_levels = w.detect_xyz_zoom_levels(dataset_dir)
bounds = w.raster_bounds_in_wgs84(src)
w.write_metadata(dataset_dir, w.metadata_dict("2D", bounds=bounds, zoom_levels=zoom_levels))
print("XYZ tiles ready at:", dataset_dir)
"""


def _allowed_file(name: str) -> bool:
    return Path(name).suffix.lower() in ALLOWED_EXTENSIONS


def _spawn_tiling_job(job_id: str, tif_path: Path) -> None:
    log_path = UPLOAD_DIR / f"{job_id}.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [str(VENV_PYTHON), "-c", _job_script(), str(tif_path)],
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    jobs[job_id]["pid"] = str(process.pid)
    jobs[job_id]["log"] = str(log_path)
    processes[job_id] = process


def _refresh_job_state(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return
    if job["status"] in {"success", "error"}:
        return

    proc = processes.get(job_id)
    running = proc is not None and proc.poll() is None

    if running:
        job["status"] = "running"
        job["message"] = "Tiling in progress..."
        return

    log_text = ""
    try:
        log_text = Path(job["log"]).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass

    if "XYZ tiles ready at:" in log_text:
        job["status"] = "success"
        job["message"] = "Processing complete. Open Local Survey Viewer."
    else:
        job["status"] = "error"
        job["message"] = "Processing failed. Check log file."


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/upload", methods=["POST"])
def upload():
    if not VENV_PYTHON.exists():
        return jsonify({"error": f"Python executable not found at {VENV_PYTHON}"}), 500

    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "No file selected."}), 400
    if not _allowed_file(f.filename):
        return jsonify({"error": "Only .tif/.tiff uploads are supported."}), 400

    safe_name = secure_filename(f.filename)
    tif_path = UPLOAD_DIR / safe_name
    f.save(tif_path)

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "filename": safe_name,
        "status": "queued",
        "message": "Upload successful. Job queued.",
    }

    try:
        _spawn_tiling_job(job_id, tif_path)
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = f"Failed to start background job: {exc}"
        return jsonify(jobs[job_id]), 500

    return jsonify(jobs[job_id]), 202


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    if job_id not in jobs:
        return jsonify({"error": "Job not found."}), 404
    _refresh_job_state(job_id)
    return jsonify(jobs[job_id])


if __name__ == "__main__":
    print("Droid Survair Portal running at http://127.0.0.1:7000")
    app.run(host="127.0.0.1", port=7000, debug=False)
