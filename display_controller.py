#!/usr/bin/env python3
"""
PCCooler GT360 - Image Display Controller (launcher script).

Delegates to the pccooler_gt360 package. From the project root, install in editable mode first:
  pip install -e .
Then run:  python display_controller.py --pattern blue
Or use the console script:  pccooler-gt360 --pattern blue
"""

if __name__ == "__main__":
    try:
        from pccooler_gt360.cli import main
    except ImportError:
        print("Run from project root after installing the package:  pip install -e .")
        raise
    main()
