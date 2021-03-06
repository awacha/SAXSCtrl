#!/usb/bin/env python

from setuptools import setup, find_packages
from setuptools.extension import Extension
from Cython.Build import cythonize
from distutils.sysconfig import get_python_lib, get_python_inc
import os

# Cython autobuilding needs the numpy headers. On Windows hosts, this trick is
# needed. On Linux, the headers are already in standard places.
incdirs = list(set([get_python_lib(0, 0), get_python_lib(0, 1), get_python_lib(1, 0),
                  get_python_lib(1, 1), get_python_inc(0), get_python_inc(1)]))
npy_incdirs = [os.path.join(x, 'numpy/core/include') for x in incdirs]
incdirs.extend(npy_incdirs)

# Extension modules written in Cython

pyxfiles = []
for dir_, subdirs, files in os.walk('saxsctrl'):
    pyxfiles.extend([os.path.join(dir_, f) for f in files if f.endswith('.pyx')])

ext_modules = [Extension(p.replace('/', '.')[:-4], [p], include_dirs=incdirs) for p in pyxfiles]

with open('.version_last','rt') as f:
    version_last=int(f.read())

setup(name='saxsctrl', version='0.0.%d'%version_last, author='Andras Wacha',
      author_email='awacha@gmail.com', url='http://github.com/awacha/SAXSCtrl',
      description='SAXS instrument control',
      packages=find_packages(),
      # cmdclass = {'build_ext': build_ext},
      ext_modules=cythonize(ext_modules),
      install_requires=['numpy>=1.0.0', 'scipy>=0.7.0', 'matplotlib'],
      setup_requires=['Cython>=0.15'],
      entry_points={'gui_scripts':['SAXSCtrl = saxsctrl:start_saxsctrl'],
                    },
      keywords="saxs sans sas small-angle scattering x-ray instrument control",
      license="",
      package_data={'saxsctrl': ['resource/*/*']},
      include_package_data=True,
      zip_safe=False,
)
