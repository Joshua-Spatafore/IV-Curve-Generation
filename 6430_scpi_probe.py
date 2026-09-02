import pyvisa

rm = pyvisa.ResourceManager()
inst = rm.open_resource("GPIB0::24::INSTR")
inst.write_termination = "\n"
inst.read_termination  = "\n"
inst.timeout = 5000

def err():
    return inst.query(":SYST:ERR?").strip()

inst.write("*CLS")
print("Try set 3000:", end=" ")
inst.write(":TRAC:POIN 3000")
print("ERR:", err())

inst.write("*CLS")
print("Try set 5000:", end=" ")
inst.write(":TRAC:POIN 5000")
print("ERR:", err())

inst.close()
rm.close()
