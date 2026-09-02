import pyvisa
import numpy as np
import matplotlib.pyplot as plt

# --- 1) Open GPIB connection ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')
inst.timeout           = 10000  # ms
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Configure the Keithley 2400 for a 0–10 V I–V sweep ---
inst.write('*RST')
inst.write(':SENS:FUNC:CONC OFF')
inst.write(':SOUR:FUNC VOLT')
inst.write(':SENS:FUNC "CURR:DC"')
inst.write(':SENS:CURR:PROT 0.1')
inst.write(':FORM:ELEM CURR')

# sweep parameters
start_v, stop_v, step_v = 0, 10, 1 # starts at 0v -> 10v step size 1v
npts = int((stop_v - start_v) / step_v) + 1

inst.write(f':SOUR:VOLT:START {start_v}')
inst.write(f':SOUR:VOLT:STOP  { stop_v}')
inst.write(f':SOUR:VOLT:STEP { step_v}')
inst.write(':SOUR:VOLT:MODE SWE')
inst.write(':SOUR:SWE:RANG AUTO')
inst.write(':SOUR:SWE:SPAC LIN')
inst.write(f':TRIG:COUN {npts}')
inst.write(':SOUR:DEL 0.1')

# --- 3) Run sweep and read back current data ---
inst.write(':OUTP ON')
data_str = inst.query(':READ?')
inst.write(':OUTP OFF')

# --- 4) Parse, filter, convert to floats, build voltage array ---
parts    = [s for s in data_str.strip().split(',') if s.strip()]
currents = np.array([float(v) for v in parts])
voltages = np.linspace(start_v, stop_v, npts)

# --- 5) Compute per‐point resistance (skip V=0) and average ---
mask = voltages != 0
resistances = voltages[mask] / currents[mask]    # R = V/I
avg_R = resistances.mean()

print(f"Average resistance (1–10 V): {avg_R:.3e} Ω")

# --- 6) Plot I–V curve ---
plt.figure()
plt.plot(voltages, currents, 'o-', label='I vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Current (A)')
plt.title('I–V Curve')
plt.grid(True)

# --- 7) Plot Resistance vs Voltage ---
plt.figure()
plt.plot(voltages[mask], resistances, 'o-', label='R vs V')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title(f'Resistance vs Voltage (Avg R ≈ {avg_R:.3e} Ω)')
plt.grid(True)

plt.show()

# --- 8) Clean up ---
inst.close()
rm.close()
