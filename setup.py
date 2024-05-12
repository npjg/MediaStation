from setuptools import Extension, setup

import warnings

# TODO: Distribute prebuilt wheels for the C bitmap decompression accelerator extension.
#
# For development work, looks like you would use this to compile the 
# C-based image decompressor:
#  python3 setup.py build_ext --inplace
bitmap_decompression = Extension(name = 'MediaStationBitmapRle', sources = ['src/MediaStation/Assets/BitmapRle.c'])
try:
    # TRY TO COMPILE THE C-BASED IMAGE DECOMPRESSOR.
    setup(
        name = 'MediaStation',
        ext_modules = [bitmap_decompression])
except:
    # RELY ON THE PYTHON FALLBACK.
    warnings.warn('The C bitmap decompression binary is not available on this installation. Expect image decompression to be SLOW.')
    setup(name = 'MediaStation')
