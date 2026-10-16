"""Ponto de entrada do executável (PyInstaller)."""
import multiprocessing
import sys

from ddbot.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
