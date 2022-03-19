import json
import os
from itertools import product
from sys import platform
from time import sleep

from rdflib import URIRef, Literal

from eurlex2lexparency.extraction.meta_data.handler import default, byify_p
from settings import LEXPATH
from eurlex2lexparency.utils.sparql_kraken import SparqlKraken, prefixes
from eurlex2lexparency.extraction.meta_data.cdm_data import ActMetaData, \
    TitlesRetriever


RESULT_PATH = os.path.join(LEXPATH, 'ELI')


class EliKraken(SparqlKraken):

    if platform == 'linux':
        ENDPOINT = 'http://localhost:7200/repositories/ELI'
    else:
        ENDPOINT = 'http://sleipnir.lexparency.org:7200/repositories/ELI'

    MAX_SLEEP_DURATION = 0

    _aux_mapping = {
        URIRef('http://data.europa.eu/eli/ontology#InForce-inForce'):
            Literal('true', datatype=URIRef('http://www.w3.org/2001/XMLSchema#boolean')),
        URIRef('http://data.europa.eu/eli/ontology#InForce-notInForce'):
            Literal('false', datatype=URIRef('http://www.w3.org/2001/XMLSchema#boolean')),
    }

    def _adapt_values(self, result):
        return [tuple(self._aux_mapping.get(i, i) for i in r) for r in result]

    def __call__(self, *args, **kwargs):
        result = []
        for arg in args:
            r = super().__call__(arg, **kwargs)
            if arg.startswith('subject_predicate_'):
                r = byify_p(r)
            result.extend(r)
        return self._adapt_values(result)

    MILLE = 1000  # parameterize for testing

    def get_celexes(self):
        result = []
        for i in range(self.MILLE):
            ddd = str(i).zfill(3)
            result.extend([str(r[0]) for r in self('celexes_ddd', ddd=ddd)])
            sleep(1)
        return result


kraken = EliKraken()

# noinspection PyProtectedMember
ActMetaData._CELLAR_TRUNC = ActMetaData._eli_resource_trunc_eli
# noinspection PyProtectedMember
ActMetaData._eli_resource_trunc_cdm = ActMetaData._eli_resource_trunc_eli
ActMetaData.kraken = kraken
ActMetaData.ontology_pref = prefixes['eli']
for name, value in ActMetaData.iter_attributes():
    value.cdm_sources = value.cdm_sources + (name,)
ActMetaData.cited_by.cdm_sources = ('cites_by',)
TitlesRetriever.kraken = kraken


if __name__ == '__main__':
    from sys import argv
    celexes = argv[1].split(',')
    for lang, celex in product(('ES',), celexes):
        md = ActMetaData.retrieve(celex, lang)
        with open(os.path.join(RESULT_PATH, f'{celex}_{lang}.json'), encoding='utf-8', mode='w') as f:
            json.dump(md.to_dict(), f, default=default, ensure_ascii=False, indent=2)
