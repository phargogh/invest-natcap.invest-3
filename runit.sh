#!/bin/bash
ENVDIR=invest_python_environment
deactivate
python bootstrap_invest_environment.py > setup_environment.py
python setup_environment.py --clear --system-site-packages $ENVDIR
source $ENVDIR/bin/activate
nosetests test/timber_core_test.py
nosetests test/invest_core_test.py
