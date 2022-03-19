import os
from functools import lru_cache
from inspect import getfile
from logging import getLogger
from urllib.error import URLError, HTTPError
from SPARQLWrapper.Wrapper import POST
from rdflib import ConjunctiveGraph

from eurlex2lexparency.utils.eurlex_request_lock import eurlex_request_queue
from eurlex2lexparency.utils.generics import retry

OP_ENDPOINT = 'https://publications.europa.eu/webapi/rdf/sparql'


prefixes = {
    "corp": "http://publications.europa.eu/resource/authority/corporate-body/",
    "res-type": "http://publications.europa.eu/resource/authority/resource-type/",
    "res-oj": "http://publications.europa.eu/resource/oj/",
    "res-celex": "http://publications.europa.eu/resource/celex/",
    "lang": "http://publications.europa.eu/resource/authority/language/",
    "ev": "http://eurovoc.europa.eu/",
    "eli": "http://data.europa.eu/eli/ontology#",
    "m-app": "http://www.iana.org/assignments/media-types/application/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "cdm": "http://publications.europa.eu/ontology/cdm#",
    "euvoc": "http://publications.europa.eu/ontology/euvoc#"
}


def bind_prefixes(base):
    for prefix, namespace in prefixes.items():
        base.bind(prefix, namespace)
    return base


class SPARQLGraph(ConjunctiveGraph):

    TIMEOUT = 30

    """ Basically a wrapper for rdf-lib SPARQLEStore. """
    def __init__(self, endpoint, default_graph=None):
        super().__init__('SPARQLStore', identifier=default_graph)
        bind_prefixes(self)
        self.open(endpoint)
        self.store._timeout = self.TIMEOUT  # With the default settings it might hang


class SparqlKraken:
    ENDPOINT = OP_ENDPOINT

    def __init__(self, logger=None):
        self.sparql = SPARQLGraph(self.ENDPOINT)
        self.sparql.store.query_method = POST  # query might be too long for GET
        self.logger = logger or getLogger()
        self.templates = {n: t for n, t in self.iter_templates()}

    @property
    @lru_cache()
    def queries(self):
        return {n: t.format for n, t in self.templates.items()}

    @classmethod
    def iter_templates(cls):
        for cl in cls.__mro__:
            if not issubclass(cl, SparqlKraken):
                break
            path = os.path.join(os.path.dirname(getfile(cl)),
                                'sparql_templates')
            if not os.path.isdir(path):
                continue
            for name in os.listdir(path):
                if not name.endswith('.sparql'):
                    continue
                with open(os.path.join(path, name)) as f:
                    yield name.replace('.sparql', ''), f.read()

    @retry(exceptions=(URLError, HTTPError, TimeoutError), tries=3, wait=5)
    def __call__(self, template, **kwargs):
        """ Added some waiting, to not annoy the Eur-lex service too much """
        eurlex_request_queue.wait()
        self.logger.debug(f'Querying {template}.')
        result = self.sparql.query(self.queries[template](**kwargs))
        self.logger.debug(f'Query {template} finished.')
        return result
