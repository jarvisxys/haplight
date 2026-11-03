"""
Phase 6 acceptance test (prompts/phase6_bengaluru.md): the Bengaluru
corridor network must validate structurally before anything gets built on
top of it (demand, calibration, evaluation). Independent of the specific
final TLS count (a scope decision, not a structural one) -- this test
re-validates whatever `nets/bengaluru/bengaluru.net.xml` the build script
last produced, using the exact same checks `validate_bengaluru_net`
enforces at build time, plus an actual SUMO load.

Run:  pytest tests/test_nets.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_nets import validate_bengaluru_net  # noqa: E402

NET_FILE = Path(__file__).resolve().parents[1] / "nets" / "bengaluru" / "bengaluru.net.xml"


@pytest.mark.skipif(not NET_FILE.exists(), reason="run scripts/build_nets.py --scenario bengaluru first")
def test_bengaluru_loads():
    """Every remaining TLS has >=2 incoming edges, no isolated junctions,
    no zero-lane edges (prompts/phase6_bengaluru.md's exact validation
    gate) -- and, beyond sumolib's parse, that libsumo/traci can actually
    START a session against the network (a file sumolib parses without
    error can still fail to load in the simulator proper)."""
    report = validate_bengaluru_net(NET_FILE)
    assert report["n_tls_invalid"] == 0, (
        f"{report['n_tls_invalid']} TLS junction(s) with <2 incoming edges: "
        f"{report['invalid_tls_ids']}"
    )
    assert report["n_isolated_junctions"] == 0, f"{report['n_isolated_junctions']} isolated junction(s)"
    assert report["n_zero_lane_edges"] == 0, f"{report['n_zero_lane_edges']} zero-lane edge(s)"
    assert report["n_tls_valid"] > 0, "no valid TLS junctions at all"

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.env import bootstrap_sumo  # noqa: E402

    traci, backend = bootstrap_sumo(prefer_libsumo=True)
    try:
        traci.start(["sumo", "-n", str(NET_FILE), "--no-step-log", "true"])
        traci.simulationStep()
    finally:
        traci.close()
