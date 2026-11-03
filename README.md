# HAPLight

Heterogeneity-aware occupancy-pressure (HAP) traffic signal control with
certified reinforcement learning, for Indian mixed traffic. Simulated in SUMO
with the SL2015 sublane model.

Author: Aditya Kumar (RGIPT)

The research plan is in [docs/plan/HAPLight_v3_Research_Plan.pdf](docs/plan/HAPLight_v3_Research_Plan.pdf).
Current progress is in [docs/STATUS.md](docs/STATUS.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and the locked dependencies.

```powershell
uv sync
# SUMO is installed as a Python package; point SUMO_HOME at it
$env:SUMO_HOME = (uv run python -c "import sumo, os; print(os.path.dirname(sumo.__file__))")
uv run pytest -q
```

On Linux or the GPU server:

```bash
uv sync
export SUMO_HOME=$(uv run python -c "import sumo, os; print(os.path.dirname(sumo.__file__))")
uv run pytest -q
```

## Layout

| Path | Contents |
|---|---|
| `src/` | environment, HAP measure, sensing model, controllers, policy, PPO, baselines |
| `scripts/` | training, evaluation, calibration and network-building entry points (`python -m scripts.<name>`) |
| `tests/` | unit and SUMO integration tests |
| `configs/default.yaml` | every numeric parameter; the only place numbers live |
| `nets/` | SUMO networks for S1 (arterial), S2 (grid) and the Bengaluru source data |
| `paper/` | paper source |
| `docs/` | plan, status, decision records, v2 history |
| `results/`, `results_baselines/` | junctions to `D:\haplight-data\runs` (not in git) |

## Data

Run outputs, checkpoints, datasets and large generated networks are kept outside
the repository in `D:\haplight-data`:

- `runs/` run outputs (`results`, `results_baselines`) and `v2_valid/`, the last valid v2 checkpoints
- `nets/bengaluru_v2/` generated Bengaluru networks from v2
- `archive/` full v2 project snapshot with its SHA-256
- `datasets/` external datasets (UVH-26)
