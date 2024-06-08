from setuptools import Extension, setup

import warnings

# BUILD THE BITMAP DECOMPRESSOR.
# For development work, looks like you would use this to compile the 
# C-based image decompressor:
#  python3 setup.py build_ext --inplace
bitmap_decompression = Extension(name = 'MediaStationBitmapRle', sources = ['src/MediaStation/Assets/BitmapRle.c'])
ima_adpcm_decompression = Extension(name = 'MediaStationImaAdpcm', sources = ['src/MediaStation/Assets/ImaAdpcm.c'])
try:
    # TRY TO COMPILE THE C-BASED IMAGE DECOMPRESSOR.
    setup(
        name = 'MediaStation',
        ext_modules = [bitmap_decompression, ima_adpcm_decompression])
except:
    # RELY ON THE PYTHON FALLBACK.
    warnings.warn('The C bitmap decompression binary is not available on this installation. Expect image decompression to be SLOW.')
    setup(name = 'MediaStation')

# BUILD THE IMA ADPCM DECOMPRESSOR.
# ima_adpcm_decompression = Extension()
# There is currently not a pure Python implementation, so there 
# is no try-catch block here. Maybe we can add a try-catch and 
# just say that ADPCM decompression is not available.