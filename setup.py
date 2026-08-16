from setuptools import setup, find_packages

setup(
    name='spotifz',
    version='1.0.0',
    description='A thin wrapper to search Spotify personal library',
    url='https://github.com/junkmechanic/spotifz',
    author='junkmechanic',
    author_email='khanna89ankur@gmail.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.9',
    ],
    keywords='spotify search fzf',
    packages=find_packages(),
    python_requires='>=3.9',
    install_requires=['spotipy>=2.26.0'],
    scripts=['bin/spotifz'],
)
