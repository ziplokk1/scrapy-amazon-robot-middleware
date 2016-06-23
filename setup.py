from setuptools import setup, find_packages

version = '0.1.0'

REQUIREMENTS = [
    'beautifulsoup',
    'scrapy',
    'pillow',
    'requests'
]

setup(
    name='scrapy-amazon-robot-middleware',
    version=version,
    packages=find_packages(),
    url='https://github.com/ziplokk1/scrapy-amazon-robot-middleware',
    license='LICENSE.txt',
    author='Mark Sanders',
    author_email='sdscdeveloper@gmail.com',
    install_requires=REQUIREMENTS,
    description='Scrapy middleware module which uses image parsing to submit a captcha response to amazon.',
    include_package_data=True
)
