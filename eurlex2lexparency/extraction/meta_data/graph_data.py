from rdflib import Graph
from rdflib.plugins.stores.sparqlstore import NSSPARQLWrapper
from SPARQLWrapper import XML, CSV

from eurlex2lexparency.utils import prefixes, bind_prefixes


def new_graph(*args, **kwargs) -> Graph:
    return bind_prefixes(Graph(*args, **kwargs))


class Inquirer(NSSPARQLWrapper):
    """ Basically another wrapper for rdf-lib SPARQLEStore. """
    nsBindings = prefixes

    def __init__(self, endpoint, return_format=XML):
        super(Inquirer, self).__init__(endpoint)
        self.setReturnFormat(return_format)

    def __call__(self, query):
        self.setQuery(query)
        r = self.query()
        if self.returnFormat == CSV:
            return r.convert().decode('utf-8').split('\n')
        return r.convert()
