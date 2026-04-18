import numpy as np
import pandas as pd

# --- CORRECTED GRID DATA (28 Load-Serving Buses) ---
GRID_DATA = {
    '844': {'kW': 432.0, 'Phases': [1, 2, 3]},
    '890': {'kW': 300.0, 'Phases': [1, 2, 3]},
    '860': {'kW': 174.0, 'Phases': [1, 2, 3]},
    '834': {'kW': 89.0, 'Phases': [1, 2, 3]},
    '848': {'kW': 71.5, 'Phases': [1, 2, 3]},
    '836': {'kW': 61.0, 'Phases': [1, 2, 3]},
    '820': {'kW': 50.0, 'Phases': [1]},
    '830': {'kW': 48.5, 'Phases': [1, 2, 3]},
    '840': {'kW': 47.0, 'Phases': [1, 2, 3]},
    '822': {'kW': 40.0, 'Phases': [1]},
    '846': {'kW': 34.0, 'Phases': [2, 3]},
    '802': {'kW': 27.5, 'Phases': [2, 3]},
    '806': {'kW': 27.5, 'Phases': [2, 3]},
    '824': {'kW': 24.5, 'Phases': [2, 3]},
    '858': {'kW': 24.5, 'Phases': [1, 2, 3]},
    '826': {'kW': 20.0, 'Phases': [2]},
    '862': {'kW': 14.0, 'Phases': [2]},
    '838': {'kW': 14.0, 'Phases': [2]},
    '818': {'kW': 10.0, 'Phases': [1]},
    '808': {'kW': 8.0, 'Phases': [2]},
    '810': {'kW': 8.0, 'Phases': [2]},
    '832': {'kW': 7.5, 'Phases': [1, 2, 3]},
    '828': {'kW': 5.5, 'Phases': [1, 3]},
    '842': {'kW': 4.5, 'Phases': [1]},
    '816': {'kW': 2.5, 'Phases': [2, 3]},
    '854': {'kW': 2.0, 'Phases': [2]},
    '856': {'kW': 2.0, 'Phases': [2]},
    '864': {'kW': 1.0, 'Phases': [1]}
}


def generate_ev_fleet(num_evs=160, seed=42):
    """
    Generates a Pandas DataFrame containing the randomized stochastic parameters
    for the EV fleet, preparing the environment for V1G Fuzzy Control.
    Integrates socio-economic phase clustering (50% Ph1, 30% Ph2, 20% Ph3).
    """
    print(f"Generating Stochastic Fleet Database for {num_evs} EVs...")
    np.random.seed(seed)  # Fixed seed for Apples-to-Apples comparison later

    # Calculate Spatial Probabilities for Buses
    buses = list(GRID_DATA.keys())
    weights = np.array([GRID_DATA[b]['kW'] for b in buses])
    bus_probs = weights / weights.sum()

    # Define Socio-Economic Phase Clustering Weights
    phase_base_weights = {1: 0.4, 2: 0.35, 3: 0.25}

    fleet_data = []

    for i in range(num_evs):
        # 1. Location (Bus Selection)
        bus = np.random.choice(buses, p=bus_probs)

        # Phase Selection (Dynamic Normalisation)
        available_phases = GRID_DATA[bus]['Phases']
        extracted_weights = [phase_base_weights[p] for p in available_phases]
        total_weight = sum(extracted_weights)
        normalised_phase_probs = [w / total_weight for w in extracted_weights]

        phase = np.random.choice(available_phases, p=normalised_phase_probs)

        # 2. Timing (Arrival and Departure)
        arrival_hr = np.random.normal(loc=18.0, scale=1.0)
        # Prevent mathematically impossible early/late arrivals for this evening peak
        arrival_hr = max(12.0, min(23.5, arrival_hr))

        duration_hrs = np.random.randint(low=3, high=12)  # Random int: 3, 4, 5, 6, or 7 hours
        departure_hr = arrival_hr + duration_hrs

        # Convert to 10-minute steps (e.g., 18.5 hours = step 111)
        arrival_step = int(arrival_hr * 6)
        departure_step = int(departure_hr * 6)

        # 3. Battery and State of Charge (SOC)
        battery_capacity_kwh = 30.0
        max_kw = 7.2

        initial_soc = np.random.uniform(low=0.30, high=0.60)  # 30% to 60%
        target_soc = np.random.uniform(low=0.70, high=1.00)  # 70% to 100%

        initial_kwh = initial_soc * battery_capacity_kwh
        target_kwh = target_soc * battery_capacity_kwh

        # 4. MTOUCP Group Assignment (1, 2, or 3)
        mtoucp_group = np.random.choice([1, 2, 3])

        # Assemble EV Record
        ev_record = {
            'EV_ID': f"EV_{i + 1}",
            'Bus_Node': bus,
            'Phase': phase,
            'Max_kW': max_kw,
            'Battery_Capacity_kWh': battery_capacity_kwh,
            'Arrival_Step': arrival_step,
            'Departure_Step': departure_step,
            'Initial_SOC': round(initial_soc, 3),
            'Target_SOC': round(target_soc, 3),
            'Initial_kWh': round(initial_kwh, 2),
            'Target_kWh': round(target_kwh, 2),
            'MTOUCP_Group': mtoucp_group,
            # Dynamic Trackers (Will change during simulation)
            'Current_kWh': round(initial_kwh, 2),
            'Is_Plugged_In': False,
            'Current_kW_Draw': 0.0
        }
        fleet_data.append(ev_record)

    # Convert to Pandas DataFrame
    df_fleet = pd.DataFrame(fleet_data)

    # Save to CSV for inspection
    csv_filename = "Master_EV_Fleet.csv"
    df_fleet.to_csv(csv_filename, index=False)
    print(f"Fleet Database successfully saved to '{csv_filename}'.\n")

    return df_fleet


if __name__ == "__main__":
    # Test the generator
    fleet_db = generate_ev_fleet(num_evs=160, seed=1)

    # Display a sample to verify the data structure
    print("--- Sample of EV Fleet Database ---")
    columns_to_show = ['EV_ID', 'Bus_Node', 'Phase', 'Arrival_Step', 'Departure_Step', 'Initial_kWh', 'Target_kWh']
    print(fleet_db[columns_to_show].head(10).to_string(index=False))

    # Quick sanity check on MTOUCP and Phase distribution
    print("\n--- Phase Allocation Distribution ---")
    print(fleet_db['Phase'].value_counts(normalize=True).sort_index() * 100)