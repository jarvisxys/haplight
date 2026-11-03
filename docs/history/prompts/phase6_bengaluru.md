# Phase 6 — Bengaluru corridor extraction

Read `PLAN.md` Sec. "Known traps" and Sec. VI-C of the paper.

This is the highest-risk phase. `osmWebWizard` output for Indian arterials is
reliably broken: missing traffic lights, unjoined junction clusters, phantom
connections, unrealistic lane counts.

Extend `scripts/build_nets.py` to produce `nets/bengaluru/` from the bounding
box in `configs/default.yaml` (`[77.67, 12.99, 77.80, 13.08]`, the Old Madras
Road / NH-75 corridor around Hoskote–K.R. Puram).

Pipeline: download the OSM extract → `netconvert` with `--junctions.join`,
`--tls.guess-signals`, `--tls.join`, `--lefthand true` → validate → repair.

Requirements:
- **Every manual correction goes in the script**, not into a hand-edited XML.
  The paper promises the network is reproducible from the bounding box alone.
- Validate before accepting: every TLS has ≥2 phases; no isolated junctions;
  no edges with 0 lanes; every signalised junction has ≥2 incoming edges. Write
  this as `tests/test_nets.py::test_bengaluru_loads`.
- Print the final signalised-intersection count `N` — it fills a `\note{}` in
  Sec. VI-C of the paper.
- Demand: synthetic, composition-calibrated, with a directional morning peak
  toward Bengaluru.

Timebox this. If after a day the network still will not validate, tell me and
we shrink the bounding box rather than sink the schedule. A smaller corridor
that works beats a large one that does not.
