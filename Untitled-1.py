import pyvisa
import matplotlib.pyplot as plt

# --- Before running: ensure you have pyvisa installed and NI‑VISA or equivalent backend ---
# pip install pyvisa

# --- 1) Open GPIB connection ---
rm = pyvisa.ResourceManager()  
# Replace 'GPIB0::24::INSTR' with your actual board number and instrument address
inst = rm.open_resource('GPIB0::24::INSTR')
inst.timeout = 10000  # in milliseconds
inst.write_termination = '\n'
inst.read_termination = '\n'

# --- 2) Configure the Keithley 2400 for a 0–10 V I–V sweep ---
inst.write('*RST')                       # Reset to defaults
inst.write(':SENS:FUNC:CONC OFF')        # Single‑function measure
inst.write(':SOUR:FUNC VOLT')            # Source = voltage
inst.write(':SENS:FUNC "CURR:DC"')       # Measure = DC current
inst.write(':SENS:CURR:PROT 0.1')        # Compliance = 0.1 A
inst.write(':FORM:ELEM CURR')            # Return only current

# Define sweep: 0 → 10 V in 1 V steps
inst.write(':SOUR:VOLT:START 0')
inst.write(':SOUR:VOLT:STOP 10')
inst.write(':SOUR:VOLT:STEP 1')
inst.write(':SOUR:VOLT:MODE SWE')        # Linear sweep mode
inst.write(':SOUR:SWE:RANG AUTO')        # Auto‑range source
inst.write(':SOUR:SWE:SPAC LIN')         # Linear spacing
inst.write(':TRIG:COUN 11')              # 11 points (0,1,…,10)
inst.write(':SOUR:DEL 0.1')              # 100 ms delay per step

# --- 3) Execute sweep and read back current data ---
inst.write(':OUTP ON')                   # Enable output
data_str = inst.query(':READ?')          # Run sweep and get CSV currents
inst.write(':OUTP OFF')                  # Disable output for safety

# --- 4) Parse the data, filter out any empty entries, and plot ---
parts    = [s for s in data_str.strip().split(',') if s.strip() != '']
currents = [float(val) for val in parts]
voltages = list(range(0, 11))            # 0 through 10 V

plt.figure()
plt.plot(voltages, currents, marker='o')
plt.xlabel('Voltage (V)')
plt.ylabel('Current (A)')
plt.title('Keithley 2400 I–V Sweep via GPIB')
plt.grid(True)
plt.show()

# --- 5) Clean up ---
inst.close()
rm.close()
