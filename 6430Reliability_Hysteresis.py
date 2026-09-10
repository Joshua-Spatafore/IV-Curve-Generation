"""Continuous hysteresis sweeps for a Keithley 6430 reliability test.

The first sweep runs from the requested start voltage to the stop voltage.
Each requested repeat immediately reverses direction, retaining the endpoint
as the first point of the new leg.  All sweep legs are saved in one workbook.
"""

import math
import os
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyvisa


# ==============================
# User-adjustable constants
# ==============================

SAVE_DIR = r"D:\school\Lab work\iv figures\excel_september_26" #change based on PC being used
INSTRUMENT_RESOURCE = "GPIB0::24::INSTR"

SOURCE_SETTLE_SECONDS = 0.2
SAMPLE_DELAY_SECONDS = 0.1
ZERO_SETTLE_SECONDS = 0.1


# ==============================
# Helpers
# ==============================

def sanitize_for_filename(text: str, max_len: int = 60) -> str:
    """Return a short string that is safe to use in a Windows filename."""
    text = text.strip()
    if not text:
        return "untitled"

    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text[:max_len].strip("_")
    return text if text else "untitled"


def filename_number(value: float, digits: int = 3) -> str:
    """Format a number without characters that make filenames awkward."""
    return (
        f"{value:.{digits}f}"
        .replace("-", "m")
        .replace(".", "p")
    )


def arange_inclusive(v0: float, v1: float, step_size: float) -> np.ndarray:
    """Return values from v0 to v1, including v1, in either direction."""
    if step_size <= 0:
        raise ValueError("Step size must be positive.")

    if math.isclose(v0, v1, rel_tol=0.0, abs_tol=1e-12):
        return np.array([float(v1)])

    direction = 1.0 if v1 > v0 else -1.0
    distance = abs(v1 - v0)
    full_steps = int(math.floor(distance / step_size))

    values = v0 + direction * step_size * np.arange(full_steps + 1)

    if math.isclose(values[-1], v1, rel_tol=0.0, abs_tol=1e-12):
        values[-1] = v1
    else:
        values = np.append(values, v1)

    return values.astype(float)


def build_voltages(
    start_v: float,
    stop_v: float,
    coarse_step: float,
    use_fine: bool,
    fine_lo: float | None = None,
    fine_hi: float | None = None,
    fine_step: float | None = None,
) -> np.ndarray:
    """Build a coarse sweep with an optional fine-step window.

    The fine-window logic works for both increasing and decreasing sweeps.
    """
    if not use_fine:
        return arange_inclusive(start_v, stop_v, coarse_step)

    if fine_lo is None or fine_hi is None or fine_step is None:
        raise ValueError("Fine-window bounds and step are required.")

    sweep_lo = min(start_v, stop_v)
    sweep_hi = max(start_v, stop_v)
    overlap_lo = max(sweep_lo, fine_lo)
    overlap_hi = min(sweep_hi, fine_hi)

    # The sweep does not pass through the selected fine window.
    if overlap_lo > overlap_hi:
        return arange_inclusive(start_v, stop_v, coarse_step)

    if stop_v >= start_v:
        fine_entry = overlap_lo
        fine_exit = overlap_hi
    else:
        fine_entry = overlap_hi
        fine_exit = overlap_lo

    before = arange_inclusive(start_v, fine_entry, coarse_step)
    inside = arange_inclusive(fine_entry, fine_exit, fine_step)
    after = arange_inclusive(fine_exit, stop_v, coarse_step)

    # Drop the first point of later segments so the boundaries occur once.
    return np.concatenate([before, inside[1:], after[1:]])


def make_output_path(
    title: str,
    start_v: float,
    stop_v: float,
    coarse_step: float,
    use_fine: bool,
    fine_lo: float | None,
    fine_hi: float | None,
    fine_step: float | None,
    n_samples: int,
    n_discard_start: int,
    n_discard_end: int,
    use_auto_range: bool,
    curr_range: float | None,
    repeats: int,
) -> str:
    """Create a descriptive, timestamped Excel filename."""
    title_tag = sanitize_for_filename(title)
    span_tag = f"{filename_number(start_v)}to{filename_number(stop_v)}"
    coarse_tag = f"c{filename_number(coarse_step, 4)}"

    if use_fine:
        fine_tag = (
            f"fine{filename_number(fine_lo)}to{filename_number(fine_hi)}"
            f"_step{filename_number(fine_step, 4)}"
        )
    else:
        fine_tag = "fineOFF"

    range_tag = (
        "AUTO"
        if use_auto_range
        else f"R{curr_range:.3e}".replace("+", "")
    )
    trim_tag = f"trim{n_discard_start}_{n_discard_end}"
    repeat_tag = f"repeat{repeats}"
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_name = (
        f"{title_tag}_reliability_"
        f"{span_tag}_{coarse_tag}_{fine_tag}_"
        f"samp{n_samples}_{trim_tag}_{range_tag}_"
        f"{repeat_tag}_hysteresis_{run_tag}.xlsx"
    )
    return os.path.join(SAVE_DIR, base_name)


def export_excel(
    xlsx_path: str,
    measurement_rows: list[dict],
    metadata: dict,
) -> None:
    """Write measurement data and metadata to separate workbook sheets."""
    data_df = pd.DataFrame(measurement_rows)
    metadata_df = pd.DataFrame(
        {"Field": list(metadata.keys()), "Value": list(metadata.values())}
    )

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        data_df.to_excel(writer, index=False, sheet_name="Data")
        metadata_df.to_excel(writer, index=False, sheet_name="Metadata")


# ==============================
# Main program
# ==============================

def main() -> None:
    # ------------------------------
    # Inputs
    # ------------------------------
    title = input("Enter title (sample name, date, etc): ").strip()

    start_v = float(input("Enter start voltage (V): "))
    stop_v = float(input("Enter stop voltage (V): "))
    coarse_step = float(input("Enter COARSE step size (V, +): "))
    n_samples = int(input("Enter readings per step: "))
    n_discard_start = int(input("Discard at START of each step: "))
    n_discard_end = int(input("Discard at END of each step: "))

    repeats = int(
        input("Enter number of direction-reversing repeats after the first sweep: ")
    )

    if coarse_step <= 0:
        raise ValueError("Coarse step must be positive.")
    if n_samples <= 0:
        raise ValueError("Readings per step must be at least 1.")
    if n_discard_start < 0 or n_discard_end < 0:
        raise ValueError("Discard counts cannot be negative.")
    if n_discard_start + n_discard_end >= n_samples:
        raise ValueError("Total discarded must be less than total samples.")
    if repeats < 0:
        raise ValueError("Number of repeats cannot be negative.")

    # Fine window settings around 0 V.
    use_fine = (
        input("Use finer step around 0 V? (y/n): ").strip().lower() == "y"
    )
    fine_lo = None
    fine_hi = None
    fine_step = None

    if use_fine:
        fine_lo = float(input("Fine window LOWER bound (e.g., -2): "))
        fine_hi = float(input("Fine window UPPER bound (e.g., 2): "))
        fine_step = float(input("Fine step size inside window (V, +): "))

        if fine_step <= 0:
            raise ValueError("Fine step must be positive.")
        if fine_lo > fine_hi:
            fine_lo, fine_hi = fine_hi, fine_lo

    comp_limit = float(
        input("Enter current compliance (A), e.g. 1e-7: ")
    )
    if comp_limit <= 0:
        raise ValueError("Current compliance must be positive.")

    curr_range_input = input(
        "Enter current measurement range (A) or 'auto': "
    ).strip().lower()

    curr_range = None
    if curr_range_input in ("auto", "0"):
        use_auto_range = True
    else:
        curr_range = float(curr_range_input)
        if curr_range <= 0:
            raise ValueError("Fixed current range must be positive.")
        use_auto_range = False

    forward_voltages = build_voltages(
        start_v,
        stop_v,
        coarse_step,
        use_fine,
        fine_lo,
        fine_hi,
        fine_step,
    )

    os.makedirs(SAVE_DIR, exist_ok=True)
    xlsx_path = make_output_path(
        title,
        start_v,
        stop_v,
        coarse_step,
        use_fine,
        fine_lo,
        fine_hi,
        fine_step,
        n_samples,
        n_discard_start,
        n_discard_end,
        use_auto_range,
        curr_range,
        repeats,
    )

    # ------------------------------
    # Open and configure Keithley 6430
    # ------------------------------
    rm = None
    inst = None
    measurement_rows = []
    test_start_iso = datetime.now().isoformat(timespec="seconds")

    try:
        rm = pyvisa.ResourceManager()
        inst = rm.open_resource(INSTRUMENT_RESOURCE)
        inst.timeout = 10000
        inst.write_termination = "\n"
        inst.read_termination = "\n"

        inst.write("*RST")
        inst.write(":SOUR:FUNC VOLT")
        inst.write(":SOUR:VOLT 0")
        inst.write(":SENS:FUNC 'CURR:DC'")
        inst.write(f":SENS:CURR:PROT {comp_limit}")
        inst.write(":FORM:ELEM CURR")

        if use_auto_range:
            inst.write(":SENS:CURR:RANGE:AUTO ON")
        else:
            inst.write(":SENS:CURR:RANGE:AUTO OFF")
            inst.write(f":SENS:CURR:RANGE {curr_range}")

        inst.write(":OUTP ON")

        # ------------------------------
        # Continuous alternating sweep and averaging
        # ------------------------------
        total_legs = repeats + 1
        global_point_number = 0

        for leg_index in range(total_legs):
            leg_number = leg_index + 1
            is_forward = leg_index % 2 == 0
            direction = "Forward" if is_forward else "Reverse"
            leg_voltages = (
                forward_voltages
                if is_forward
                else forward_voltages[::-1]
            )

            print(
                f"Starting {direction.lower()} sweep leg "
                f"{leg_number} of {total_legs}..."
            )

            for point_in_leg, voltage in enumerate(leg_voltages, start=1):
                global_point_number += 1
                inst.write(f":SOUR:VOLT {voltage}")
                time.sleep(SOURCE_SETTLE_SECONDS)

                readings = []
                for _ in range(n_samples):
                    time.sleep(SAMPLE_DELAY_SECONDS)
                    readings.append(
                        float(inst.query(":MEAS:CURR:DC?"))
                    )

                trim_stop = n_samples - n_discard_end
                trimmed = readings[n_discard_start:trim_stop]
                avg_current = float(np.mean(trimmed))

                if voltage != 0 and avg_current != 0:
                    resistance = float(voltage / avg_current)
                else:
                    resistance = np.nan

                measurement_rows.append(
                    {
                        "Sweep Leg": leg_number,
                        "Direction": direction,
                        "Point in Leg": point_in_leg,
                        "Global Point": global_point_number,
                        "Timestamp ISO": datetime.now().isoformat(
                            timespec="seconds"
                        ),
                        "Voltage (V)": float(voltage),
                        "Avg Current (A)": avg_current,
                        "Resistance (ohm)": resistance,
                    }
                )

            print(f"Completed sweep leg {leg_number} of {total_legs}.")

    finally:
        # Make a best effort to leave the source in a safe state, including
        # when the program is interrupted or a measurement raises an error.
        if inst is not None:
            try:
                inst.write(":SOUR:VOLT 0")
                time.sleep(ZERO_SETTLE_SECONDS)
                inst.write(":OUTP OFF")
            except Exception:
                pass

            try:
                inst.close()
            except Exception:
                pass

        if rm is not None:
            try:
                rm.close()
            except Exception:
                pass

    test_end_iso = datetime.now().isoformat(timespec="seconds")

    # ------------------------------
    # Excel export
    # ------------------------------
    metadata = {
        "Title": title,
        "test_start_timestamp_iso": test_start_iso,
        "test_end_timestamp_iso": test_end_iso,
        "instrument_resource": INSTRUMENT_RESOURCE,
        "start_v": start_v,
        "stop_v": stop_v,
        "coarse_step": coarse_step,
        "use_fine": use_fine,
        "fine_lo": fine_lo if use_fine else np.nan,
        "fine_hi": fine_hi if use_fine else np.nan,
        "fine_step": fine_step if use_fine else np.nan,
        "points_per_sweep_leg": len(forward_voltages),
        "number_of_direction_reversing_repeats": repeats,
        "total_sweep_legs": repeats + 1,
        "total_measurement_points": len(forward_voltages) * (repeats + 1),
        "n_samples": n_samples,
        "discard_start": n_discard_start,
        "discard_end": n_discard_end,
        "comp_limit": comp_limit,
        "use_auto_range": use_auto_range,
        "curr_range_if_fixed": (
            np.nan if use_auto_range else curr_range
        ),
        "source_settle_seconds": SOURCE_SETTLE_SECONDS,
        "sample_delay_seconds": SAMPLE_DELAY_SECONDS,
    }

    export_excel(xlsx_path, measurement_rows, metadata)
    print(f"Exported Excel file: {xlsx_path}")


if __name__ == "__main__":
    main()
