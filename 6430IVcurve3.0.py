# measures current over a set voltage range, with capabilities to take finer measurements around 0 V.
import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time, math
from datetime import datetime
import pandas as pd
import os
import re

# ==============================
# Same folders as your other programs
# ==============================
SAVE_DIR = r"D:\school\Lab work\iv figures\excel_march_26"
FIG_DIR  = r"D:\school\Lab work\iv figures\IV_figs_march_26"
# ==============================
# Helper: Windows-safe filename chunk
# ==============================
def sanitize_for_filename(s: str, max_len: int = 60) -> str:
    s = s.strip()
    if not s:
        return "untitled"
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)  # illegal filename chars -> _
    s = re.sub(r"\s+", "_", s)            # whitespace -> _
    s = s[:max_len].strip("_")            # keep it short
    return s if s else "untitled"

# ==============================
# 0) Inputs
# ==============================
Title        = str(input("Enter title (sample name, date, etc): ")).strip()

start_v      = float(input("Enter start voltage (V): "))
stop_v       = float(input("Enter stop voltage (V): "))
coarse_step  = float(input("Enter COARSE step size (V, +): "))
n_samples    = int(input("Enter readings per step: "))
n_discard_start = int(input("Discard at START of each step: "))
n_discard_end   = int(input("Discard at END of each step: "))

if n_discard_start + n_discard_end >= n_samples:
    raise ValueError("Total discarded must be less than total samples.")
if coarse_step <= 0:
    raise ValueError("Coarse step must be positive.")

# --- Fine window settings around 0 V ---
use_fine = input("Use finer step around 0V? (y/n): ").strip().lower() == 'y'
if use_fine:
    fine_lo   = float(input("Fine window LOWER bound (e.g., -2): "))
    fine_hi   = float(input("Fine window UPPER bound (e.g.,  2): "))
    fine_step = float(input("Fine step size inside window (V, +): "))
    if fine_step <= 0:
        raise ValueError("Fine step must be positive.")
    if fine_lo > fine_hi:
        fine_lo, fine_hi = fine_hi, fine_lo

comp_limit = float(input("Enter current compliance (A), e.g. 1e-7: "))
curr_range_input = input("Enter current measurement range (A) or 'auto': ").strip().lower()
if curr_range_input in ("auto", "0"):
    use_auto_range = True
else:
    curr_range = float(curr_range_input)
    use_auto_range = False

# ==============================
# Build voltage list with fine window
# ==============================
def arange_inclusive(v0, v1, step_pos):
    """Inclusive arange that respects direction and hits v1."""
    sgn = 1.0 if v1 >= v0 else -1.0
    step = sgn * step_pos
    n = max(1, int(math.floor((v1 - v0)/step)) + 1)
    arr = v0 + np.arange(n) * step
    # ensure last exactly equals v1
    if (sgn > 0 and arr[-1] < v1 - 1e-12) or (sgn < 0 and arr[-1] > v1 + 1e-12):
        arr = np.append(arr, v1)
    else:
        arr[-1] = v1
    return arr

def build_voltages(start_v, stop_v, coarse_step, use_fine, fine_lo=None, fine_hi=None, fine_step=None):
    if not use_fine:
        return arange_inclusive(start_v, stop_v, coarse_step)

    lo = min(start_v, stop_v); hi = max(start_v, stop_v)
    if hi < fine_lo or lo > fine_hi:
        return arange_inclusive(start_v, stop_v, coarse_step)

    win_lo = max(min(start_v, stop_v), fine_lo)
    win_hi = min(max(start_v, stop_v), fine_hi)

    v1 = arange_inclusive(start_v, win_lo, coarse_step)[:-1]
    v2 = arange_inclusive(win_lo, win_hi, fine_step)
    v3 = arange_inclusive(win_hi, stop_v, coarse_step)[1:]

    return np.concatenate([v1, v2, v3])

voltages = build_voltages(
    start_v, stop_v, coarse_step, use_fine,
    fine_lo if use_fine else None,
    fine_hi if use_fine else None,
    fine_step if use_fine else None
)

# ==============================
# Filename improvements (Title + key settings baked in)
# ==============================
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(FIG_DIR,  exist_ok=True)

run_tag   = datetime.now().strftime("%Y%m%d_%H%M%S")
Title_tag = sanitize_for_filename(Title)

Vspan_tag = f"{start_v:.3f}to{stop_v:.3f}".replace(".", "p").replace("-", "m")
Cstep_tag = f"c{coarse_step:.4f}".replace(".", "p").replace("-", "m")
Ns_tag    = f"samp{n_samples}"
Trim_tag  = f"trim{n_discard_start}_{n_discard_end}"
Fine_tag  = "fineOFF"
if use_fine:
    Fine_tag = (
        f"fine{fine_lo:.3f}to{fine_hi:.3f}_step{fine_step:.4f}"
        .replace(".", "p").replace("-", "m")
    )

Range_tag = "AUTO" if use_auto_range else f"R{curr_range:.3e}".replace("+", "")
NPLC_tag  = "NPLC_na"  # this script does not set NPLC; keeping tag explicit

base_name = f"{Title_tag}_iv_sweep_{Vspan_tag}_{Cstep_tag}_{Fine_tag}_{Ns_tag}_{Trim_tag}_{Range_tag}_{run_tag}"

xlsx_path = os.path.join(SAVE_DIR, base_name + ".xlsx")
fig_iv_path = os.path.join(FIG_DIR,  base_name + "_IV.png")
fig_rv_path = os.path.join(FIG_DIR,  base_name + "_RV.png")

# ==============================
# 1) Open GPIB
# ==============================
rm   = pyvisa.ResourceManager()
inst = rm.open_resource('GPIB0::24::INSTR')  # adjust as needed
inst.timeout           = 10000
inst.write_termination = '\n'
inst.read_termination  = '\n'

# ==============================
# 2) Configure 6430
# ==============================
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

# ==============================
# 3) Sweep and averaging
# ==============================
avg_currents = []
t_start_iso = datetime.now().isoformat(timespec="seconds")

for v in voltages:
    inst.write(f":SOUR:VOLT {v}")
    time.sleep(0.2)  # settle
    readings = []
    for _ in range(n_samples):
        time.sleep(0.1)
        readings.append(float(inst.query(":MEAS:CURR:DC?")))
    trimmed = readings[n_discard_start : n_samples - n_discard_end] \
              if (n_discard_start + n_discard_end) < n_samples else readings
    avg_currents.append(np.mean(trimmed))

# Return to 0V and turn off
inst.write(":SOUR:VOLT 0")
time.sleep(0.1)
inst.write(":OUTP OFF")

# ==============================
# 4) Compute R–V
# ==============================
avg_currents = np.array(avg_currents)
mask = (voltages != 0) & (avg_currents != 0)
resistances = np.full_like(voltages, np.nan, dtype=float)
resistances[mask] = voltages[mask] / avg_currents[mask]

# ==============================
# 5) Plot I–V (AUTO-SAVE)
# ==============================
plt.figure()
plt.plot(voltages, avg_currents, 'o-')
plt.xlabel('Voltage (V)')
plt.ylabel('Average Current (A)')
plt.title(
    f"{Title}\n"
    f"I–V | {start_v}→{stop_v} V | coarse={coarse_step} V | "
    f"{'fine ON' if use_fine else 'fine OFF'} | samples/step={n_samples} | "
    f"discard={n_discard_start}+{n_discard_end} | range={'AUTO' if use_auto_range else curr_range} | "
    f"comp={comp_limit}"
)
plt.grid(True)
plt.tight_layout()
plt.savefig(fig_iv_path, dpi=300, bbox_inches="tight")

# ==============================
# 6) Plot R–V (AUTO-SAVE)
# ==============================
plt.figure()
plt.plot(voltages[mask], resistances[mask], 'o-')
plt.xlabel('Voltage (V)')
plt.ylabel('Resistance (Ω)')
plt.title(
    f"{Title}\n"
    f"R–V | computed as V/I (nonzero only) | points={int(np.sum(mask))}"
)
plt.grid(True)
plt.tight_layout()
plt.savefig(fig_rv_path, dpi=300, bbox_inches="tight")

# show both figures at the end (keeps behavior familiar)
plt.show()

# ==============================
# 7) Export to Excel (same path as other programs) + metadata header
# ==============================
df = pd.DataFrame({
    "Voltage (V)": voltages,
    "Avg Current (A)": avg_currents,
    "Resistance (Ω)": resistances
})

meta = pd.DataFrame({
    "field": [
        "Title", "timestamp_iso",
        "start_v", "stop_v",
        "coarse_step", "use_fine", "fine_lo", "fine_hi", "fine_step",
        "n_samples", "discard_start", "discard_end",
        "comp_limit", "use_auto_range", "curr_range_if_fixed"
    ],
    "value": [
        Title, t_start_iso,
        start_v, stop_v,
        coarse_step, use_fine,
        (fine_lo if use_fine else np.nan),
        (fine_hi if use_fine else np.nan),
        (fine_step if use_fine else np.nan),
        n_samples, n_discard_start, n_discard_end,
        comp_limit, use_auto_range,
        (np.nan if use_auto_range else curr_range)
    ]
})

with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
    meta.to_excel(writer, index=False, sheet_name="data", startrow=0)
    df.to_excel(writer, index=False, sheet_name="data", startrow=3)

print(f"Saved IV FIG: {fig_iv_path}")
print(f"Saved RV FIG: {fig_rv_path}")
print(f"Exported Excel file: {xlsx_path}")

# ==============================
# 8) Clean up
# ==============================
inst.close()
rm.close()