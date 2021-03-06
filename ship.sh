#!/usr/bin/env bash
set -e

. ./venv/Scripts/activate

export PYTHONPATH=$(pwd)

echo "Running unittest."
./venv/Scripts/python.exe -m unittest discover eurlex2lexparency/ -p  'test_*.py'

echo "Building the package."
./venv/Scripts/python.exe setup.py sdist
./venv/Scripts/python.exe setup.py bdist_wheel

rm -rf eurlex2lexparency.egg-info/
rm -rf build

echo -e "\nDone"
echo -e "You can now upload to PyPI via\n > ./venv/Scripts/python.exe -m twine upload dist/*"
