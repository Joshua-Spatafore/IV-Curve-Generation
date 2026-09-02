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

# --- fixed channels on 7158 ---
channels = [101, 102]

# Build the voltage array (inclusive of stop_v)
num_pts = int((stop_v - start_v) / step_v) + 1
voltages = np.linspace(start_v, stop_v, num_pts)

# --- 1) Open GPIB connection to the 6430 ---
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust address as needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# --- 2) Reset and configure 6430 for V‑source, I‑sense ---
inst.write("*RST")
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {voltages[0]}")
inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
inst.write(":FORM:ELEM CURR")
inst.write(":OUTP ON")

if use_auto_range:
    inst.write(":SENS:CURR:RANGE:AUTO ON")
else:
    inst.write(":SENS:CURR:RANGE:AUTO OFF")
    inst.write(f":SENS:CURR:RANGE {curr_range}")

# --- 3) Configure the 7001/7158 scanner on the 6430 ---
inst.write(":ROUT:SCAN:CARD 7158")
scan_str = "@(" + ",".join(str(ch) for ch in channels) + ")"
inst.write(f":ROUT:SCAN ({scan_str})")
inst.write(":ROUT:SCAN:STAT ON")

# --- 4) Sweep loop: one scan reading per channel per voltage ---
avg_currents = {ch: [] for ch in channels}

for v in voltages:
    inst.write(f":SOUR:VOLT {v}")
    readings = {ch: [] for ch in channels}
    for _ in range(n_samples):
        time.sleep(0.1)
        inst.write("INIT")
        data = inst.query_ascii_values("FETCH?")
        for ch, I in zip(channels, data):
            readings[ch].append(I)
    for ch in channels:
        raw = readings[ch]
        trimmed = raw[n_discard_start : n_samples - n_discard_end]
        avg_currents[ch].append(np.mean(trimmed))

# drive back to 0 V and turn off
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")
inst.close()
rm.close()

# --- 5) Compute resistances ---
res_data = {}
for ch in channels:
    I_arr = np.array(avg_currents[ch])
    mask = voltages != 0
    R = voltages[mask] / I_arr[mask]
    res_data[ch] = {
        "volt": voltages[mask],
        "I":     I_arr[mask],
        "R":     R,
        "avg_R":       R.mean(),
        "norm_avg_R":  np.sort(R)[1:-1].mean()
    }

# --- 6) Plot results for each probe ---
for ch in channels:
    d = res_data[ch]
    plt.figure()
    plt.plot(d["volt"], d["I"], 'o-')
    plt.xlabel('Voltage (V)')
    plt.ylabel('Current (A)')
    plt.title(f'Probe on Channel {ch}: I–V Curve')
    plt.grid(True)

    plt.figure()
    plt.plot(d["volt"], d["R"], 'o-')
    plt.axhline(d["avg_R"],      linestyle='--', label=f'Avg R ≈ {d["avg_R"]:.3e} Ω')
    plt.axhline(d["norm_avg_R"], linestyle=':',  label=f'Norm Avg R ≈ {d["norm_avg_R"]:.3e} Ω')
    plt.xlabel('Voltage (V)')
    plt.ylabel('Resistance (Ω)')
    plt.title(f'Probe on Channel {ch}: Resistance vs Voltage')
    plt.legend()
    plt.grid(True)

plt.show()
