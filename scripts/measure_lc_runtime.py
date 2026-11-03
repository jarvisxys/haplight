"""
Phase 4 pre-check (prompts/phase4_rl.md): measure the REAL SL2015-vs-LC2013
runtime ratio on a full S2 episode at nominal demand, before any RL training
is built. Phase 3 measured 7.6-8.7x on a dense held-then-released queue
(PAPER_CHANGELOG P3-2) against PLAN.md's 2-4x compute-budget assumption,
with an explicit caveat that a queue-release burst might not generalise to
spread-out episode traffic. This resolves that caveat with a real
production episode rather than the synthetic testbed.

Runs the SAME S2 net/route/seed/controller (GreedyHAP, full
episode_length_s) twice, through the identical HAPLightEnv code path --
only src.env.HAPLightEnv's new `sublane_simulation` flag differs (whether
--lateral-resolution is passed to SUMO; SL2015 requires it, LC2013 is
incompatible with it) -- for an apples-to-apples wall-clock comparison that
isolates the SUMO-engine cost, not Python-side control overhead.

Usage
-----
    python -m scripts.measure_lc_runtime
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402


def _make_lc2013_variant(net_dir: Path, out_dir: Path) -> None:
    """Copies net_dir's .sumocfg/.net.xml/.rou.xml/a_bar_per_movement.json
    into out_dir, with the route file's laneChangeModel switched to LC2013
    and the SL2015-only latAlignment/lcSublane attributes stripped (LC2013
    doesn't understand them)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in net_dir.glob("*"):
        if src.suffix == ".rou.xml" or src.name.endswith(".rou.xml"):
            text = src.read_text()
            text = text.replace('laneChangeModel="SL2015"', 'laneChangeModel="LC2013"')
            text = re.sub(r' latAlignment="[^"]*"', "", text)
            text = re.sub(r' lcSublane="[^"]*"', "", text)
            (out_dir / src.name).write_text(text)
        elif src.name.endswith(".sumocfg"):
            # Net-file reference inside is relative to net_dir originally;
            # rewrite to an absolute path so it still resolves from out_dir.
            text = src.read_text()
            net_name = next(net_dir.glob("*.net.xml")).name
            text = text.replace(net_name, str((net_dir / net_name).resolve()))
            (out_dir / src.name).write_text(text)
        elif src.name.endswith(".net.xml") or src.name == "a_bar_per_movement.json":
            (out_dir / src.name).write_bytes(src.read_bytes())


def _run(net_dir: Path, cfg: dict, fleet: Fleet, sublane_simulation: bool, seed: int) -> float:
    env = HAPLightEnv(
        str(net_dir), cfg, fleet, seed=seed, eta=0.0, estimator="area",
        sublane_simulation=sublane_simulation,
    )
    try:
        t0 = time.perf_counter()
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        return time.perf_counter() - t0
    finally:
        env.close()


def main() -> int:
    cfg = yaml.safe_load(Path("configs/default.yaml").read_text())
    fleet = Fleet.from_config(cfg)
    net_dir = Path("nets/grid4x4")
    lc2013_dir = Path("nets/grid4x4_lc2013_tmp")

    print(f"S2 (grid4x4) full episode ({cfg['demand']['episode_length_s']:.0f}s), "
          f"nominal demand, GreedyHAP, seed=0")

    print("  Running SL2015 (production config)...")
    sl_s = _run(net_dir, cfg, fleet, sublane_simulation=True, seed=0)
    print(f"    wall_clock = {sl_s:.1f}s")

    print("  Building LC2013 variant and running...")
    _make_lc2013_variant(net_dir, lc2013_dir)
    lc_s = _run(lc2013_dir, cfg, fleet, sublane_simulation=False, seed=0)
    print(f"    wall_clock = {lc_s:.1f}s")

    ratio = sl_s / lc_s if lc_s else float("nan")
    print(f"\n  SL2015/LC2013 wall-clock ratio on a REAL S2 episode = {ratio:.2f}x")
    print(f"  PLAN.md compute budget assumed 2-4x; Phase 3's queue-release testbed measured 7.6-8.7x")
    if ratio >= 6.0:
        print(
            "\n  !! ratio >= 6x -- per prompts/phase4_rl.md, STOP before launching any "
            "training and report this. Do not proceed to build policy/ppo/train "
            "until this is resolved."
        )
    else:
        print("\n  ratio < 6x -- proceeding with Phase 4 as planned.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
