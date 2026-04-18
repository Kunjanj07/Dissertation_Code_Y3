def get_smart_charging_rate(current_voltage_pu, current_step, ev_data):
    """
    Decentralized V1G Smart Controller for a single EV.
    Strictly implements Table I and Table II matrices from the literature.
    """
    target_kwh = ev_data['Target_kWh']
    current_kwh = ev_data['Current_kWh']
    departure_step = ev_data['Departure_Step']
    group = ev_data['MTOUCP_Group']

    if current_kwh >= target_kwh or current_step >= departure_step:
        return 0.0

    # --- SUB-STEP 2A: Power Draw Priority (PD) ---
    energy_needed = target_kwh - current_kwh
    hours_remaining = (departure_step - current_step) / 6.0
    required_kw = energy_needed / hours_remaining
    pd_score = required_kw / 7.2

    if pd_score < 0.2:
        priority = 'EL'
    elif pd_score < 0.4:
        priority = 'L'
    elif pd_score < 0.6:
        priority = 'M'
    elif pd_score < 0.8:
        priority = 'H'
    else:
        priority = 'EH'

    # --- SUB-STEP 2B: Voltage Categories (\Delta V) ---
    if current_voltage_pu < 0.950:
        v_cat = 'DL'
    elif current_voltage_pu < 0.952:
        v_cat = 'WL'
    elif current_voltage_pu < 0.980:
        v_cat = 'N'
    elif current_voltage_pu < 1.050:
        v_cat = 'WH'
    else:
        v_cat = 'DH'

    # --- SUB-STEP 2C: Grid Signal (TOU) ---
    hour_of_day = (current_step * 10) / 60.0
    release_hour = 23.0 if group == 1 else 24.0 if group == 2 else 25.0

    tou = "NC" if (18.0 <= hour_of_day < release_hour) else "CH"

    # --- SUB-STEP 2D: The Exact Matrices (From Paper Images) ---
    HC = 7.2  # High Charge
    LC = 3.6  # Low Charge
    Z_kw = 0.0  # Zero Charge

    if tou == "NC":
        # Applying TABLE II rules strictly
        if priority in ['EL', 'L', 'M']:
            return Z_kw
        elif priority == 'H':
            if v_cat in ['DL', 'WL']:
                return Z_kw
            elif v_cat == 'N':
                return LC
            elif v_cat in ['WH', 'DH']:
                return HC
        elif priority == 'EH':
            if v_cat == 'DL':
                return LC
            elif v_cat in ['WL', 'N', 'WH', 'DH']:
                return HC

    elif tou == "CH":
        # Applying TABLE I (Left side) rules strictly.
        # Grid safety net: If voltage drops to DL/WL off-peak, protect the grid.
        if v_cat in ['DL', 'WL']:
            if priority == 'EH':
                return LC
            else:
                return Z_kw

        # Normal Table I (Left) implementation
        if priority in ['EL', 'L']:
            if v_cat in ['N', 'WH']:
                return LC
            elif v_cat == 'DH':
                return HC
        elif priority == 'M':
            if v_cat == 'N':
                return LC
            elif v_cat in ['WH', 'DH']:
                return HC
        elif priority in ['H', 'EH']:
            return HC

    return Z_kw


if __name__ == "__main__":
    print("Logic Engine successfully updated with Table I & II matrices.")