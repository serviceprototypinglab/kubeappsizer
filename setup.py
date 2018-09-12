# python3 setup.py sdist
# python3 setup.py bdist_wheel
# python3 setup.py bdist_egg
# twine upload dist/*.* [-r testpypi]
# -> automated in tools/make-dist.sh

from setuptools import setup

setup(
	name="descriptorrewriter",
	description="... (kubeappsizer)",
	long_description="...",
	version="0.0.1",
	url="https://github.com/serviceprototypinglab/kubeappsizer",
	author="Josef Spillner",
	author_email="josef.spillner@zhaw.ch",
	license="Apache 2.0",
	classifiers=[
		"Development Status :: 2 - Pre-Alpha",
		"Environment :: Console",
		"Environment :: No Input/Output (Daemon)",
		"Intended Audience :: Science/Research",
		"License :: OSI Approved :: Apache Software License",
		"Programming Language :: Python :: 3",
		"Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware"
	],
	keywords="kubernetes deployment",
	packages=["descriptorrewriter"],
	scripts=["kubeappsizer-rewrite-descriptors"]
)
