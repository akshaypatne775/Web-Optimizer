#!/usr/bin/env python3
"""
Web Optimizer Tool - Droid Survair Master Suite

Automates conversion of heavy drone survey data into web-streaming formats:
- GeoTIFF -> Cloud Optimized GeoTIFF (COG)
- LAS/LAZ -> Cesium 3D Tiles
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List

from colorama import Fore, Style, init
from tqdm import tqdm

# Optional dependency import (primary path for COG conversion)
try:
    import rasterio
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

    for src in tqdm(tiff_files, desc="Converting TIFFs", unit="file", colour="green"):
        dst = src.with_name(f"{src.stem}_web_optimized.tif")
        try:
            run_stage_progress(
                [
                    "Validating source",
                    "Preparing COG options",
                    "Converting",
                    "Finalizing",
                ],
                sleep_s=0.1,
            )

            if HAS_RASTERIO:
                convert_tiff_to_cog_with_rasterio(src, dst)
            else:
                convert_tiff_to_cog_with_gdal(src, dst)

            print_success(f"Created: {dst}")
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

    output_dir = input_file.with_name(f"{input_file.stem}_3dtiles")

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
        print(f"{CYAN}[1]{RESET} Optimize Ortho/DEM (TIFF to Cloud Optimized GeoTIFF - COG)")
        print(f"{CYAN}[2]{RESET} Optimize Point Cloud (LAS/LAZ to 3D Tiles)")
        print(f"{CYAN}[3]{RESET} Exit")
        choice = input(f"\n{YELLOW}Select an option (1-3): {RESET}").strip()

        if choice == "1":
            optimize_ortho_dem()
        elif choice == "2":
            optimize_point_cloud()
        elif choice == "3":
            print_success("Exiting Web Optimizer Tool.")
            break
        else:
            print_warning("Invalid choice. Please select 1, 2, or 3.")

        input(f"\n{YELLOW}Press Enter to return to menu...{RESET}")


def main() -> None:
    try:
        menu_loop()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user. Exiting.{RESET}")


if __name__ == "__main__":
    main()
