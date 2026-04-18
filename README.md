# MTOUCP Co-Simulation Framework for Decentralised EV Charging on the IEEE 34-Bus Feeder

## 1. Introduction

This repository contains the software developed for the 3rd Year Individual Project (EEEN30330) at the University of Manchester, Department of Electrical and Electronic Engineering.

The project investigates the impact of uncoordinated electric vehicle (EV) charging on distribution network infrastructure and evaluates a decentralised smart charging algorithm — the **Multi-Group Time-of-Use with Critical Peak (MTOUCP)** controller — as a mitigation strategy. The software implements a Python–OpenDSS co-simulation framework that performs Monte Carlo probabilistic analysis across multiple EV penetration levels, comparing a disorderly (uncontrolled) charging baseline against the MTOUCP orderly charging strategy. Performance is evaluated using four engineering metrics: voltage stability (p.u.), voltage unbalance factor (VUF %), cumulative active power losses (kWh), and mechanical tap operations on voltage regulators.

## 2. Contextual Overview

The framework operates as a closed-loop co-simulation between Python (decision logic and data management) and OpenDSS (power flow solver). The diagram below illustrates how the software modules interact:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MONTE CARLO OUTER LOOP                       │
│                  (run_monte_carlo_pof.py)                        │
│                                                                 │
│   For each iteration (seed = 1, 2, ..., N):                    │
│                                                                 │
│   ┌───────────────────────┐                                     │
│   │  generate_fleet_db.py │──► Stochastic EV Fleet DataFrame    │
│   │  (Fleet Generator)    │    (bus, phase, arrival, departure, │
│   └───────────────────────┘     SoC, MTOUCP group)              │
│              │                                                  │
│              ▼                                                  │
│   ┌─────────────────────────────────────────────────┐           │
│   │        48-HOUR TIME-SERIES INNER LOOP           │           │
│   │        (288 steps × 10-min intervals)           │           │
│   │                                                 │           │
│   │   ┌──────────────┐    ┌───────────────────┐     │           │
│   │   │  OpenDSS     │◄──►│  Python Master    │     │           │
│   │   │  (Power Flow │    │  Controller       │     │           │
│   │   │   Solver)    │    │                   │     │           │
│   │   │              │    │  1. Solve PF       │     │           │
│   │   │  Master_     │    │  2. Extract V, VUF │     │           │
│   │   │  IEEE34.dss  │    │  3. Call Logic ─────┼──► │           │
│   │   └──────────────┘    │  4. Override kW    │     │           │
│   │                       │  5. Advance step   │     │           │
│   │                       └───────────────────┘     │           │
│   │                              │                  │           │
│   │                   ┌──────────┴──────────┐       │           │
│   │                   │  ev_logic_engine.py │       │           │
│   │                   │  (MTOUCP Controller)│       │           │
│   │                   │  Tables I & II      │       │           │
│   │                   └─────────────────────┘       │           │
│   └─────────────────────────────────────────────────┘           │
│              │                                                  │
│              ▼                                                  │
│   Exports: MonteCarlo_Summary_XXXEVs.csv                        │
│            SimulationData_XXXEVs.npz                             │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
   ┌───────────────────────┐
   │  Master_plotter.py    │──► IEEE-formatted figures (.png)
   │  (Results Visualiser) │
   └───────────────────────┘
```

Additionally, `generate_ev_scenarios.py` is a standalone script that produces the disorderly (uncoordinated) baseline scenario files used for initial validation prior to the Monte Carlo framework.

## 3. Repository Structure

```
├── run_monte_carlo_pof.py       # Main simulation orchestrator (Monte Carlo loop)
├── generate_fleet_db.py         # Stochastic EV fleet database generator
├── ev_logic_engine.py           # MTOUCP decentralised smart charging controller
├── generate_ev_scenarios.py     # Disorderly baseline scenario generator (standalone)
├── Master_plotter.py            # IEEE-formatted results visualisation
├── Master_IEEE34.dss            # OpenDSS network model (IEEE 34-Node Test Feeder)
├── IEEELineCodes.dss            # Line impedance data (referenced by Master_IEEE34.dss)
├── requirements.txt             # Python dependency list
└── README.md                    # This file
```

**Note:** The simulation generates several output files at runtime that are not included in this repository. These include `EV_Disorderly_Scenario.dss` (temporary DSS load definitions), `EV_Shapes_Matrix.csv` (load shape profiles), `Master_EV_Fleet.csv` (fleet inspection file), `MonteCarlo_Summary_XXXEVs.csv` (summary statistics), and `SimulationData_XXXEVs.npz` (raw array data for plotting).

## 4. Installation Instructions

### Prerequisites

- **Python 3.10** (tested and developed on this version)
- **OpenDSS** must be installed on the system. Download from [EPRI OpenDSS](https://www.epri.com/pages/sa/opendss). The COM server must be registered (this is handled automatically by the OpenDSS installer on Windows).
- **Operating System:** Windows is required, as the `py-dss-interface` library communicates with OpenDSS via the Windows COM interface.

### Setup

1. Clone or download this repository:
   ```
   git clone https://github.com/<your-username>/<repo-name>.git
   cd <repo-name>
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

   The key dependencies are:
   | Package            | Version  | Purpose                                              |
   |--------------------|----------|------------------------------------------------------|
   | `numpy`            | 2.2.6    | Numerical computation and array operations           |
   | `pandas`           | 2.3.3    | EV fleet database management (DataFrames)            |
   | `py-dss-interface` | 2.3.0    | Python–OpenDSS COM interface bridge                  |
   | `matplotlib`       | *        | Results visualisation (used by Master_plotter.py)    |

   *Note: `matplotlib` is required for `Master_plotter.py` but is not listed in the base `requirements.txt`. Install it separately if needed:*
   ```
   pip install matplotlib
   ```

3. Ensure that `IEEELineCodes.dss` is present in the same directory as `Master_IEEE34.dss`. This file contains the phase impedance matrices for the IEEE 34-bus line segments and is loaded via a `Redirect` command inside the master DSS file.

## 5. How to Run the Software

### Step 1 — Run the Monte Carlo Simulation

The primary entry point is `run_monte_carlo_pof.py`. Before running, configure the simulation parameters at the top of the file:

```python
NUM_ITERATIONS = 100   # Number of Monte Carlo iterations per scenario
NUM_EVS = 300          # EV penetration level (e.g. 150, 200, 250)
```

Then execute:
```
python run_monte_carlo_pof.py
```

This will:
- Generate a randomised EV fleet for each iteration using a unique seed
- Run both a **disorderly** (uncoordinated, 7.2 kW flat) and an **orderly** (MTOUCP-controlled) 48-hour simulation per iteration
- Export a summary CSV (`MonteCarlo_Summary_XXXEVs.csv`) and a NumPy archive (`SimulationData_XXXEVs.npz`) containing the raw results

To evaluate multiple penetration levels, change `NUM_EVS` and re-run the script for each level (e.g. 150, 200, 250).

### Step 2 — Generate Figures

After running simulations for all desired penetration levels, configure `Master_plotter.py`:

```python
SCENARIOS = [150, 200, 250]
SCENARIO_LABELS = ['150 EVs (Low Stress)', '200 EVs (High Stress)', '250 EVs (Extreme)']
```

Then execute:
```
python Master_plotter.py
```

This reads the `.npz` files and produces IEEE-formatted publication-quality figures for voltage distributions, temporal loss profiles, spatial tap operations, and temporal tap position traces.

### Standalone: Disorderly Baseline Generator

`generate_ev_scenarios.py` can be run independently to produce the OpenDSS load definitions and load shape matrix for an uncoordinated charging scenario:
```
python generate_ev_scenarios.py
```
This outputs `EV_Disorderly_Scenario.dss` and `EV_Shapes_Matrix.csv`.

## 6. Technical Details

### 6.1 Co-Simulation Architecture

OpenDSS is a static power flow solver that cannot execute condition-based logic natively. To implement the MTOUCP algorithm, a co-simulation approach was adopted. Python interfaces with OpenDSS via the Component Object Model (COM) through the `py-dss-interface` library. At each of the 288 time steps (10-minute resolution over 48 hours), Python:

1. Commands OpenDSS to solve the network power flow
2. Extracts node voltages, sequence voltages (for VUF), system losses, and regulator tap positions
3. Evaluates the MTOUCP logic for each connected EV
4. Overrides the active power setpoint (`kW`) of each EV load object in the OpenDSS model
5. Advances the simulation to the next time step

### 6.2 Stochastic EV Fleet Model

Each Monte Carlo iteration generates a unique EV fleet using `generate_fleet_db.py`. The stochastic parameters are:

- **Spatial allocation (bus):** Weighted categorical distribution based on base load at each of the 28 load-serving buses. Higher-load buses attract proportionally more EVs.
- **Phase allocation:** Socio-economic clustering weights (Phase A: 40%, Phase B: 35%, Phase C: 25%), dynamically normalised to the phases available at each bus.
- **Arrival time:** Gaussian distribution (μ = 18:00, σ = 1.0 hour), clamped to [12:00, 23:30].
- **Connection duration:** Uniform random integer between 3 and 11 hours.
- **Initial SoC:** Uniform distribution [30%, 60%].
- **Target SoC:** Uniform distribution [70%, 100%].
- **Battery capacity:** Fixed at 30 kWh.
- **Maximum charger rating:** Fixed at 7.2 kW (Level 2).
- **MTOUCP group:** Randomly assigned to Group 1, 2, or 3 (staggered release hours at 23:00, 24:00, and 25:00 respectively).

Each iteration uses a unique random seed (seed = iteration number) to ensure reproducibility and statistical independence.

### 6.3 MTOUCP Decentralised Controller

The smart charging algorithm (`ev_logic_engine.py`) is a hybrid rule-based heuristic that combines a staggered time-of-use tariff with localised voltage feedback. It operates using three input variables evaluated independently at each EV's connection node:

**A. Power Draw Priority (S_pri):** Quantifies the urgency of each EV's energy requirement as the ratio of required charging rate to the maximum charger power (7.2 kW). Mapped to five categories: Extra Low (EL), Low (L), Medium (M), High (H), Extra High (EH).

**B. Local Voltage Category (ΔV):** The per-unit voltage at the EV's connection bus is classified into five operational states:

| Category     | Notation | Threshold (p.u.)       |
|--------------|----------|------------------------|
| Danger Low   | DL       | V < 0.950              |
| Warning Low  | WL       | 0.950 ≤ V < 0.952      |
| Nominal      | N        | 0.952 ≤ V < 0.980      |
| Warning High | WH       | 0.980 ≤ V < 1.050      |
| Danger High  | DH       | V ≥ 1.050              |

**C. TOU Grid Signal:** During the on-peak window (18:00 to the group-specific release hour), the signal is "No Charge" (NC). Outside this window, the signal switches to "Charge" (CH).

These three inputs are mapped to an output power setpoint P_charge ∈ {0.0, 3.6, 7.2} kW via two decision matrices:

**Table I — On-Peak Actuation Matrix (t < t_release):**

| S_pri \ V_local | DL  | WL  | N   | WH  | DH  |
|-----------------|-----|-----|-----|-----|-----|
| EL              | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| L               | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| M               | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| H               | 0.0 | 0.0 | 3.6 | 7.2 | 7.2 |
| EH              | 3.6 | 7.2 | 7.2 | 7.2 | 7.2 |

**Table II — Off-Peak Actuation Matrix (t ≥ t_release):**

| S_pri \ V_local | DL  | WL  | N   | WH  | DH  |
|-----------------|-----|-----|-----|-----|-----|
| EL              | 0.0 | 0.0 | 3.6 | 3.6 | 7.2 |
| L               | 0.0 | 0.0 | 3.6 | 3.6 | 7.2 |
| M               | 0.0 | 0.0 | 3.6 | 7.2 | 7.2 |
| H               | 0.0 | 0.0 | 7.2 | 7.2 | 7.2 |
| EH              | 3.6 | 3.6 | 7.2 | 7.2 | 7.2 |

The voltage-responsive throttling provides an implicit phase-balancing effect: heavily loaded phases experience voltage droop first, causing the algorithm to curtail power on those phases before others.

### 6.4 Performance Metrics

The framework evaluates the following metrics across all Monte Carlo iterations:

- **Probability of Failure (PoF) — Voltage:** Percentage of iterations where the absolute minimum node voltage falls below 0.95 p.u.
- **Probability of Failure (PoF) — VUF:** Percentage of iterations where the maximum VUF exceeds 2.0%.
- **Mean Cumulative Active Power Losses:** Average total system losses (kWh) across the 48-hour simulation window.
- **Mean Total Tap Operations:** Average number of mechanical tap changes across all six single-phase regulators (creg1a–c, creg2a–c).

### 6.5 Network Model

The distribution network is the **IEEE 34-Node Test Feeder**, defined in `Master_IEEE34.dss`. This is a standard test network widely used in power systems research, featuring an extended radial topology, single-phase and three-phase laterals, two inline voltage regulators (each with three single-phase units), distributed shunt capacitors, and 28 load-serving buses. The base frequency has been set to 50 Hz for this study. Dynamic residential loading is applied via daily load shapes.

## 7. Known Issues and Future Improvements

### Known Limitations

- **Windows-only execution:** The `py-dss-interface` library relies on the Windows COM interface to communicate with OpenDSS. The framework cannot run on macOS or Linux without an alternative OpenDSS binding (e.g. `OpenDSSDirect.py`).
- **Fixed battery parameters:** All EVs share a uniform 30 kWh battery capacity and 7.2 kW maximum charger rating. Real-world fleets exhibit significant heterogeneity in both parameters.
- **Single charger type:** Only Level 2 (7.2 kW) home charging is modelled. Rapid chargers, workplace charging, and public charging infrastructure are not considered.
- **Sequential EV iteration:** The charging logic loop iterates over each EV in series within each time step rather than using fully vectorised operations, which increases computation time for large fleet sizes.
- **No V2G capability:** The controller only manages unidirectional charging (V1G). Vehicle-to-grid (V2G) power export is not implemented.

### Potential Future Extensions

- Introduce heterogeneous battery capacities and charger ratings sampled from real-world fleet data.
- Implement V2G bidirectional power flow to evaluate grid support services.
- Port the OpenDSS interface to `OpenDSSDirect.py` for cross-platform compatibility.
- Vectorise the per-EV charging logic loop for improved computational performance.
- Extend the framework to larger or more realistic UK distribution network models.
- Add thermal constraint monitoring (cable and transformer ratings) as an additional performance metric.

## 8. Third-Party Code and Acknowledgements

- **OpenDSS** is an open-source distribution system simulator developed by the Electric Power Research Institute (EPRI). Available at: [https://www.epri.com/pages/sa/opendss](https://www.epri.com/pages/sa/opendss)
- **py-dss-interface** (v2.3.0) is a Python COM interface wrapper for OpenDSS, developed by Paulo Radatz. Available at: [https://github.com/PauloRadatz/py_dss_interface](https://github.com/PauloRadatz/py_dss_interface)
- **IEEE 34-Node Test Feeder** is a standard test case maintained by the IEEE PES Distribution System Analysis Subcommittee. The `.dss` model file used in this project is adapted from the version distributed with OpenDSS, with the base frequency modified to 50 Hz and dynamic residential load shapes added.
- The MTOUCP tariff structure and the decentralised fuzzy-logic control concept are based on the work of Faddel and Mohammed [1].
- All other code in this repository was developed by the author for this project.

### References

[1] S. Faddel and O. Mohammed, "Automated Distributed Electric Vehicle Controller for Residential Demand Side Management," *IEEE Transactions on Industry Applications*, vol. 55, no. 1, pp. 16–25, Jan.–Feb. 2019.
