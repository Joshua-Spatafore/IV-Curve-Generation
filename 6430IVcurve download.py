import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time

# --- 0) Get user inputs for sweep parameters ---
start_v    = float(input("Enter start voltage (V): "))
stop_v     = float(input("Enter stop voltage (V): "))
step_v     = float(input("Enter step size (V): "))
n_samples  = int(input("Enter number of readings per voltage step: "))
comp_limit = float(input("Enter current compliance (A), e.g. 1e-9: "))

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
inst.write(":SOUR:FUNC VOLT")                        # voltage source mode
inst.write(f":SOUR:VOLT {voltages[0]}")               # initial voltage
inst.write(":SENS:FUNC 'CURR:DC'")                    # measure DC current
inst.write(f":SENS:CURR:PROT {comp_limit}")           # set current compliance
inst.write(":SENS:CURR:RANGE:AUTO ON")                # auto-range current
inst.write(":FORM:ELEM CURR")                        # only return the current value
inst.write(":OUTP ON")

# --- 3) Sweep loop: take n_samples readings per voltage and average ---
avg_currents = []
for v in voltages:
    inst.write(f":SOUR:VOLT {v}")
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)                     # let source settle
        raw = inst.query(":MEAS:CURR:DC?")  # returns just one number now
        readings.append(float(raw))
    avg_currents.append(np.mean(readings))

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
# "normalized" average (exclude the single lowest & highest)
sorted_R   = np.sort(resistances)
trimmed_R  = sorted_R[1:-1]
norm_avg_R = trimmed_R.mean()

# --- 5) Plot and save I–V curve ---
fig1 = plt.figure()
plt.plot(voltages, avg_currents, 'o-')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(f'I–V Curve ({n_samples}× Averaged)')
plt.grid(True)
fig1.savefig('iv_curve.png', dpi=300, bbox_inches='tight')
plt.show()

# --- 6) Plot and save Resistance vs Voltage with averages ---
fig2 = plt.figure()
plt.plot(voltages[mask], resistances, 'o-')
plt.axhline(avg_R,      linestyle='--', label=f'Avg R ≈ {avg_R:.3e} Ω')
plt.axhline(norm_avg_R, linestyle=':',  label=f'Norm Avg R ≈ {norm_avg_R:.3e} Ω')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title('Resistance vs Voltage')
plt.legend()
plt.grid(True)
fig2.savefig('resistance_curve.png', dpi=300, bbox_inches='tight')
plt.show()

# --- 7) Build, plot, and save results table as figure (no pandas) ---
headers = ['Voltage (V)', 'Avg Current (A)', 'Resistance (Ω)']
rows = []
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    rows.append([f"{v:.6f}", f"{I:.6e}", f"{R:.6e}"])

fig3, ax = plt.subplots(figsize=(8, len(rows) * 0.3 + 1))
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
fig3.savefig('results_table.png', dpi=300, bbox_inches='tight')
plt.show()

# --- 8) Clean up ---
inst.close()
rm.close()
