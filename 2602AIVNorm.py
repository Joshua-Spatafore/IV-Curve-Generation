import pyvisa
import numpy as np
import matplotlib.pyplot as plt

# --- 0) Get user inputs for sweep parameters ---
start_v    = float(input("Enter start voltage (V): "))
stop_v     = float(input("Enter stop voltage (V): "))
step_v     = float(input("Enter step size (V): "))
n_samples  = int(  input("Enter number of readings per voltage step: ") )

# Build the voltage array (inclusive of stop_v)
num_pts = int((stop_v - start_v) / step_v) + 1
voltages = np.linspace(start_v, stop_v, num_pts)

# --- 1) Open GPIB connection to the 2602A ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust address if needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset and configure SMU B ---
inst.write('*RST')
inst.write('smub.source.func = smub.OUTPUT_DCVOLTS')
inst.write('smub.source.limiti = 0.1')             # 0.1 A compliance
inst.write('smub.measure.autorangei = smub.AUTORANGE_ON')

# --- 3) Sweep loop: take n_samples readings per voltage and average ---
avg_currents = []
inst.write('smub.source.output = 1')
for v in voltages:
    inst.write(f'smub.source.levelv = {v}')
    readings = []
    for _ in range(n_samples):
        inst.write('delay(0.1)')
        raw = inst.query('print(smub.measure.i())')
        readings.append(float(raw.strip()))
    avg_currents.append(sum(readings)/n_samples)

inst.write('smub.source.levelv = 0')
inst.write('smub.source.output = 0')

# --- 4) Compute R–V data & averages ---
avg_currents = np.array(avg_currents)
mask = voltages != 0
resistances = voltages[mask] / avg_currents[mask]

# raw average
avg_R = resistances.mean()

# “normalized” average (exclude the single lowest & highest)
sorted_R   = np.sort(resistances)
trimmed_R  = sorted_R[1:-1]
norm_avg_R = trimmed_R.mean()

# --- 5) Print results ---
print("\n   V (V)       |   Avg I (A)     |      R (Ω)")
print("------------------------------------------------")
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    print(f"{v:10.6f} | {I:14.6e} | {R:14.6e}")
print(f"\nAverage R (over {voltages[mask][0]:.6f}–{voltages[mask][-1]:.6f} V): {avg_R:.3e} Ω")
print(f"Normalized Average R (excl. highest & lowest): {norm_avg_R:.3e} Ω\n")

# --- 6) Plot I–V curve ---
plt.figure()
plt.plot(voltages, avg_currents, 'o-', label='I vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(f'I–V Curve ({n_samples}× Averaged)')
plt.grid(True)

# --- 7) Plot R–V curve ---
plt.figure()
plt.plot(voltages[mask], resistances, 'o-', label='R vs V')
plt.axhline(avg_R,      linestyle='--', label=f'Avg R ≈ {avg_R:.3e} Ω')
plt.axhline(norm_avg_R, linestyle=':',  label=f'Norm Avg R ≈ {norm_avg_R:.3e} Ω')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title('Resistance vs Voltage')
plt.legend()
plt.grid(True)

# --- 8) Table Figure: Voltage, Current, Resistance ---
plt.figure()
plt.axis('off')  # Hide axes
plt.title('Measurement Table (V, I, R)', fontsize=12)

# Prepare table data
table_data = [["V (V)", "I (A)", "R (Ω)"]]
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    table_data.append([f"{v:.3f}", f"{I:.3e}", f"{R:.3e}"])

# Draw table
table = plt.table(cellText=table_data, loc='center', cellLoc='center', colWidths=[0.2, 0.3, 0.3])
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1.2, 1.2)

plt.tight_layout()

# --- 9) Show all plots ---
plt.show()

# --- 10) Clean up ---
inst.close()
rm.close()

