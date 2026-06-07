#!/bin/bash
# Run all mediaman tests.
# Usage: ./run_tests.sh            (all tests)
#        ./run_tests.sh -v         (verbose)
#        ./run_tests.sh photoman   (specific module)

cd "$(dirname "$0")"
exec python3 -m unittest discover -s . -p '*_test.py' "$@"
