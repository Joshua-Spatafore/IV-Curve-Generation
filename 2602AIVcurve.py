# Joshua Spatafore R11874738 please keep in mind that 2602A must warm up for two hours
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
# --- 2) Reset and configure SMU B for a voltage sweep with current measurement ---
inst.write('*RST')
inst.write('smub.source.func = smub.OUTPUT_DCVOLTS')
inst.write('smub.source.limiti = 0.1')             # 0.1 A compliance
inst.write('smub.measure.autorangei = smub.AUTORANGE_ON')
# --- 3) Sweep loop: for each voltage, take n_samples readings and average ---
avg_currents = []
inst.write('smub.source.output = 1')
for v in voltages:
    inst.write(f'smub.source.levelv = {v}')
    readings = []
    for _ in range(n_samples):
        inst.write('delay(0.1)')
        raw = inst.query('print(smub.measure.i())')
        readings.append(float(raw.strip()))
    avg_I = sum(readings) / n_samples
    avg_currents.append(avg_I)
inst.write('smub.source.levelv = 0')
inst.write('smub.source.output = 0')
# --- 4) Compute per-point resistance (skip V=0) and overall average ---
avg_currents = np.array(avg_currents)
mask = voltages != 0
resistances = voltages[mask] / avg_currents[mask]
avg_R = resistances.mean()
# --- 5) Print results ---
print("\n   V (V)       |   Avg I (A)     |      R (Ω)")
print("------------------------------------------------")
for v, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    print(f"{v:10.6f} | {I:14.6e} | {R:14.6e}")
print(f"\nAverage R (over {voltages[mask][0]:.6f}–{voltages[mask][-1]:.6f} V): {avg_R:.3e} Ω\n")
# --- 6) Plot I–V and R–V curves ---
plt.figure()
plt.plot(voltages, avg_currents, 'o-', label='I vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(f'I–V Curve ({n_samples}× Averaged)')
plt.grid(True)

plt.figure()
plt.plot(voltages[mask], resistances, 'o-', label='R vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title(f'Resistance vs Voltage (Avg R ≈ {avg_R:.3e} Ω)')
plt.grid(True)

plt.show()
# --- 7) Clean up ---
inst.close()
rm.close()