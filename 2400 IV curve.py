import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time

# --- 0) Get sweep parameters from the user ---
start_v   = float(input("Enter start voltage (V): "))
stop_v    = float(input("Enter stop voltage (V): "))
step_v    = float(input("Enter step size    (V): "))
n_samples = int(  input("Enter # of readings per step: ") )

# Build the list of voltages (inclusive of stop_v)
num_pts = int((stop_v - start_v) / step_v) + 1
voltages = np.linspace(start_v, stop_v, num_pts)

# --- 1) Open GPIB connection to the 2400 ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # change address if needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset & configure the 2400 for voltage sourcing + current measurement ---
inst.write('*RST')
inst.write(':SENS:FUNC:CONC OFF')
inst.write(':SOUR:FUNC VOLT')
inst.write(':SENS:FUNC "CURR:DC"')
inst.write(':SENS:CURR:PROT 0.1')   # 0.1 A compliance
inst.write(':FORM:ELEM CURR')

# --- 3) Step through each voltage, take n_samples readings, average them ---
avg_currents = []

inst.write(':OUTP ON')
for v in voltages:
    inst.write(f':SOUR:VOLT {v}')   # set the source voltage in TSP
    time.sleep(0.1)                  # allow settling (adjust if needed)

    readings = []
    for _ in range(n_samples):
        raw = inst.query(':READ?')     # trigger & read current once
        readings.append(float(raw.strip()))
        # optional small pause if you want:
        # time.sleep(0.05)

    avg_I = sum(readings) / n_samples
    avg_currents.append(avg_I)

inst.write(':OUTP OFF')

avg_currents = np.array(avg_currents)

# --- 4) Compute resistances (skip V=0) and average resistance ---
mask = voltages != 0
resistances = voltages[mask] / avg_currents[mask]
avg_R = resistances.mean()

# --- 5) Print a table of results ---
print("\n  V (V)   |  Avg I (A)   |  R (Ω)")
print("------------------------------------")
for V, I, R in zip(voltages[mask], avg_currents[mask], resistances):
    print(f"{V:7.2f} | {I:11.6e} | {R:11.6e}")
print(f"\nAverage resistance (over {start_v:.2f}→{stop_v:.2f} V): {avg_R:.3e} Ω\n")

# --- 6) Plot I–V and R–V curves ---
plt.figure()
plt.plot(voltages, avg_currents, 'o-', label='I vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(f'I–V Curve ({n_samples}× readings averaged)')
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