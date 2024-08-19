#!/usr/bin/env python

import os, io, re, mmap

OK_ICON = "[ OK ] "
FAIL_ICON = "[FAIL] "
INFO_ICON = "[INFO] "
SKIP_ICON = "[SKIP] "

IRQBALANCE_PATH="/usr/sbin/irqbalance"
IRQBALANCE_SERVICE_PATH="/usr/lib/systemd/system/irqbalance.service"

# a set of strings we assume (perhaps too boldly) should always appear
# in a properly built irqbalance executable
#
MARKERS=[ "libcap-ng.so.0", "libnuma.so.1", "/sys/devices/system/cpu",
    "%s/topology/core_siblings", "/proc/interrupts", "/proc/irq/%i/node",
    "g_main_loop_run", "g_list_append",
    "irqbalance" ]

# --- subroutines ---

# Reads a single line from the file at the given path,
# strips spaces and returns the result.
# Returns None if an error occurred (does not throw).
#
def read_one_line(path):
    line = ''
    try:
        with io.open(path, "r") as f:
            line = f.readline().strip()
        return line
    except e:
        return None

# Finds a running process, if present, and returns its PID.
# Returns None if the process is not found.
#
def find_running_process_id(name):
    for pid in os.listdir("/proc/"):
        if re.match("^[0-9]+$", pid):
            cmdline = read_one_line("/proc/" + pid + "/cmdline")
            if cmdline.find(name) != -1:
                return int(pid)
    return None

# Collects statistics of IRQs by parsing /proc/interrupts.
# The result is a dictionary of arrays; the key is the name of the IRQ
# (either a stringified IRQ number, or a three-letter abbreviation),
# the value is an array of numbers with length equal to the number of CPUs,
# each number is the number of times the given IRQ was handled by that CPU.
#
def get_irq_statistics():
    result = {}
    f = io.open("/proc/interrupts", "r", encoding="utf-8")
    with f:

        # first line is the list of CPUs (header of the table)
        #
        l = f.readline()
        cpu_list = l.split()
        cpu_count = len(cpu_list)

        # following lines represent various IRQs, first is the IRQ name,
        # then the number of IRQs processed by each of the CPUs,
        # and finally some descriptive words (those are not used here)
        #
        while f:
            columns = f.readline().split()
            if len(columns) <= 1:
                break
            irq_name = columns[0].strip(':')

            # ERR and MIS are special because they are not handled by any CPU
            # and therefore have no per-CPU statistics; skip these
            #
            if irq_name == 'ERR' or irq_name == 'MIS':
                continue

            # collect per-CPU statistics
            #
            irqs_per_cpu = [ int(x) for x in columns[1:cpu_count] ]
            result[irq_name] = irqs_per_cpu
    return result

# Counts nonzero values in the given vector.
#
def count_nonzero_values(vec):
    count = 0
    for x in vec:
        if x != 0:
            count = count + 1
    return count

def get_nonzero_index(vec):
    index = 0
    for x in vec:
        if x != 0:
            return index
        index = index + 1

# --- main ---

cpu_count = os.cpu_count()
print(INFO_ICON + "processor count: %d" % cpu_count)

if os.access(IRQBALANCE_PATH, os.X_OK):
    print(OK_ICON + IRQBALANCE_PATH + " exists and is executable")
else:
    print(FAIL_ICON + IRQBALANCE_PATH + " does not exist, or is not accessible")
    #exit(1)

try:
    fd = os.popen(IRQBALANCE_PATH + " --version")
except:
    print(FAIL_ICON + IRQBALANCE_PATH + " --version did not execute correctly")
    exit(1)

with fd:
    line = fd.readline().strip()
    exitcode = fd.close()
    if exitcode == None:
        print(OK_ICON + IRQBALANCE_PATH + " --version returns '" + line + "'")
    else:
        print(FAIL_ICON + IRQBALANCE_PATH + " --version failed with exit code %d" %
            os.waitstatus_to_exitcode(exitcode))

if os.access(IRQBALANCE_SERVICE_PATH, os.R_OK):
    print(OK_ICON + IRQBALANCE_SERVICE_PATH + " exists and is readable")
else:
    print(FAIL_ICON + IRQBALANCE_SERVICE_PATH + " does not exist or is not readable")

try:
    fd = os.open(IRQBALANCE_PATH, os.O_RDONLY)
except:
    print(FAIL_ICON + IRQBALANCE_PATH + ": could not open for reading")
    fd = None

if fd:
    mem = mmap.mmap(fd, 0, mmap.MAP_SHARED, mmap.PROT_READ)
    with mem:
        for marker in MARKERS:
            if mem.find(bytes(marker, "utf-8")) == -1:
                print(FAIL_ICON + "marker '%s' not found in the irqbalance executable" %
                    marker)
            else:
                print(OK_ICON + "marker '%s' found in the irqbalance executable" % marker)
    os.close(fd)
else:
    print(SKIP_ICON + "no irqbalance executable, cannot test markers")

pid = find_running_process_id("irqbalance")
if not pid:
    print(INFO_ICON + "irqbalance seems not to be running")
else:
    print(OK_ICON + "irqbalance currently running (PID %d)" % pid)

irqs = get_irq_statistics()
irqs_per_cpu = [ 0 ] * cpu_count
for irq in irqs:
    if count_nonzero_values(irqs[irq]) == 1:
        cpu_index = get_nonzero_index(irqs[irq])
        irqs_per_cpu[cpu_index] += irqs[irq][cpu_index]
#for cpu_index in range(0, cpu_count-1):
#    print(INFO_ICON + "IRQs handled by CPU #%d: %d" % (cpu_index, irqs_per_cpu[cpu_index]))
