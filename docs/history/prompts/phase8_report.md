# Phase 8 — Statistics and LaTeX generation

Read `PLAN.md` (placeholder table) and Sec. VI-F and VII of the paper.

Build `src/stats.py` and `scripts/report.py`.

**src/stats.py**
- Two-sided Wilcoxon signed-rank, HAPLight-RL vs each baseline on per-episode
  means.
- Holm–Bonferroni within each (scenario, metric) family — not globally.
- Rank-biserial correlation as effect size.
- BCa bootstrap 95% CI on the relative difference (10,000 resamples).
- A `practically_significant()` helper: corrected p < 0.05 **and** relative
  effect exceeds the pre-registered MPE (2% ATT, 5% AQL from the config).

With n=150 the Wilcoxon flags 0.3-second differences. The MPE check is what
stops the paper over-claiming, so it is not optional decoration.

**scripts/report.py** — reads `results/*.parquet` and emits `.tex` fragments
into `paper/generated/` that the main file `\input`s: Tables VIII–XIII, and
pgfplots data for Figs. 4 and 5. Mark results that pass significance but fail
the MPE distinctly (the paper uses † for significant, ‡ for significant *and*
above MPE).

No number in Section VII is ever typed by hand. When this script runs, the
`\pl` placeholders disappear.

Also emit a `results/summary.md` I can read quickly: for each hypothesis
H1–H5, whether the data support it, refute it, or are inconclusive. Be blunt —
a refuted hypothesis reported honestly is worth more than a massaged one.

Finally: recompile `paper/HAPLight_journal_v2.tex` and confirm 0 errors and
0 undefined references.
