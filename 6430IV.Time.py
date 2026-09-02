# takes a set voltage and measures current every x ms
# @plc=1,   periodmax =250ms 257 pts
# @plc=.1,  periodmax =50ms  1469 pts
# @plc=.01, periodmax =24ms  2647 pts

import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time, math, csv, os
from datetime import datetime
import pandas as pd
import re

# ==============================
# Helper: make a Windows-safe filename chunk
# ==============================
def sanitize_for_filename(s: str, max_len: int = 60) -> str:
    s = s.strip()
    if not s:
        return "untitled"
    # Replace illegal filename chars with underscore
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    # Collapse whitespace
    s = re.sub(r"\s+", "_", s)
    # Keep it reasonably short
    s = s[:max_len].strip("_")
    return s if s else "untitled"

# ==============================
# User inputs
# ==============================
Title         = str(input("Enter title (sample name, date, etc): ")).strip()
V_set         = float(input("Voltage to apply (V): "))
total_seconds = float(input("Total time (seconds): "))
period_ms     = float(input("Reading period (ms), e.g. 25 for 25 ms: "))
comp_limit    = float(input("Current compliance (A), e.g. 1e-7: "))
curr_range_in = input("Current range (A), fixed only (e.g. 1e-12): ").strip().lower()
nplc          = float(input("Integration time in PLC (e.g. .01): "))

if total_seconds <= 0:
    raise ValueError("Total time must be > 0 seconds")
if period_ms <= 0:
    raise ValueError("Reading period must be > 0 ms")

period_s     = period_ms / 1000.0
n_points_est = int(math.floor(total_seconds / period_s)) + 1
if n_points_est < 1:
    n_points_est = 1

# ==============================
# Output directory
# ==============================
save_dir = r"D:\school\Lab work\iv figures\excel_march_26"
fig_dir  = r"D:\school\Lab work\iv figures\IV_figs_march_26"
os.makedirs(save_dir, exist_ok=True)
os.makedirs(fig_dir,  exist_ok=True)

run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

# ==============================
# File name
# ==============================
V_tag = f"{V_set:.3f}".replace(".", "p")
T_tag = f"{int(total_seconds)}s"
P_tag = f"{int(period_ms)}ms"
Title_tag = sanitize_for_filename(Title)

# File names already include the title
base_name = f"{Title_tag}_hold_stream_{V_tag}_{T_tag}_{P_tag}_{n_points_est}pts_{run_tag}"

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

# ==============================
# Configure source and measurement
# ==============================
inst.write(":SOUR:FUNC VOLT")
inst.write(f":SOUR:VOLT {V_set}")

inst.write(":SENS:FUNC 'CURR:DC'")
inst.write(f":SENS:CURR:PROT {comp_limit}")
inst.write(f":SENS:CURR:NPLC {nplc}")

try:
    curr_range = float(curr_range_in)
except ValueError:
    raise ValueError("Enter numeric range (A).")

inst.write(":SENS:CURR:RANGE:AUTO OFF")
inst.write(f":SENS:CURR:RANGE {curr_range}")

inst.write(":FORM:ELEM CURR")

inst.write(":OUTP ON")
time.sleep(0.25)

# ==============================
# Acquisition loop (host-timed)
# ==============================
records = []

t0 = time.monotonic()
t_start_iso = datetime.now().isoformat(timespec="seconds")

with open(csv_path, "w", newline="") as f_csv:
    w = csv.writer(f_csv)

    # CSV header row includes Title
    w.writerow([
        "Title",
        "index",
        "timestamp_iso",
        "elapsed_s",
        "V_set(V)",
        "I(A)",
        "period_s",
        "NPLC",
        "fixed_range_A"
    ])

    k = 0
    while True:
        target = t0 + k * period_s
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)

        reading_str = inst.query(":READ?")
        I_val = float(reading_str.strip())

        elapsed_s = time.monotonic() - t0

        rec = {
            "Title": Title,
            "index": k + 1,
            "timestamp_iso": t_start_iso,
            "elapsed_s": elapsed_s,
            "V_set(V)": V_set,
            "I(A)": I_val,
            "period_s": period_s,
            "NPLC": nplc,
            "fixed_range_A": curr_range,
        }
        records.append(rec)

        w.writerow([
            rec["Title"],
            rec["index"],
            rec["timestamp_iso"],
            f"{rec['elapsed_s']:.6f}",
            f"{rec['V_set(V)']:.6f}",
            f"{rec['I(A)']:.12e}",
            f"{rec['period_s']:.6f}",
            f"{rec['NPLC']:.3g}",
            f"{rec['fixed_range_A']:.3e}",
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
# Pack data
# ==============================
elapsed_arr = np.array([r["elapsed_s"] for r in records], dtype=float)
curr_arr    = np.array([r["I(A)"]      for r in records], dtype=float)

df = pd.DataFrame({
    "Title":         [Title] * len(records),
    "index":         [r["index"] for r in records],
    "time_s":        elapsed_arr,
    "current_A":     curr_arr,
    "V_set_V":       [V_set] * len(records),
    "total_s":       [total_seconds] * len(records),
    "period_s":      [period_s] * len(records),
    "NPLC":          [nplc] * len(records),
    "fixed_range_A": [curr_range] * len(records),
    "timestamp_iso": [t_start_iso] * len(records),
})

# ==============================
# Write Excel
# Row 1 will feature the title string
# ==============================
with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    # Row 1: title only
    title_df = pd.DataFrame([[Title]])
    title_df.to_excel(writer, index=False, header=False, sheet_name="data", startrow=0)

    # Metadata starts below title
    meta = pd.DataFrame({
        "field": [
            "Title",
            "V_set_V",
            "total_s",
            "period_s",
            "NPLC",
            "fixed_range_A",
            "timestamp_iso",
            "points_captured"
        ],
        "value": [
            Title,
            V_set,
            total_seconds,
            period_s,
            nplc,
            curr_range,
            t_start_iso,
            len(records)
        ],
    })
    meta.to_excel(writer, index=False, sheet_name="data", startrow=2)

    # Data table below metadata
    df.to_excel(writer, index=False, sheet_name="data", startrow=12)

print(f"Saved CSV:  {csv_path}")
print(f"Saved XLSX: {xlsx_path}")
print(f"Points captured: {len(records)}")

# ==============================
# Plot + AUTO SAVE FIGURE
# Figure title includes Title
# ==============================
plt.figure()
plt.plot(elapsed_arr, curr_arr, 'o-')
plt.xlabel("Time (s)")
plt.ylabel("Current (A)")
plt.title(
    f"{Title}\n"
    f"6430 hold {V_set} V | {len(records)} pts | total={int(total_seconds)} s | "
    f"period={period_s:.3f}s | fixed {curr_range:.3e} A | NPLC={nplc}"
)
plt.grid(True)
plt.tight_layout()

fig_name = f"{base_name}.png"
fig_path = os.path.join(fig_dir, fig_name)
plt.savefig(fig_path, dpi=300, bbox_inches='tight')
print(f"Saved FIG:  {fig_path}")

plt.show()