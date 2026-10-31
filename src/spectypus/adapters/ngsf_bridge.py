"""Standalone launcher: preserve legacy NGSF np.math compatibility privately."""
import math
import os
import runpy
import sys

import numpy as np

np.math = math
target, parameters = sys.argv[1:3]
sys.path.insert(0, os.path.dirname(target))
sys.argv = [target, parameters]
runpy.run_path(target, run_name="__main__")
