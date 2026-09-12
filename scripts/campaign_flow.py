#!/usr/bin/env python3
"""Compatibility CLI for campaign flow parsing and graph building."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from whshr.campaign import main

if __name__ == "__main__":
    sys.exit(main())
