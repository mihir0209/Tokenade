"""
Tokenade - Production-grade token shifting tool.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tokenade",
    version="2.0.0",
    author="Tokenade Team",
    description="Production-grade token shifting and session portability tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mihir0209/tokenade",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: Browsers",
        "Topic :: Security",
    ],
    python_requires=">=3.8",
    install_requires=[
        "playwright>=1.40.0",
        "requests>=2.28.0",
        "pycryptodome>=3.19.0",
        "keyring>=24.0.0",
    ],
    extras_require={
        "windows": ["pywin32>=306"],
        "linux": ["secretstorage>=3.3.3"],
        "runtime": ["curl-cffi>=0.6.0"],  # For JA3 fingerprint matching
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "tokenade=tokenade.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
