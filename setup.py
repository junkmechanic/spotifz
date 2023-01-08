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
        'Programming Language :: Python :: 3.7',
    ],
    keywords='spotify search fzf',
    packages=find_packages(),
    python_requires='>=3.5',
    install_requires=['spotipy@git+ssh://git@github.com/plamere/spotipy'],
    scripts=['bin/spotifz'],
)
