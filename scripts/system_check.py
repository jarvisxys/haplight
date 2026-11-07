"""
Prints the machine and software environment, whether PyTorch can use a GPU,
and the latest backend benchmark results. Use it to check a new machine
(e.g. the college server) before running experiments.

Usage:
  uv run python -m scripts.system_check
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pandas as pd
import psutil
import pyarrow  # noqa: F401  # import before libsumo on Windows (CLAUDE.md)

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["eclipse-sumo", "libsumo", "traci", "torch", "numpy", "pandas"]


def _cpu_name() -> str:
    if sys.platform == "win32":
        import winreg

        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _gpus() -> list[str]:
    if not shutil.which("nvidia-smi"):
        return []
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, check=False,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _latest_benchmarks() -> pd.DataFrame | None:
    runs = sorted((ROOT / "results" / "benchmarks").glob("backend_w*_*/episodes.parquet"))
    if not runs:
        return None
    frames = []
    for path in runs:
        df = pd.read_parquet(path)
        df["run"] = path.parent.name
        frames.append(df)
    df = pd.concat(frames)
    return df.groupby(["run", "scenario", "backend"]).agg(
        episodes=("wall_s", "size"), median_wall_s=("wall_s", "median"),
        peak_mem_mb=("peak_mem_worker_mb", "max"),
    ).round(1)


def main() -> int:
    vm = psutil.virtual_memory()
    print("== Machine ==")
    print(f"host          {platform.node()}  ({platform.platform()})")
    print(f"CPU           {_cpu_name()}, {psutil.cpu_count(logical=False)} cores / "
          f"{psutil.cpu_count()} threads")
    print(f"RAM           {vm.total / 2**30:.1f} GB total, {vm.available / 2**30:.1f} GB available")
    gpus = _gpus()
    print(f"GPU           {'; '.join(gpus) if gpus else 'none detected (nvidia-smi not found)'}")

    print("\n== Software ==")
    print(f"python        {sys.version.split()[0]}")
    for p in PACKAGES:
        try:
            print(f"{p:<13} {metadata.version(p)}")
        except metadata.PackageNotFoundError:
            print(f"{p:<13} not installed")
    import torch

    cuda = torch.cuda.is_available()
    print(f"torch CUDA    {'available: ' + torch.cuda.get_device_name(0) if cuda else 'not available'}"
          f" (build CUDA: {torch.version.cuda or 'none, CPU-only build'})")

    print("\n== Latest backend benchmarks (full 3600 s episodes, GreedyHAP) ==")
    bench = _latest_benchmarks()
    print(bench.to_string() if bench is not None else "none found in results/benchmarks/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
