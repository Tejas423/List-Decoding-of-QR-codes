"""
Build the wu_core C++ extension module.

Usage:
    pip install .                          # install into site-packages
    python setup.py build_ext --inplace    # build .pyd next to wu_qr.py
"""

from setuptools import setup, Extension
import pybind11

ext = Extension(
    "wu_core",
    sources=["wu_core.cpp"],
    include_dirs=[pybind11.get_include()],
    language="c++",
    extra_compile_args=["/std:c++17", "/O2", "/EHsc"],   # MSVC flags
)

setup(
    name="wu_core",
    version="1.0",
    description="C++ backend for GF(2^8) Wu list decoder",
    ext_modules=[ext],
)
