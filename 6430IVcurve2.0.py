#Joshua Spatafore R11874738 warmup for 30 min 
#this code allows you to sweep back to your original start position
import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time

# --- 0) Get user inputs for sweep parameters ---
start_v    = float(input("Enter start voltage (V): "))
stop_v     = float(input("Enter stop voltage (V): "))
step_v     = float(input("Enter step size (V): "))
n_samples  = int(input("Enter number of readings per voltage step: "))
n_discard_start = int(input("Enter number of readings to discard at START of each step: "))
n_discard_end   = int(input("Enter number of readings to discard at END of each step: "))

if n_discard_start + n_discard_end >= n_samples:
    raise ValueError("Total number of discarded readings must be less than total number of samples.")

comp_limit = float(input("Enter current compliance (A), e.g. 1e-9: "))
curr_range_input = input("Enter current measurement range (A), e.g. 1e-12 for pA (or 'auto' for auto-range): ").strip().lower()
sweep_back = input("Sweep back from stop to start? [y/n]: ").strip().lower().startswith('y')

if curr_range_input in ("auto", "0"):
    use_auto_range = True
else:
    try:
        curr_range = float(curr_range_input)
        use_auto_range = False
    except ValueError:
        raise ValueError("Invalid current range input. Enter a number (e.g. 1e-12) or 'auto'.")

# Build the voltage array (inclusive of stop_v)
num_pts = int((stop_v - start_v) / step_v) + 1
voltages_up = np.linspace(start_v, stop_v, num_pts)

# For the down sweep, avoid immediately repeating the stop point
voltages_down = voltages_up[-2::-1] if sweep_back and len(voltages_up) > 1 else np.array([])

# --- 1) Open GPIB connection to the 6430 ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust address as needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset and configure 6430 for V-source, I-sense ---
inst.write("*RST")
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {voltages_up[0]}")
inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
inst.write(":FORM:ELEM CURR")
inst.write(":OUTP ON")

if use_auto_range:
    inst.write(":SENS:CURR:RANGE:AUTO ON")
else:
    inst.write(":SENS:CURR:RANGE:AUTO OFF")
    inst.write(f":SENS:CURR:RANGE {curr_range}")

def sweep_and_average(v_array):
    avg_I = []
    for v in v_array:
        inst.write(f":SOUR:VOLT {v}")
        readings = []
        for _ in range(n_samples):
            time.sleep(0.1)
            readings.append(float(inst.query(":MEAS:CURR:DC?")))
        trimmed = readings[n_discard_start : n_samples - n_discard_end]
        avg_I.append(np.mean(trimmed))
    return np.array(avg_I)

# --- 3) Run sweeps ---
avg_I_up = sweep_and_average(voltages_up)
avg_I_down = sweep_and_average(voltages_down) if sweep_back else np.array([])

# Drive back to 0 V and turn off
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")

# --- 4) Compute R–V data & averages (combine for stats) ---
def rv(vs, Is):
    mask = vs != 0
    return vs[mask], (vs[mask] / Is[mask]) if mask.any() else np.array([])

v_r_up, R_up = rv(voltages_up, avg_I_up)
v_r_down, R_down = rv(voltages_down, avg_I_down) if sweep_back else (np.array([]), np.array([]))

resistances_all = np.concatenate([R_up, R_down]) if sweep_back else R_up
avg_R = resistances_all.mean() if resistances_all.size else np.nan
if resistances_all.size > 2:
    sorted_R   = np.sort(resistances_all)
    norm_avg_R = sorted_R[1:-1].mean()
else:
    norm_avg_R = avg_R

# --- 5) Plot I–V curve ---
plt.figure()
plt.plot(voltages_up,   avg_I_up,   'o-', label='Sweep up')
if sweep_back and avg_I_down.size:
    plt.plot(voltages_down, avg_I_down, 's-', label='Sweep down')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
mode = "Auto-range" if use_auto_range else f"Fixed-range ({curr_range_input})"
plt.title(f'I–V Curve ({mode}, {n_samples} samples, discard {n_discard_start}+{n_discard_end})')
plt.legend()
plt.grid(True)
plt.show()

# --- 6) Plot Resistance vs Voltage with averages ---
plt.figure()
if R_up.size:
    plt.plot(v_r_up, R_up, 'o-', label='Sweep up')
if sweep_back and R_down.size:
    plt.plot(v_r_down, R_down, 's-', label='Sweep down')
if np.isfinite(avg_R):
    plt.axhline(avg_R,      linestyle='--', label=f'Avg R ≈ {avg_R:.3e} Ω')
if np.isfinite(norm_avg_R):
    plt.axhline(norm_avg_R, linestyle=':',  label=f'Norm Avg R ≈ {norm_avg_R:.3e} Ω')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title('Resistance vs Voltage')
plt.legend()
plt.grid(True)
plt.show()

# --- 7) Build and show results table (with sweep label) ---
headers = ['Sweep', 'Voltage (V)', 'Avg Current (A)', 'Resistance (Ω)']
rows = []

def calc_R(v, I):
    if v == 0 or not np.isfinite(I) or I == 0:
        return np.nan
    return v / I

for v, I in zip(voltages_up, avg_I_up):
    R = calc_R(v, I)
    rows.append(['Up', f"{v:.6f}", f"{I:.6e}", f"{R:.6e}" if np.isfinite(R) else "NaN"])

if sweep_back and avg_I_down.size:
    for v, I in zip(voltages_down, avg_I_down):
        R = calc_R(v, I)
        rows.append(['Down', f"{v:.6f}", f"{I:.6e}", f"{R:.6e}" if np.isfinite(R) else "NaN"])

fig, ax = plt.subplots(figsize=(9, len(rows) * 0.3 + 1.2))
ax.axis('off')
table = ax.table(cellText=rows, colLabels=headers, loc='center')
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 1.5)
plt.title('IV Sweep Results Table', pad=20)
plt.tight_layout()
plt.show()

# --- 8) Clean up ---
inst.close()
rm.close()