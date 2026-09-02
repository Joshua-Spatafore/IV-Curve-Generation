import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time

# --- 0) Get user inputs ---
print("Channel A sweep parameters:")
start_A   = float(input("  Start voltage A (V): "))
stop_A    = float(input("  Stop  voltage A (V): "))
step_A    = float(input("  Step  size A (V): "))
print("\nChannel B sweep parameters:")
start_B   = float(input("  Start voltage B (V): "))
stop_B    = float(input("  Stop  voltage B (V): "))
step_B    = float(input("  Step  size B (V): "))
n_samples = int(  input("\n# of readings per voltage step (both channels): ") )

# Build voltage arrays
npts_A   = int((stop_A - start_A) / step_A) + 1
volt_A   = np.linspace(start_A, stop_A, npts_A)
npts_B   = int((stop_B - start_B) / step_B) + 1
volt_B   = np.linspace(start_B, stop_B, npts_B)

# --- 1) Open GPIB connection ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust GPIB address if needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset & configure both SMUs for voltage source + current measure ---
inst.write('*RST')
for ch in ('smua','smub'):
    inst.write(f'{ch}.source.func        = {ch}.OUTPUT_DCVOLTS')
    inst.write(f'{ch}.source.limiti      = 0.1')             # 100 mA compliance
    inst.write(f'{ch}.measure.autorangei = {ch}.AUTORANGE_ON')

# --- 3) Turn on outputs ---
inst.write('smua.source.output = 1')
inst.write('smub.source.output = 1')

# --- 4) Sweep Channel A ---
avg_I_A = []
for v in volt_A:
    inst.write(f'smua.source.levelv = {v}')
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)
        raw = inst.query('print(smua.measure.i())')
        readings.append(float(raw.strip()))
    avg_I_A.append(sum(readings) / n_samples)
avg_I_A = np.array(avg_I_A)

# --- 5) Sweep Channel B ---
avg_I_B = []
for v in volt_B:
    inst.write(f'smub.source.levelv = {v}')
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)
        raw = inst.query('print(smub.measure.i())')
        readings.append(float(raw.strip()))
    avg_I_B.append(sum(readings) / n_samples)
avg_I_B = np.array(avg_I_B)

# --- 6) Turn off outputs ---
inst.write('smua.source.output = 0')
inst.write('smub.source.output = 0')

# --- 7) Compute resistances (skip zero voltage points) ---
mask_A = volt_A != 0
R_A    = volt_A[mask_A] / avg_I_A[mask_A]
mask_B = volt_B != 0
R_B    = volt_B[mask_B] / avg_I_B[mask_B]

# --- 8) Plot Channel A I–V ---
plt.figure()
plt.plot(volt_A, avg_I_A, 'o-')
plt.xlabel('Voltage A (V)')
plt.ylabel('Current A (A)')
plt.title(f'Channel A I–V ({n_samples}× avg)')
plt.grid(True)

# --- 9) Plot Channel A R–V ---
plt.figure()
plt.plot(volt_A[mask_A], R_A, 'o-')
plt.xlabel('Voltage A (V)')
plt.ylabel('Resistance A (Ω)')
plt.title('Channel A R–V')
plt.grid(True)

# --- 10) Plot Channel B I–V ---
plt.figure()
plt.plot(volt_B, avg_I_B, 's-')
plt.xlabel('Voltage B (V)')
plt.ylabel('Current B (A)')
plt.title(f'Channel B I–V ({n_samples}× avg)')
plt.grid(True)

# --- 11) Plot Channel B R–V ---
plt.figure()
plt.plot(volt_B[mask_B], R_B, 's-')
plt.xlabel('Voltage B (V)')
plt.ylabel('Resistance B (Ω)')
plt.title('Channel B R–V')
plt.grid(True)

plt.show()

# --- 12) Clean up ---
inst.close()
rm.close()
