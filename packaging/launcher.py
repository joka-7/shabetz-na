"""Entry point frozen into the desktop executable."""

import multiprocessing
import sys

from shabetz.desktop import main

if __name__ == "__main__":
    # Required before anything else in a frozen Windows program that may spawn
    # processes; without it a child re-runs the whole app instead.
    multiprocessing.freeze_support()
    sys.exit(main())
