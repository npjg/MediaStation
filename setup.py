from setuptools import Extension, setup

setup(
    ext_modules = [
        Extension(name = 'MediaStationBitmapRle', sources = ['MediaStation/Assets/BitmapRle.c'])
    ]
)