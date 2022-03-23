from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in bmga/__init__.py
from bmga import __version__ as version

setup(
	name="bmga",
	version=version,
	description="Bmga app",
	author="Karthik Raman",
	author_email="karthikeyan@yuvabe.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
