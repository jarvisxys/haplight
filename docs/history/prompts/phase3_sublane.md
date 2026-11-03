# Phase 3 — Two-wheeler behaviour calibration

Read `PLAN.md` and `configs/default.yaml`.

The paper claims the SL2015 sublane model approximates Indian two-wheeler
gap-filling. Right now that claim is untested. Make it true, or find out how
false it is.

Build `tests/test_sublane.py::test_2w_reach_front`: build a mixed standing
queue on one approach (fleet shares from the config), release it, and measure
the mean stop-line arrival position of two-wheelers versus cars. Two-wheelers
that started behind should end up in front. If they do not, the sublane
parameters are wrong.

Tune only pure lane-changing behaviour parameters, in
`configs/default.yaml` under `fleet`: `lat_alignment`, `lc_sublane`, and
`lcPushy` / `lcAssertive` / `lcAccelLat` if you need to add them.

Do **not** change `length`, `width`, `min_gap` **or `min_gap_lat`**. All four
feed `a_v = (L + g)(W + g_lat)` in Eq. (3), so changing any of them silently
alters the equivalency vectors pi and beta, epsilon*, Table III, every
assertion in `tests/test_hap.py`, and both calibration experiments C1 and C2.
(This corrects an earlier instruction of mine that listed `min_gap_lat` as
tunable — it is not.) If you become convinced the geometry itself is wrong,
say so and stop; that is a deliberate re-calibration, not a tuning knob.

Report: the measured 2W-vs-car position gap before and after tuning, and the
runtime cost of sublane versus the default model on the same episode (the
compute budget assumes 2–4×). If you cannot get realistic filtering, say so —
that is a limitation the paper already flags and I would rather know than have
it papered over.
