#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

script = Path(__file__).with_suffix(".ps1")
cmd = [r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-NoProfile", "-File", str(script), *sys.argv[1:]]
raise SystemExit(subprocess.run(cmd).returncode)
