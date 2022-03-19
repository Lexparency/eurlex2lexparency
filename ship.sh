#!/usr/bin/env bash
set -e

. ./venv/Scripts/activate

export PYTHONPATH=$(pwd)

echo "Running unittest."
python -m unittest discover eurlex2lexparency/ -p  'test_*.py'

echo "Building the package."
python setup.py sdist
python setup.py bdist_wheel

rm -rf eurlex2lexparency.egg-info/
rm -rf build

echo -e "\nDone"
echo -e "You can now upload to PyPI via\n > python -m twine upload dist/*"
