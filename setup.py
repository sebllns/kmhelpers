"""Setup script for kmhelpers package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="kmhelpers",
    version="0.4.0",
    author="Sébastien BELLENOUS",  
    author_email="sebastien.bellenous@inria.fr",  
    description="A Python toolkit for managing, compressing, and querying indexes with kmindex",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.inria.fr/omicfinder/kmhelpers", 
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "psutil>=5.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=3.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.950",
        ],
    },
    entry_points={
        "console_scripts": [
            "kmhelpers-query=kmhelpers.cli.query_index:main",
            "kmhelpers-compress=kmhelpers.cli.compress_index:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
