import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time

# --- 0) Get user inputs ---
start_v    = float(input("Enter start voltage (V): "))
stop_v     = float(input("Enter stop voltage (V): "))
step_v     = float(input("Enter step size (V): "))
n_samples  = int(input("Enter number of readings per voltage step: "))
comp_limit = float(input("Enter current compliance (A), e.g. 1e-9: "))

curr_range_input = input("Enter current measurement range (A), e.g. 1e-12 for pA (or 'auto'): ").strip().lower()
res_range_input  = input("Enter resistance measurement range (Ohms), e.g. 1e6 for 1MΩ (or 'auto'): ").strip().lower()

# --- Parse current range ---
if curr_range_input == "auto" or curr_range_input == "0":
    use_curr_auto_range = True
else:
    try:
        curr_range = float(curr_range_input)
        use_curr_auto_range = False
    except ValueError:
        raise ValueError("Invalid current range input.")

# --- Parse resistance range ---
if res_range_input == "auto" or res_range_input == "0":
    use_res_auto_range = True
else:
    try:
        res_range = float(res_range_input)
        use_res_auto_range = False
    except ValueError:
        raise ValueError("Invalid resistance range input.")

# Build the voltage array (inclusive of stop_v)
num_pts = int((stop_v - start_v) / step_v) + 1
voltages = np.linspace(start_v, stop_v, num_pts)

# --- 1) Open GPIB connection ---
rm = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Configure for voltage source and current measurement ---
inst.write("*RST")
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {voltages[0]}")
inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
if use_curr_auto_range:
    inst.write(":SENS:CURR:RANG:AUTO ON")
else:
    inst.write(f":SENS:CURR:RANG {curr_range}")
inst.write(":FORM:ELEM CURR")
inst.write(":OUTP ON")

# --- 3) Voltage sweep with current averaging ---
avg_currents = []
for v in voltages:
    inst.write(f":SOUR:VOLT {v}")
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)
        readings.append(float(inst.query(":MEAS:CURR:DC?")))
    avg_currents.append(np.mean(readings))

# Return to 0 V
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")

# --- 4) Measure resistance using built-in :MEAS:RES? ---
inst.write(":SOUR:FUNC VOLT")
inst.write(":SOUR:VOLT 1")
inst.write(":SENS:FUNC 'RES'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
if use_res_auto_range:
    inst.write(":SENS:RES:RANG:AUTO ON")
else:
    inst.write(f":SENS:RES:RANG {res_range}")
inst.write(":OUTP ON")
time.sleep(0.5)
measured_res = float(inst.query(":MEAS:RES?"))
inst.write(":OUTP OFF")

# --- 5) Calculate resistance from V/I (excluding V=0 to avoid divide-by-zero) ---
avg_currents = np.array(avg_currents)
mask = voltages != 0
resistances = voltages[mask] / avg_currents[mask]
avg_R = resistances.mean()
sorted_R = np.sort(resistances)
trimmed_R = sorted_R[1:-1]
norm_avg_R = trimmed_R.mean()

# --- 6) Plot I–V Curve ---
plt.figure()
plt.plot(voltages, avg_currents, 'o-')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(f'I–V Curve ({n_samples}× Averaged)')
plt.grid(True)
plt.show()

# --- 7) Plot Resistance vs Voltage + Measured Value ---
plt.figure()
plt.plot(voltages[mask], resistances, 'o-')
plt.axhline(avg_R, linestyle='--', label=f'Avg R ≈ {avg_R:.3e} Ω')
plt.axhline(norm_avg_R, linestyle=':', label=f'Norm Avg R ≈ {norm_avg_R:.3e} Ω')
plt.axhline(measured_res, linestyle='-.', label=f'Measured R ≈ {measured_res:.3e} Ω')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title('Resistance vs Voltage')
plt.legend()
plt.grid(True)
plt.show()

# --- 8) Results Table (No pandas) ---
headers = ['Voltage (V)', 'Avg Current (A)', 'Resistance (Ω)']
rows = []
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    rows.append([f"{v:.6f}", f"{I:.6e}", f"{R:.6e}"])

fig, ax = plt.subplots(figsize=(8, len(rows) * 0.3 + 1))
ax.axis('off')
table = ax.table(cellText=rows, colLabels=headers, loc='center')
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 1.5)
plt.title('IV Sweep Results Table', pad=20)
plt.tight_layout()
plt.show()

# --- 9) Cleanup ---
inst.close()
rm.close()