import os
import tools
import datetime
import subprocess
from decimal import *

from tools.cmgr import *

XILINX_INSTALL_PATH = '/opt/Xilinx'  # Path to the Xilinx installation
XILINX_VERSION      = None           # Use a specific version
                                     # (If unavailable tool will autodetect and
                                     #  use latest installed version)
XILINX_TOOLS_TYPE   = 32             # Use 32-bit or 64-bit version of tools

def _format_constraint(c):
	if isinstance(c, Pins):
		return "LOC=" + c.identifiers[0]
	elif isinstance(c, IOStandard):
		return "IOSTANDARD=" + c.name
	elif isinstance(c, Drive):
		return "DRIVE=" + str(c.strength)
	elif isinstance(c, Misc):
		return c.misc

def _format_ucf(signame, pin, others, resname):
	fmt_c = [_format_constraint(c) for c in ([Pins(pin)] + others)]
	fmt_r = resname[0] + ":" + str(resname[1])
	if resname[2] is not None:
		fmt_r += "." + resname[2]
	return "NET \"" + signame + "\" " + " | ".join(fmt_c) + "; # " + fmt_r + "\n"

def _build_ucf(ns, sig_constraints, platform_commands):
	r = ""
	
	for sig, pins, others, resname in sig_constraints:
		if len(pins) > 1:
			for i, p in enumerate(pins):
				r += _format_ucf(ns.get_name(sig) + "(" + str(i) + ")", p, others, resname)
		else:
			r += _format_ucf(ns.get_name(sig), pins[0], others, resname)
	
	for template, args in platform_commands:
		name_dict = dict((k, ns.get_name(sig)) for k, sig in args.items())
		r += template.format(**name_dict)
	
	return r

#-----------------------------------------------------------------------------#
# Build the project in the current working directory                          #
#                                                                             #
# Parameters:                                                                 #
#   sources: A list of HDL source files. Each element of the list is a        #
#            dictionary with the following keys:                              #
#            'type': 'verliog' or 'vhdl'                                      #
#            'path': relative path to the file (from current directory)       # 
#   build_name: A string to be used as a prefix for all generated files       #   
#   top: Top level HDL component (assumes same as build_name if not specified)#
#-----------------------------------------------------------------------------#
def build(device, sources, namespace, sig_constraints, platform_commands, build_name):
	# Generate UCF
	tools.write_to_file(build_name + ".ucf", _build_ucf(namespace, sig_constraints, platform_commands))

	# Generate project file
	prj_contents = ""
	for s in sources:
		prj_contents += s["type"] + " work " + s["path"] + "\n"
	tools.write_to_file(build_name + ".prj", prj_contents)

	# Generate XST script
	xst_contents = """run
-ifn %s.prj
-top top
-ifmt MIXED
-opt_mode SPEED
-reduce_control_sets auto
-ofn %s.ngc
-p %s""" % (build_name, build_name, device)
	tools.write_to_file(build_name + ".xst", xst_contents)

	# Determine Xilinx tool paths
	def isValidVersion(v):
		try: 
			Decimal(v)
			return os.path.isdir(os.path.join(XILINX_INSTALL_PATH, v))
		except:
			return False
	vers = [ver for ver in os.listdir(XILINX_INSTALL_PATH) if isValidVersion(ver)]
	tools_version = str(XILINX_VERSION) in vers and str(XILINX_VERSION) or max(vers)
	xilinx_settings_file = '%s/%s/ISE_DS/settings%d.sh' % (XILINX_INSTALL_PATH, tools_version, XILINX_TOOLS_TYPE) 

	# Generate Build script
	build_script_contents = """# Build Script for %s
# Autogenerated by rhino-tools at %s

set -e

source %s
# XST
xst -ifn %s.xst
# NGD
ngdbuild -uc %s.ucf %s.ngc
# Mapping
map -ol high -w %s.ngd
# Place and Route
par -ol high -w %s.ncd %s-routed.ncd
# Generate FPGA configuration
bitgen -g Binary:Yes -w %s-routed.ncd %s.bit
""" % (build_name, datetime.datetime.now(), xilinx_settings_file, build_name, build_name, build_name, build_name, build_name, build_name, build_name, build_name)
	build_script_file = "build_" + build_name + ".sh"
	tools.write_to_file(build_script_file, build_script_contents)

	r = subprocess.call(["bash", build_script_file])
	if r != 0:
		raise OSError("Subprocess failed")
