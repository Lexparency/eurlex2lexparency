from setuptools import setup, find_packages

setup(
    name="eurlex2lexparency",
    author="Martin Heimsoth",
    author_email="mail@lexparency.org",
    url="https://github.com/Lexparency/eurlex2lexparency",
    description="Transforming documents from Eur-Lex to Lexparency",
    version="1.2.3",
    packages=find_packages(include=["eurlex2lexparency", "eurlex2lexparency.*"],
                           exclude=["*.tests"]),
    package_data={
        "eurlex2lexparency.celex_manager": [
            "sparql_templates/*.sparql",
            "doQuery_envelope_template.xml",
        ],
        "eurlex2lexparency.extraction.meta_data": [
            "sparql_templates/*.sparql",
            "static/*",
        ],
        "eurlex2lexparency.extraction.meta_data.bulk": [
            "sparql_templates/*.sparql",
        ],
    },
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
