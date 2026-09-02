#Joshua Spatafore R11874738 warmup for 30 min 
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
voltages = np.linspace(start_v, stop_v, num_pts)

# --- 1) Open GPIB connection to the 6430 ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust address as needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset and configure 6430 for V-source, I-sense ---
inst.write("*RST")
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {voltages[0]}")
inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
inst.write(":FORM:ELEM CURR")
inst.write(":OUTP ON")

if use_auto_range:
    # Full auto-range mode
    inst.write(":SENS:CURR:RANGE:AUTO ON")
else:
    # Fixed-range mode: disable auto-range first, then set the manual range
    inst.write(":SENS:CURR:RANGE:AUTO OFF")
    inst.write(f":SENS:CURR:RANGE {curr_range}")

# --- 3) Sweep loop: take n_samples readings, discard first/last readings ---
avg_currents = []
for v in voltages:
    inst.write(f":SOUR:VOLT {v}")
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)
        readings.append(float(inst.query(":MEAS:CURR:DC?")))
    trimmed = readings[n_discard_start : n_samples - n_discard_end]
    avg_currents.append(np.mean(trimmed))

# drive back to 0 V and turn off
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")

# --- 4) Compute R–V data & averages ---
avg_currents = np.array(avg_currents)
mask = voltages != 0
resistances = voltages[mask] / avg_currents[mask]

# raw average
avg_R = resistances.mean()
# normalized average (exclude the single lowest & highest)
sorted_R   = np.sort(resistances)
trimmed_R  = sorted_R[1:-1]
norm_avg_R = trimmed_R.mean()

# --- 5) Plot I–V curve ---
plt.figure()
plt.plot(voltages, avg_currents, 'o-')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
mode = "Auto-range" if use_auto_range else f"Fixed-range ({curr_range_input})"
plt.title(f'I–V Curve ({mode}, {n_samples} samples, discard {n_discard_start}+{n_discard_end})')
plt.grid(True)
plt.show()

# --- 6) Plot Resistance vs Voltage with averages ---
plt.figure()
plt.plot(voltages[mask], resistances, 'o-')
plt.axhline(avg_R,      linestyle='--', label=f'Avg R ≈ {avg_R:.3e} Ω')
plt.axhline(norm_avg_R, linestyle=':',  label=f'Norm Avg R ≈ {norm_avg_R:.3e} Ω')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title('Resistance vs Voltage')
plt.legend()
plt.grid(True)
plt.show()

# --- 7) Build and show results table as figure (no pandas) ---
headers = ['Voltage (V)', 'Avg Current (A)', 'Resistance (Ω)']
rows = []
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    rows.append([f"{v:.6f}", f"{I:.6e}", f"{R:.6e}"])

fig, ax = plt.subplots(figsize=(8, len(rows) * 0.3 + 1))
ax.axis('off')
table = ax.table(
    cellText=rows,
    colLabels=headers,
    loc='center'
)
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 1.5)
plt.title('IV Sweep Results Table', pad=20)
plt.tight_layout()
plt.show()

# --- 8) Clean up ---
inst.close()
rm.close()