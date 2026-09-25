"""Bench mode: plausible sensor readings for a node with no sensors wired.

Set BENCH_SIMULATE = True in config.py and every channel reports what the desktop
app's physics model predicts it would read at the current fan level, with a small
wobble. Telemetry, Wi-Fi, the display and commands all stay real, so the whole
pipeline can be exercised on the bench. Never leave this on in an installed box.

PROFILES is generated from tools/simulate_node.py (_PROFILES), which comes from
the app's SystemModel.PredictReading for Option A and Option C. Channels a
profile has no value for (Option C has no cyclone or bin) report as not found.
"""

import math

try:
    from time import ticks_ms
except ImportError:                                   # host tests
    import time as _t

    def ticks_ms(): return int(_t.monotonic() * 1000)

# profile -> fan level -> channel name -> Pa
PROFILES = {
    'A': {
        0: {'fan_in': 0, 'bin': 0, 'cyc_dp': 0, 'encl': 0, 'pitot': 0, 'run_in': 0},
        1: {'fan_in': 4.19, 'bin': 2.5, 'cyc_dp': 2.14, 'encl': 0.18, 'pitot': 0.44, 'run_in': 3.59},
        2: {'fan_in': 16.71, 'bin': 10.29, 'cyc_dp': 8.79, 'encl': 0.72, 'pitot': 1.81, 'run_in': 14.59},
        3: {'fan_in': 37.55, 'bin': 23.44, 'cyc_dp': 20.03, 'encl': 1.65, 'pitot': 4.12, 'run_in': 33.08},
        4: {'fan_in': 66.71, 'bin': 41.98, 'cyc_dp': 35.87, 'encl': 2.95, 'pitot': 7.38, 'run_in': 59.1},
        5: {'fan_in': 104.19, 'bin': 65.93, 'cyc_dp': 56.33, 'encl': 4.64, 'pitot': 11.59, 'run_in': 92.65},
        6: {'fan_in': 149.98, 'bin': 95.29, 'cyc_dp': 81.42, 'encl': 6.7, 'pitot': 16.75, 'run_in': 133.74},
        7: {'fan_in': 204.09, 'bin': 130.09, 'cyc_dp': 111.15, 'encl': 9.15, 'pitot': 22.87, 'run_in': 182.39},
        8: {'fan_in': 266.5, 'bin': 170.32, 'cyc_dp': 145.52, 'encl': 11.98, 'pitot': 29.94, 'run_in': 238.6},
        9: {'fan_in': 337.24, 'bin': 215.98, 'cyc_dp': 184.54, 'encl': 15.19, 'pitot': 37.97, 'run_in': 302.37},
        10: {'fan_in': 416.28, 'bin': 267.09, 'cyc_dp': 228.21, 'encl': 18.78, 'pitot': 46.96, 'run_in': 373.72},
    },
    'C': {
        0: {'fan_in': 0, 'encl': 0, 'pitot': 0, 'run_in': 0},
        1: {'fan_in': 3.81, 'encl': 0.34, 'pitot': 0.85, 'run_in': 2.74},
        2: {'fan_in': 15.14, 'encl': 1.42, 'pitot': 3.54, 'run_in': 11.25},
        3: {'fan_in': 33.96, 'encl': 3.26, 'pitot': 8.15, 'run_in': 25.62},
        4: {'fan_in': 60.24, 'encl': 5.87, 'pitot': 14.67, 'run_in': 45.88},
        5: {'fan_in': 93.99, 'encl': 9.25, 'pitot': 23.14, 'run_in': 72.06},
        6: {'fan_in': 135.19, 'encl': 13.41, 'pitot': 33.54, 'run_in': 104.16},
        7: {'fan_in': 183.86, 'encl': 18.35, 'pitot': 45.88, 'run_in': 142.21},
        8: {'fan_in': 239.88, 'encl': 24.06, 'pitot': 60.16, 'run_in': 186.13},
        9: {'fan_in': 303.31, 'encl': 30.55, 'pitot': 76.37, 'run_in': 235.96},
        10: {'fan_in': 374.16, 'encl': 37.81, 'pitot': 94.53, 'run_in': 291.72},
    },
}


class NoMux:
    """Stands in for the TCA9548A: every port selects."""

    def select(self, port):
        return True

    def invalidate(self):
        pass


class Driver:
    """Stands in for one pressure sensor; reads from the profile table."""

    def __init__(self, name, profile, level):
        self.name = name
        self.table = PROFILES.get(profile, PROFILES["A"])
        self.level = level                            # callable -> current fan level

    def start(self):
        return self.name in self.table[10]

    def read(self):
        lvl = max(0, min(10, int(self.level() or 0)))
        pa = self.table[lvl].get(self.name)
        if pa is None:
            raise OSError("no such channel in this profile")
        wobble = 1 + 0.012 * math.sin(ticks_ms() / 1500.0 + len(self.name))
        return pa * wobble, 24.0
