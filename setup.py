from setuptools import setup, find_packages

LONG_DESCRIPTION = """aws-prometheus-exporter

This library allows to export the result of AWS API calls to Prometheus.
API calls and how they translate to Prometheus metrics are encoded in YAML.
See https://github.com/movio/aws-prometheus-exporter for usage and instructions.
"""

setup(
    name="aws-prometheus-exporter",
    version="0.1.2",
    author="Movio Developers",
    author_email="nicolas@movio.co",
    description="AWS exporter for Prometheus",
    license="MIT",
    keywords="aws monitoring prometheus",
    url="https://github.com/movio/aws-prometheus-exporter",
    packages=find_packages(),
    long_description=LONG_DESCRIPTION,
    setup_requires=["pytest-runner"],
    tests_require=["pytest"],
    install_requires=[
        "boto3>=1.9",
        "pyyaml>=3.13",
        "prometheus_client>=0.4",
    ],
    python_requires='>=3.7',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: Apache Software License",
    ],
)
