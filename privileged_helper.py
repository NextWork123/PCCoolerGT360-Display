#!/usr/bin/env python3
"""Privileged helper: run PCCooler GT360 USB operations as root. Invoked by the UI via sudo."""

import json
import sys

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    # Options from UI; stop_event is not passed (Stop is handled by terminating this process)
    kwargs = {k: v for k, v in data.items() if k != "stop_event"}
    try:
        from example import main as example_main
        example_main(**kwargs)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
