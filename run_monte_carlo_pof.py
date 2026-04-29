import py_dss_interface
import pandas as pd
import numpy as np
import pathlib

# Import your existing modules
from generate_fleet_db import generate_ev_fleet
from ev_logic_engine import get_smart_charging_rate

# --- EVALUATION CONFIGURATION ---
NUM_ITERATIONS = 1000  # Executing full 1000-iteration campaign
NUM_EVS = 150  # Mandatory: Test at the 200 EV hosting capacity threshold
DSS_FILE = "Master_IEEE34.dss"
SIMULATION_STEPS = 288  # 48 hours in 10-minute steps

# --- REGULATOR MAPPING ---
REGULATORS = ['creg1a', 'creg1b', 'creg1c', 'creg2a', 'creg2b', 'creg2c']


def run_single_simulation(scenario, df_fleet, dss):
    """
    Runs a single 48-hour simulation.
    Returns: Absolute Min Voltage, Max VUF, Total Losses (kWh),
             Tap Operations Dict, Temporal creg1a Array, Temporal creg2a Array,
             Step Losses (kW) Array, Probability of Under-Charge (%), Mean Deficit (kWh)
    """
    dss.text("Clear")
    script_path = pathlib.Path(__file__).parent.resolve()

    dummy_ev_file = script_path / "EV_Disorderly_Scenario.dss"
    with open(dummy_ev_file, 'w') as f:
        f.write("! Blank file\n")

    dss.text(f"Compile '{script_path / DSS_FILE}'")

    for _, ev in df_fleet.iterrows():
        dss.text(f"New Load.{ev['EV_ID']} Bus1={ev['Bus_Node']}.{ev['Phase']} "
                 f"Phases=1 kV=14.4 kW=0.0 PF=0.99 Model=1 Status=Variable")

    dss.text("Set Mode=Daily StepSize=10m Number=1")

    # --- PERFORMANCE OPTIMISATION (Pre-simulation Mapping) ---
    three_phase_buses = []
    for bus in dss.circuit.buses_names:
        dss.circuit.set_active_bus(bus)
        if dss.bus.num_nodes >= 3:
            three_phase_buses.append(bus)

    absolute_min_v = 2.0
    absolute_max_vuf = 0.0
    total_losses_kwh = 0.0

    # Regulator Tap Trackers
    tap_positions = {r: 0 for r in REGULATORS}
    tap_operations = {r: 0 for r in REGULATORS}
    temporal_creg1a = []
    temporal_creg2a = []

    # Instantaneous Loss Tracker
    step_losses_kw = []

    local_fleet = df_fleet.copy()

    for step in range(SIMULATION_STEPS):
        dss.solution.solve()

        if not dss.solution.converged:
            print(f"Warning: Power flow diverged at step {step}")
            break

        # 1. Vectorised Voltage Extraction
        try:
            nodes = np.array(dss.circuit.nodes_names)
            v_pu = np.array(dss.circuit.buses_vmag_pu)
        except AttributeError:
            nodes = np.array(dss.circuit.all_node_names)
            v_pu = np.array(dss.circuit.all_bus_vmag_pu)

        valid_mask = v_pu > 0.1
        v_pu_valid = v_pu[valid_mask]
        nodes_valid = nodes[valid_mask]

        step_min_v = np.min(v_pu_valid)
        if step_min_v < absolute_min_v:
            absolute_min_v = step_min_v

        voltage_dict = {}
        for n, v in zip(nodes_valid, v_pu_valid):
            bus_base = n.split('.')[0]
            if bus_base not in voltage_dict or v < voltage_dict[bus_base]:
                voltage_dict[bus_base] = v

        # 2. Optimised VUF Extraction
        step_max_vuf = 0.0
        for bus in three_phase_buses:
            dss.circuit.set_active_bus(bus)
            seq = dss.bus.seq_voltages
            if len(seq) >= 3 and seq[1] > 0.1:
                vuf = (seq[2] / seq[1]) * 100.0
                if vuf > step_max_vuf:
                    step_max_vuf = vuf

        if step_max_vuf > absolute_max_vuf:
            absolute_max_vuf = step_max_vuf

        # 3. System Losses Extraction
        active_losses_kw = dss.circuit.losses[0] / 1000.0
        total_losses_kwh += active_losses_kw * (10.0 / 60.0)
        step_losses_kw.append(active_losses_kw)

        # 4. Regulator Tap Extraction (Mechanical Operations)
        for reg in REGULATORS:
            dss.regcontrols.name = reg
            current_tap = dss.regcontrols.tap_number
            if step == 0:
                tap_positions[reg] = current_tap
            else:
                tap_operations[reg] += abs(current_tap - tap_positions[reg])
                tap_positions[reg] = current_tap

        temporal_creg1a.append(tap_positions['creg1a'])
        temporal_creg2a.append(tap_positions['creg2a'])

        # 5. Apply Charging Logic
        for idx in local_fleet.index:
            ev = local_fleet.loc[idx].to_dict()

            if ev['Is_Plugged_In']:
                kwh_added = ev['Current_kW_Draw'] * (10.0 / 60.0)
                ev['Current_kWh'] += kwh_added

            is_time_to_charge = (step >= ev['Arrival_Step']) and (step < ev['Departure_Step'])
            needs_charge = (ev['Current_kWh'] < ev['Target_kWh'])

            if is_time_to_charge and needs_charge:
                ev['Is_Plugged_In'] = True
            else:
                ev['Is_Plugged_In'] = False
                ev['Current_kW_Draw'] = 0.0

            if ev['Is_Plugged_In']:
                if scenario == "orderly":
                    local_bus = str(ev['Bus_Node'])
                    local_v = voltage_dict.get(local_bus, 1.0)
                    new_kw = get_smart_charging_rate(local_v, step, ev)
                else:
                    new_kw = ev['Max_kW']
                ev['Current_kW_Draw'] = new_kw

            local_fleet.at[idx, 'Current_kWh'] = ev['Current_kWh']
            local_fleet.at[idx, 'Is_Plugged_In'] = ev['Is_Plugged_In']
            local_fleet.at[idx, 'Current_kW_Draw'] = ev['Current_kW_Draw']

            dss.text(f"Edit Load.{ev['EV_ID']} kW={ev['Current_kW_Draw']}")

    # --- 6. Post-Simulation Energy Deficit Extraction ---
    local_fleet['Deficit'] = local_fleet['Target_kWh'] - local_fleet['Current_kWh']
    undercharged_mask = local_fleet['Deficit'] > 0.1
    undercharged_count = undercharged_mask.sum()

    prob_undercharge = (undercharged_count / len(local_fleet)) * 100.0
    mean_deficit = local_fleet.loc[undercharged_mask, 'Deficit'].mean() if undercharged_count > 0 else 0.0

    return absolute_min_v, absolute_max_vuf, total_losses_kwh, tap_operations, temporal_creg1a, temporal_creg2a, step_losses_kw, prob_undercharge, mean_deficit


def run_monte_carlo():
    print(f"=== STARTING MONTE CARLO EVALUATION ===")
    print(f"Testing {NUM_ITERATIONS} Iterations at {NUM_EVS} EVs penetration.")

    dss = py_dss_interface.DSS()

    disorderly_v_fails, disorderly_vuf_fails = 0, 0
    orderly_v_fails, orderly_vuf_fails = 0, 0

    disorderly_losses, orderly_losses = [], []
    disorderly_max_vufs, orderly_max_vufs = [], []
    disorderly_min_volts, orderly_min_volts = [], []

    # Consumer Deficit Trackers
    disorderly_prob_uc, orderly_prob_uc = [], []
    disorderly_mean_def, orderly_mean_def = [], []

    # Tap Specific Trackers
    d_tap_ops_matrix = {r: [] for r in REGULATORS}
    o_tap_ops_matrix = {r: [] for r in REGULATORS}
    d_temporal_creg1a_matrix = []
    o_temporal_creg1a_matrix = []
    d_temporal_creg2a_matrix = []
    o_temporal_creg2a_matrix = []

    # Loss Specific Trackers
    d_step_losses_matrix = []
    o_step_losses_matrix = []

    for i in range(1, NUM_ITERATIONS + 1):
        print(f"Running Iteration {i}/{NUM_ITERATIONS} (Seed: {i})...")

        df_fleet = generate_ev_fleet(num_evs=NUM_EVS, seed=i)

        # --- DISORDERLY SCENARIO ---
        d_min_v, d_max_vuf, d_loss, d_tap_ops, d_temp_creg1a, d_temp_creg2a, d_step_loss, d_prob_uc, d_mean_def = run_single_simulation(
            "disorderly", df_fleet, dss)

        if d_min_v < 0.95: disorderly_v_fails += 1
        if d_max_vuf > 2.0: disorderly_vuf_fails += 1

        disorderly_losses.append(d_loss)
        disorderly_max_vufs.append(d_max_vuf)
        disorderly_min_volts.append(d_min_v)
        disorderly_prob_uc.append(d_prob_uc)
        disorderly_mean_def.append(d_mean_def)

        for r in REGULATORS: d_tap_ops_matrix[r].append(d_tap_ops[r])
        d_temporal_creg1a_matrix.append(d_temp_creg1a)
        d_temporal_creg2a_matrix.append(d_temp_creg2a)
        d_step_losses_matrix.append(d_step_loss)

        # --- ORDERLY SCENARIO ---
        o_min_v, o_max_vuf, o_loss, o_tap_ops, o_temp_creg1a, o_temp_creg2a, o_step_loss, o_prob_uc, o_mean_def = run_single_simulation(
            "orderly", df_fleet, dss)

        if o_min_v < 0.95: orderly_v_fails += 1
        if o_max_vuf > 2.0: orderly_vuf_fails += 1

        orderly_losses.append(o_loss)
        orderly_max_vufs.append(o_max_vuf)
        orderly_min_volts.append(o_min_v)
        orderly_prob_uc.append(o_prob_uc)
        orderly_mean_def.append(o_mean_def)

        for r in REGULATORS: o_tap_ops_matrix[r].append(o_tap_ops[r])
        o_temporal_creg1a_matrix.append(o_temp_creg1a)
        o_temporal_creg2a_matrix.append(o_temp_creg2a)
        o_step_losses_matrix.append(o_step_loss)

    # --- CALCULATE SUMMARY STATISTICS ---
    avg_d_loss = np.mean(disorderly_losses) if disorderly_losses else 0.0
    avg_o_loss = np.mean(orderly_losses)
    avg_d_vuf = np.mean(disorderly_max_vufs) if disorderly_max_vufs else 0.0
    avg_o_vuf = np.mean(orderly_max_vufs)

    # 95% Confidence Interval Multiplier (Z-score)
    Z_95 = 1.96

    # Probability of Failure (PoF) metrics
    pof_d_v = (disorderly_v_fails / NUM_ITERATIONS) * 100
    pof_d_vuf = (disorderly_vuf_fails / NUM_ITERATIONS) * 100
    pof_o_v = (orderly_v_fails / NUM_ITERATIONS) * 100
    pof_o_vuf = (orderly_vuf_fails / NUM_ITERATIONS) * 100

    # PoF Binomial Confidence Intervals
    def calc_binomial_ci(pof_pct, n):
        p = pof_pct / 100.0
        se = np.sqrt((p * (1.0 - p)) / n) if n > 0 else 0.0
        return (Z_95 * se) * 100.0

    ci_d_v = calc_binomial_ci(pof_d_v, NUM_ITERATIONS)
    ci_d_vuf = calc_binomial_ci(pof_d_vuf, NUM_ITERATIONS)
    ci_o_v = calc_binomial_ci(pof_o_v, NUM_ITERATIONS)
    ci_o_vuf = calc_binomial_ci(pof_o_vuf, NUM_ITERATIONS)

    # Consumer Deficit Aggregation & Standard Error CIs
    avg_d_prob_uc = np.mean(disorderly_prob_uc) if disorderly_prob_uc else 0.0
    ci_d_prob_uc = Z_95 * (np.std(disorderly_prob_uc, ddof=1) / np.sqrt(
        NUM_ITERATIONS)) if disorderly_prob_uc and NUM_ITERATIONS > 1 else 0.0

    avg_d_mean_def = np.mean(disorderly_mean_def) if disorderly_mean_def else 0.0
    ci_d_mean_def = Z_95 * (np.std(disorderly_mean_def, ddof=1) / np.sqrt(
        NUM_ITERATIONS)) if disorderly_mean_def and NUM_ITERATIONS > 1 else 0.0

    avg_o_prob_uc = np.mean(orderly_prob_uc)
    ci_o_prob_uc = Z_95 * (np.std(orderly_prob_uc, ddof=1) / np.sqrt(NUM_ITERATIONS)) if NUM_ITERATIONS > 1 else 0.0

    avg_o_mean_def = np.mean(orderly_mean_def)
    ci_o_mean_def = Z_95 * (np.std(orderly_mean_def, ddof=1) / np.sqrt(NUM_ITERATIONS)) if NUM_ITERATIONS > 1 else 0.0

    # Aggregate Mean Tap Operations for CSV
    mean_d_tap_ops = sum(np.mean(d_tap_ops_matrix[r]) for r in REGULATORS) if d_tap_ops_matrix[REGULATORS[0]] else 0.0
    mean_o_tap_ops = sum(np.mean(o_tap_ops_matrix[r]) for r in REGULATORS)

    # Extract Mean Array Vectors for Temporal Tracking
    mean_d_step_losses = np.mean(d_step_losses_matrix, axis=0) if d_step_losses_matrix else []
    mean_o_step_losses = np.mean(o_step_losses_matrix, axis=0)
    mean_d_creg1a = np.mean(d_temporal_creg1a_matrix, axis=0) if d_temporal_creg1a_matrix else []
    mean_o_creg1a = np.mean(o_temporal_creg1a_matrix, axis=0)
    mean_d_creg2a = np.mean(d_temporal_creg2a_matrix, axis=0) if d_temporal_creg2a_matrix else []
    mean_o_creg2a = np.mean(o_temporal_creg2a_matrix, axis=0)

    # Convert tap operations to simple lists for export
    mean_d_tap_ops_array = [np.mean(d_tap_ops_matrix[r]) for r in REGULATORS] if d_tap_ops_matrix[REGULATORS[0]] else []
    mean_o_tap_ops_array = [np.mean(o_tap_ops_matrix[r]) for r in REGULATORS]

    # --- CSV EXPORT (SUMMARY ONLY) ---
    csv_filename = f"MonteCarlo_Summary_{NUM_EVS}EVs.csv"
    with open(csv_filename, 'w') as f:
        f.write("--- SUMMARY STATISTICS ---\n")
        f.write(f"Runs,{NUM_ITERATIONS},EVs,{NUM_EVS}\n")
        # Added CI columns to the header
        f.write(
            "Scenario,Voltage_PoF_%,95CI_V_+,VUF_PoF_%,95CI_VUF_+,Mean_Max_VUF_%,Avg_System_Losses_kWh,Mean_Total_Tap_Ops,Prob_Undercharge_%,95CI_Undercharge_+,Mean_Deficit_kWh,95CI_Deficit_+\n")

        if disorderly_losses:
            f.write(
                f"Disorderly,{pof_d_v:.1f},{ci_d_v:.2f},{pof_d_vuf:.1f},{ci_d_vuf:.2f},{avg_d_vuf:.3f},{avg_d_loss:.1f},{mean_d_tap_ops:.1f},{avg_d_prob_uc:.2f},{ci_d_prob_uc:.3f},{avg_d_mean_def:.3f},{ci_d_mean_def:.3f}\n")
        else:
            f.write(f"Disorderly,N/A,N/A,N/A,N/A,N/A,N/A,N/A,0.00,0.000,0.000,0.000\n")

        f.write(
            f"Orderly,{pof_o_v:.1f},{ci_o_v:.2f},{pof_o_vuf:.1f},{ci_o_vuf:.2f},{avg_o_vuf:.3f},{avg_o_loss:.1f},{mean_o_tap_ops:.1f},{avg_o_prob_uc:.2f},{ci_o_prob_uc:.3f},{avg_o_mean_def:.3f},{ci_o_mean_def:.3f}\n")

    print(f"\nSummary results saved to: {csv_filename}")
    print(f"DIAGNOSTIC CHECK: Disorderly Prob Undercharge is {avg_d_prob_uc:.2f}% (Must be 0.00%)")

    # --- NUMPY EXPORT FOR MASTER PLOTTER ---
    export_filename = f"SimulationData_{NUM_EVS}EVs_{NUM_ITERATIONS}.npz"
    np.savez(export_filename,
             num_evs=NUM_EVS,
             iterations=NUM_ITERATIONS,
             regulators=REGULATORS,
             d_min_volts=disorderly_min_volts if disorderly_min_volts else [0.0],
             o_min_volts=orderly_min_volts,
             d_mean_step_losses=mean_d_step_losses if len(mean_d_step_losses) > 0 else np.zeros(288),
             o_mean_step_losses=mean_o_step_losses,
             d_mean_tap_ops=mean_d_tap_ops_array if len(mean_d_tap_ops_array) > 0 else np.zeros(len(REGULATORS)),
             o_mean_tap_ops=mean_o_tap_ops_array,
             d_mean_creg1a=mean_d_creg1a if len(mean_d_creg1a) > 0 else np.zeros(288),
             o_mean_creg1a=mean_o_creg1a,
             d_mean_creg2a=mean_d_creg2a if len(mean_d_creg2a) > 0 else np.zeros(288),
             o_mean_creg2a=mean_o_creg2a)

    print(f"Raw array data exported successfully to: {export_filename}")
    print("Execution Complete.")


if __name__ == "__main__":
    run_monte_carlo()
