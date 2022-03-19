from setuptools import setup


setup(
    name="eurlex2lexparency",
    author="Martin Heimsoth",
    author_email="mail@lexparency.org",
    url="https://github.com/Lexparency/eurlex2lexparency",
    description="Transforming documents from Eur-Lex to Lexparency",
    version="1.0",
    packages=['eurlex2lexparency'],
    install_requires=[
        'lexref',
        'singletonmetaclasss',
        'pandas',
        'cachier',
        'dataclasses',
        'lxml',
        'Pillow',
        'SPARQLWrapper == 1.8.5',
        'rdflib == 4.2.2',
        'SQLAlchemy',
        'urllib3',
        'certifi',
        'anytree',
        'requests',
        'dateparser',
        'beautifulsoup4',
        'html5lib',
        'keepalive',
        'numpy',
    ],
)
