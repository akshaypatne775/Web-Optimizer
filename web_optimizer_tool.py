#!/usr/bin/env python3
"""Web Optimizer Tool - Droid Survair Master Suite.

Automates conversion of heavy drone survey data into web-streaming formats:
- GeoTIFF -> Cloud Optimized GeoTIFF (COG)
- LAS/LAZ -> Cesium 3D Tiles
- GeoTIFF -> XYZ map tiles
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from colorama import Fore, Style, init
from tqdm import tqdm

# Optional dependency import (primary path for COG conversion)
try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    from rasterio.shutil import copy as rio_copy

    HAS_RASTERIO = True
except Exception:
    HAS_RASTERIO = False


init(autoreset=True)


CYAN = Fore.CYAN
YELLOW = Fore.YELLOW
GREEN = Fore.GREEN
RED = Fore.RED
RESET = Style.RESET_ALL
WGS84_EPSG = 4326
SURVEY_OUTPUTS_DIR = Path.cwd() / "survey_outputs"


def print_header() -> None:
    print(f"{CYAN}{'=' * 64}")
    print(f"{CYAN}      Droid Survair - Master Suite | Web Optimizer Tool")
    print(f"{CYAN}{'=' * 64}{RESET}")


def print_warning(msg: str) -> None:
    print(f"{YELLOW}[WARNING]{RESET} {msg}")


def print_error(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}")


def print_success(msg: str) -> None:
    print(f"{GREEN}[SUCCESS]{RESET} {msg}")


def print_info(msg: str) -> None:
    print(f"{CYAN}[INFO]{RESET} {msg}")


def ensure_output_root() -> Path:
    SURVEY_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return SURVEY_OUTPUTS_DIR


def to_deg_bounds(bounds: Tuple[float, float, float, float], crs: CRS) -> Tuple[float, float, float, float]:
    if not HAS_RASTERIO:
        return bounds
    left, bottom, right, top = rasterio.warp.transform_bounds(crs, CRS.from_epsg(WGS84_EPSG), *bounds, densify_pts=21)
    return left, bottom, right, top


def metadata_dict(
    data_type: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    zoom_levels: Optional[Dict[str, int]] = None,
) -> Dict[str, object]:
    center = None
    if bounds:
        left, bottom, right, top = bounds
        center = {"lat": (bottom + top) / 2, "lon": (left + right) / 2}
        bounds_payload = {
            "southwest": {"lat": bottom, "lon": left},
            "northeast": {"lat": top, "lon": right},
        }
    else:
        bounds_payload = None
    return {
        "type": data_type,
        "center": center,
        "bounds": bounds_payload,
        "zoom_levels": zoom_levels or {"min": 0, "max": 22},
    }


def write_metadata(dataset_dir: Path, metadata: Dict[str, object]) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print_info(f"Metadata written: {metadata_path}")


def tileset_bounds_from_json(tileset_path: Path) -> Optional[Tuple[float, float, float, float]]:
    try:
        payload = json.loads(tileset_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    region = payload.get("root", {}).get("boundingVolume", {}).get("region")
    if not region or len(region) < 4:
        return None

    # 3D Tiles region bounds are radians: [west, south, east, north, minHeight, maxHeight].
    west, south, east, north = region[:4]
    return (
        float(west) * (180.0 / 3.141592653589793),
        float(south) * (180.0 / 3.141592653589793),
        float(east) * (180.0 / 3.141592653589793),
        float(north) * (180.0 / 3.141592653589793),
    )


def run_stage_progress(stages: Iterable[str], sleep_s: float = 0.25) -> None:
    """
    Lightweight staged progress for operations where true progress callbacks
    are unavailable.
    """
    stage_list = list(stages)
    with tqdm(total=len(stage_list), desc="Progress", unit="stage", colour="cyan") as pbar:
        for stage in stage_list:
            pbar.set_postfix_str(stage)
            time.sleep(sleep_s)
            pbar.update(1)


def gather_tiffs(input_folder: Path) -> List[Path]:
    files: List[Path] = []
    for pattern in ("*.tif", "*.tiff", "*.TIF", "*.TIFF"):
        files.extend(input_folder.glob(pattern))
    return sorted(set(files))


def raster_bounds_in_wgs84(path: Path) -> Optional[Tuple[float, float, float, float]]:
    if not HAS_RASTERIO:
        return None
    with rasterio.open(path) as src:
        if not src.crs:
            return None
        raw_bounds = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
        return to_deg_bounds(raw_bounds, src.crs)


@contextmanager
def prepare_wgs84_source(src: Path) -> Iterator[Path]:
    """Yield a WGS84 TIFF path; reprojection is automatic if needed."""
    if not HAS_RASTERIO:
        # Caller may use GDAL fallback conversion from original source.
        yield src
        return

    with rasterio.open(src) as dataset:
        if dataset.crs and dataset.crs.to_epsg() == WGS84_EPSG:
            yield src
            return

    temp_dir = ensure_output_root() / "_tmp_reprojected"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{src.stem}_wgs84.tif"
    print_info(f"Auto-reprojecting {src.name} -> EPSG:{WGS84_EPSG}")

    with rasterio.open(src) as source:
        if not source.crs:
            raise RuntimeError(f"{src.name} has no CRS. Cannot auto-reproject to EPSG:4326.")

        transform, width, height = calculate_default_transform(
            source.crs,
            CRS.from_epsg(WGS84_EPSG),
            source.width,
            source.height,
            *source.bounds,
        )
        kwargs = source.meta.copy()
        kwargs.update(
            {
                "crs": CRS.from_epsg(WGS84_EPSG),
                "transform": transform,
                "width": width,
                "height": height,
            }
        )
        with rasterio.open(temp_path, "w", **kwargs) as destination:
            for band_idx in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band_idx),
                    destination=rasterio.band(destination, band_idx),
                    src_transform=source.transform,
                    src_crs=source.crs,
                    dst_transform=transform,
                    dst_crs=CRS.from_epsg(WGS84_EPSG),
                    resampling=Resampling.bilinear,
                )
    try:
        yield temp_path
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def convert_tiff_to_cog_with_rasterio(src: Path, dst: Path) -> None:
    """
    Convert TIFF to COG using rasterio's COG driver.
    """
    rio_copy(
        src.as_posix(),
        dst.as_posix(),
        driver="COG",
        compress="DEFLATE",
        tiled=True,
        blocksize=512,
        overview_resampling="nearest",
        OVERVIEWS="AUTO",
    )


def convert_tiff_to_cog_with_gdal(src: Path, dst: Path) -> None:
    """
    Convert TIFF to COG using gdal_translate as fallback.
    """
    if shutil.which("gdal_translate") is None:
        raise RuntimeError(
            "gdal_translate was not found in PATH. Install GDAL and ensure "
            "'gdal_translate' is available from your terminal."
        )

    cmd = [
        "gdal_translate",
        "-of",
        "COG",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=DEFLATE",
        "-co",
        "OVERVIEWS=AUTO",
        str(src),
        str(dst),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "gdal_translate failed.\n"
            f"stdout: {completed.stdout.strip()}\n"
            f"stderr: {completed.stderr.strip()}"
        )


def convert_tiff_to_xyz_tiles(src_tif: Path, output_tiles_dir: Path) -> None:
    output_tiles_dir.mkdir(parents=True, exist_ok=True)
    candidate_cmds = [
        [sys.executable, "-m", "gdal2tiles", "-w", "none", "-r", "bilinear", str(src_tif), str(output_tiles_dir)],
        [sys.executable, "gdal2tiles.py", "-w", "none", "-r", "bilinear", str(src_tif), str(output_tiles_dir)],
        ["gdal2tiles", "-w", "none", "-r", "bilinear", str(src_tif), str(output_tiles_dir)],
        ["gdal2tiles.bat", "-w", "none", "-r", "bilinear", str(src_tif), str(output_tiles_dir)],
        ["gdal2tiles.py", "-w", "none", "-r", "bilinear", str(src_tif), str(output_tiles_dir)],
    ]

    last_error: str | None = None
    for cmd in candidate_cmds:
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except (FileNotFoundError, OSError) as exc:
            last_error = f"Command failed to start: {' '.join(cmd)}\n{exc}"
            continue

        if completed.returncode == 0:
            return

        output = (completed.stdout + "\n" + completed.stderr).strip()
        last_error = f"Command failed: {' '.join(cmd)}\n{output}"

    base_message = (
        "gdal2tiles command not found. Please open your terminal, activate the virtual "
        "environment, and run: pip install gdal2tiles"
    )
    if last_error:
        raise RuntimeError(f"{base_message}\n\nLast error:\n{last_error}")
    raise RuntimeError(base_message)


def detect_xyz_zoom_levels(tiles_dir: Path) -> Dict[str, int]:
    zoom_values: List[int] = []
    for child in tiles_dir.iterdir():
        if child.is_dir() and child.name.isdigit():
            zoom_values.append(int(child.name))
    if not zoom_values:
        return {"min": 0, "max": 22}
    return {"min": min(zoom_values), "max": max(zoom_values)}


def optimize_ortho_dem() -> None:
    print(f"\n{CYAN}-- Optimize Ortho/DEM (TIFF -> COG) --{RESET}")
    folder_raw = input(f"{YELLOW}Enter input folder containing TIFF files: {RESET}").strip().strip('"')
    input_folder = Path(folder_raw).expanduser()

    if not input_folder.exists() or not input_folder.is_dir():
        print_error("Provided path is not a valid folder.")
        return

    tiff_files = gather_tiffs(input_folder)
    if not tiff_files:
        print_warning("No .tif/.tiff files found in the specified folder.")
        return

    print_info(f"Found {len(tiff_files)} TIFF file(s) to optimize.")
    failures: List[str] = []

    out_root = ensure_output_root()
    for src in tqdm(tiff_files, desc="Converting TIFFs", unit="file", colour="green"):
        dataset_dir = out_root / f"{src.stem}_cog"
        dst = dataset_dir / f"{src.stem}_web_optimized.tif"
        try:
            dataset_dir.mkdir(parents=True, exist_ok=True)
            run_stage_progress(
                [
                    "Validating source",
                    "Checking CRS / auto-reproject",
                    "Preparing COG options",
                    "Converting",
                    "Finalizing",
                ],
                sleep_s=0.1,
            )

            with prepare_wgs84_source(src) as wgs84_source:
                if HAS_RASTERIO:
                    convert_tiff_to_cog_with_rasterio(wgs84_source, dst)
                else:
                    convert_tiff_to_cog_with_gdal(wgs84_source, dst)

            print_success(f"Created: {dst}")
            bounds = raster_bounds_in_wgs84(dst)
            write_metadata(dataset_dir, metadata_dict("2D", bounds=bounds, zoom_levels={"min": 0, "max": 22}))
        except Exception as exc:
            failures.append(f"{src.name}: {exc}")
            print_error(f"Failed for {src.name} -> {exc}")

    if failures:
        print_warning("Some TIFF files failed to convert:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print_success("All TIFF files optimized successfully.")

    if not HAS_RASTERIO and shutil.which("gdal_translate") is None:
        print_warning(
            "Neither rasterio nor GDAL (gdal_translate) are available. Install one of:\n"
            "  - pip install rasterio\n"
            "  - GDAL binaries with gdal_translate in PATH"
        )


def generate_xyz_tiles() -> None:
    print(f"\n{CYAN}-- Generate Map Tiles (XYZ/Standard) --{RESET}")
    folder_raw = input(f"{YELLOW}Enter input folder containing TIFF files: {RESET}").strip().strip('"')
    input_folder = Path(folder_raw).expanduser()

    if not input_folder.exists() or not input_folder.is_dir():
        print_error("Provided path is not a valid folder.")
        return

    tiff_files = gather_tiffs(input_folder)
    if not tiff_files:
        print_warning("No .tif/.tiff files found in the specified folder.")
        return

    out_root = ensure_output_root()
    failures: List[str] = []
    print_info(f"Found {len(tiff_files)} TIFF file(s) for XYZ tiling.")

    for src in tqdm(tiff_files, desc="Generating XYZ tiles", unit="file", colour="yellow"):
        dataset_dir = out_root / f"{src.stem}_tiles"
        try:
            run_stage_progress(
                [
                    "Validating source",
                    "Checking CRS / auto-reproject",
                    "Preparing tile pyramid",
                    "Running gdal2tiles.py",
                ],
                sleep_s=0.1,
            )
            with prepare_wgs84_source(src) as wgs84_source:
                convert_tiff_to_xyz_tiles(wgs84_source, dataset_dir)

            zoom_levels = detect_xyz_zoom_levels(dataset_dir)
            bounds = raster_bounds_in_wgs84(src)
            write_metadata(dataset_dir, metadata_dict("2D", bounds=bounds, zoom_levels=zoom_levels))
            print_success(f"XYZ tiles generated: {dataset_dir}")
        except Exception as exc:
            failures.append(f"{src.name}: {exc}")
            print_error(f"Failed for {src.name} -> {exc}")

    if failures:
        print_warning("Some TIFF files failed XYZ tiling:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print_success("All XYZ tile datasets generated successfully.")


def run_py3dtiles_convert(input_file: Path, output_dir: Path) -> None:
    """
    Convert LAS/LAZ to 3D Tiles using py3dtiles CLI.
    Several command patterns are attempted for compatibility across versions.
    """
    candidate_cmds = [
        ["py3dtiles", "convert", "--out", str(output_dir), str(input_file)],
        ["py3dtiles", "convert", str(input_file), "--out", str(output_dir)],
        [sys.executable, "-m", "py3dtiles", "convert", "--out", str(output_dir), str(input_file)],
        [sys.executable, "-m", "py3dtiles", "convert", str(input_file), "--out", str(output_dir)],
    ]

    last_error: str | None = None
    for cmd in candidate_cmds:
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            last_error = "py3dtiles command not found."
            continue

        if completed.returncode == 0:
            return

        # If command exists but args do not match this version, keep trying.
        output = (completed.stdout + "\n" + completed.stderr).strip()
        last_error = f"Command failed: {' '.join(cmd)}\n{output}"

    raise RuntimeError(
        f"Unable to run py3dtiles conversion. Last error:\n{last_error or 'Unknown error.'}"
    )


def optimize_point_cloud() -> None:
    print(f"\n{CYAN}-- Optimize Point Cloud (LAS/LAZ -> 3D Tiles) --{RESET}")
    file_raw = input(f"{YELLOW}Enter input .las/.laz file path: {RESET}").strip().strip('"')
    input_file = Path(file_raw).expanduser()

    if not input_file.exists() or not input_file.is_file():
        print_error("Provided path is not a valid file.")
        return

    if input_file.suffix.lower() not in (".las", ".laz"):
        print_error("Input file must be .las or .laz")
        return

    out_root = ensure_output_root()
    output_dir = out_root / f"{input_file.stem}_3dtiles"

    try:
        run_stage_progress(
            [
                "Checking dependencies",
                "Preparing output structure",
                "Converting to 3D Tiles",
                "Validating tileset",
            ],
            sleep_s=0.15,
        )

        run_py3dtiles_convert(input_file, output_dir)

        tileset_path = output_dir / "tileset.json"
        if not tileset_path.exists():
            print_warning(
                "Conversion command completed but tileset.json was not found. "
                "Please verify py3dtiles version/flags."
            )
        else:
            print_success(f"3D Tiles generated at: {output_dir}")
            print_info("Expected contents include tileset.json and tile binaries (.pnts/.b3dm).")
            bounds = tileset_bounds_from_json(tileset_path)
            write_metadata(output_dir, metadata_dict("3D", bounds=bounds, zoom_levels={"min": 0, "max": 22}))

    except Exception as exc:
        print_error(str(exc))
        print_warning(
            "py3dtiles may be missing or unavailable. Install with:\n"
            "  - pip install py3dtiles\n"
            "Then ensure either 'py3dtiles' is in PATH or Python can run '-m py3dtiles'."
        )


def menu_loop() -> None:
    while True:
        print_header()
        print_info(f"Unified output directory: {ensure_output_root()}")
        print(f"{CYAN}[1]{RESET} Optimize Ortho/DEM (TIFF to Cloud Optimized GeoTIFF - COG)")
        print(f"{CYAN}[2]{RESET} Optimize Point Cloud (LAS/LAZ to 3D Tiles)")
        print(f"{CYAN}[3]{RESET} Generate Map Tiles (XYZ/Standard)")
        print(f"{CYAN}[4]{RESET} Exit")
        choice = input(f"\n{YELLOW}Select an option (1-4): {RESET}").strip()

        if choice == "1":
            optimize_ortho_dem()
        elif choice == "2":
            optimize_point_cloud()
        elif choice == "3":
            generate_xyz_tiles()
        elif choice == "4":
            print_success("Exiting Web Optimizer Tool.")
            break
        else:
            print_warning("Invalid choice. Please select 1, 2, 3, or 4.")

        input(f"\n{YELLOW}Press Enter to return to menu...{RESET}")


def main() -> None:
    try:
        menu_loop()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user. Exiting.{RESET}")


if __name__ == "__main__":
    main()
