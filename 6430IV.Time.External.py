# takes a set voltage and measueres current every x ms
import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time, math, csv, os
from datetime import datetime
import pandas as pd

# ==============================
# User inputs
# ==============================
V_set          = float(input("Voltage to apply (V): "))
total_minutes  = float(input("Total time (minutes): "))
period_ms      = float(input("Reading period (ms), e.g. 200 for 200 ms: "))
comp_limit     = float(input("Current compliance (A), e.g. 1e-7: "))
curr_range_in  = input("Fixed current range (A), e.g. 1e-9: ").strip()
nplc           = float(input("Integration time in PLC (e.g. 1.0): "))

if total_minutes <= 0:
    raise ValueError("Total time must be > 0")
if period_ms <= 0:
    raise ValueError("Reading period must be > 0 ms")

period_s      = period_ms / 1000.0
total_seconds = total_minutes * 60.0
n_points_est  = int(math.floor(total_seconds / period_s)) + 1

# ==============================
# Output directory
# ==============================
save_dir = r"D:\school\Lab work\iv figures\excel"
os.makedirs(save_dir, exist_ok=True)
run_tag   = datetime.now().strftime("%Y%m%d_%H%M%S")
base_name = f"hold_stream_{V_set:.3f}V_{int(total_minutes)}min_{int(period_ms)}ms_{n_points_est}pts_{run_tag}".replace('.', 'p')
csv_path  = os.path.join(save_dir, base_name + ".csv")
xlsx_path = os.path.join(save_dir, base_name + ".xlsx")

# ==============================
# VISA / 6430 setup
# ==============================
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')
inst.timeout           = 60000
inst.write_termination = '\n'
inst.read_termination  = '\n'

inst.write("*RST")
inst.write(":ABOR")
inst.write("*CLS")

# Configure source and measurement
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {V_set}")
inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
inst.write(f":SENS:CURR:NPLC {nplc}")
inst.write(":FORM:ELEM CURR")

# ==============================
# Force fixed current range
# ==============================
try:
    curr_range = float(curr_range_in)
except ValueError:
    raise ValueError("Enter numeric current range in amps. Autorange disabled.")
inst.write(":SENS:CURR:RANGE:AUTO OFF")
inst.write(f":SENS:CURR:RANGE {curr_range}")
print(f"Fixed current range locked to {curr_range} A")

# Enable output and settle
inst.write(":OUTP ON")
time.sleep(0.25)

# ==============================
# Acquisition loop
# ==============================
records = []
t0 = time.monotonic()
t_start_iso = datetime.now().isoformat(timespec="seconds")

with open(csv_path, "w", newline="") as f_csv:
    w = csv.writer(f_csv)
    w.writerow(["index","timestamp_iso","elapsed_s","V_set(V)","I(A)","period_s","NPLC"])
    k = 0
    while True:
        target = t0 + k * period_s
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)

        I_val = float(inst.query(":MEAS:CURR:DC?"))
        elapsed_s = time.monotonic() - t0

        rec = {
            "index": k + 1,
            "timestamp_iso": t_start_iso,
            "elapsed_s": elapsed_s,
            "V_set(V)": V_set,
            "I(A)": I_val,
            "period_s": period_s,
            "NPLC": nplc,
        }
        records.append(rec)

        w.writerow([
            rec["index"],
            rec["timestamp_iso"],
            f"{rec['elapsed_s']:.6f}",
            f"{rec['V_set(V)']:.6f}",
            f"{rec['I(A)']:.12e}",
            f"{rec['period_s']:.6f}",
            f"{rec['NPLC']:.3g}",
        ])
        f_csv.flush()

        k += 1
        if elapsed_s >= total_seconds:
            break

# ==============================
# Ramp down and turn off
# ==============================
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")
inst.close()
rm.close()

# ==============================
# Save and plot
# ==============================
elapsed_arr = np.array([r["elapsed_s"] for r in records])
curr_arr    = np.array([r["I(A)"] for r in records])

df = pd.DataFrame({
    "index": [r["index"] for r in records],
    "time_s": elapsed_arr,
    "current_A": curr_arr,
    "V_set_V": [V_set]*len(records),
    "period_s": [period_s]*len(records),
    "NPLC": [nplc]*len(records),
    "timestamp_iso":[t_start_iso]*len(records),
})
df.to_excel(xlsx_path, index=False, engine="openpyxl")
print(f"Saved CSV:  {csv_path}")
print(f"Saved XLSX: {xlsx_path}")

plt.figure()
plt.plot(elapsed_arr, curr_arr, 'o-')
plt.xlabel("Time (s)")
plt.ylabel("Current (A)")
plt.title(f"Keithley 6430 hold {V_set} V | {len(records)} pts | {period_s:.3f}s | fixed {curr_range} A | NPLC={nplc}")
plt.grid(True)
plt.tight_layout()
plt.show()