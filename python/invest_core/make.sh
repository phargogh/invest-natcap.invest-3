#!/bin/bash
INCLUDE="-I." \
LDFLAGS="-L." \
    python ./setup.py build_ext --inplace
