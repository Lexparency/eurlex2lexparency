from __future__ import annotations
import json
import os
from datetime import date
from urllib import parse
from urllib.error import URLError
from functools import reduce, lru_cache

from rdflib import Graph
from cachier import cachier
from lxml import etree as et
import logging
import re
from lxml.etree import XMLSyntaxError
from collections import defaultdict

from eurlex2lexparency.celex_manager.celex import CelexBase
from eurlex2lexparency.extraction.meta_data.handler import byify_p, default, corrigendum, CORRIGENDUM, correct_no
from settings import LEXPATH
from eurlex2lexparency.utils.generics import retry
from eurlex2lexparency.celex_manager.eurlex import country_mapping
from eurlex2lexparency.utils.sparql_kraken import SparqlKraken, prefixes

from .handler import DocumentMetaData, Anchor, DressedAttribute
from . import treaties as tmd
from .short_titles import PopularTitles
from .title_parsing import TitleParser, title_upmarker

ELI_PATH = os.path.join(LEXPATH, 'ELI')


class EmptyMetaDataException(Exception):
    pass


def path_of(name):
    return os.path.join(os.path.dirname(__file__), 'static', name)


def to_python(x):
    if x is None:
        return None
    return x.toPython()


# noinspection HttpUrlsUsage
@cachier(next_time=True, pickle_reload=False)
def local_graph():
    with open(path_of('op_resource_authority.ttl'), encoding='utf-8') as f:
        graph = Graph().parse(file=f, format='turtle')
    graph.bind('euvoc', "http://publications.europa.eu/ontology/euvoc#")
    graph.bind("skos", "http://www.w3.org/2004/02/skos/core#")
    return graph


class Resolver:
    """ Callables to retrieve human readable expression that, belonging to
        given set of IRIs.

        This is actually a workaround to include data that is not obtained via
        the SPARQL query. This may be due to the fact that the corresponding
        graph data is not loaded into the triple store, or to avoid that the
        query becomes too cumbersome.
    """

    types = {
        'ResourceType': prefixes['res-type'],  # (not used any more)
        'Corporate': prefixes['corp'],
    }

    with open(path_of('standard_mappings.json'), encoding='utf-8') as f:
        standard_mappings = json.load(f)

    def __init__(self, mapping_type, language):
        self.type = mapping_type
        self.prefix = self.types[mapping_type]
        self.language = language
        self.mapping = self.get_mapping()

    def _get_new_mapping(self):
        graph = local_graph()
        results = graph.query(
            kraken.queries['new_resolver_map'](type=self.type,
                                               language=self.language))
        return {self.unprefix(item): str(label) for item, label in results}

    def get_mapping(self):
        try:
            return {i['key']: i['value']
                    for i in self.standard_mappings[self.type][self.language]}
        except KeyError:
            return self._get_new_mapping()

    def unprefix(self, uriref: str):
        assert uriref.startswith(self.prefix)
        return uriref[len(self.prefix):]

    def __call__(self, uri):
        if uri is None:
            return None
        if not uri.startswith(self.prefix):
            return None
        uri = uri[len(self.prefix):]
        if uri in ("OP_DATPRO", "DATPRO"):
            return None
        return self.mapping.get(uri, None)


class Kraken(SparqlKraken):

    def __init__(self):
        super().__init__()
        self.extendeds = self._extend_templates()

    celex_filter = re.compile(
        r"\?(?P<subject>[a-zA-Z_]+) "
        r"cdm:resource_legal_id_celex '{celex}'\^\^xsd:string .")

    alt_filter = (" ?{name} cdm:resource_legal_id_celex ?filter_celex .\n"
                  "  FILTER( str(?filter_celex) = '{{celex}}' ) .").format

    def _extend_templates(self):
        extendeds = []
        for key, t in list(self.templates.items()):
            new_t = t
            for m in self.celex_filter.finditer(t):
                new_t = new_t.replace(
                    m.group(), self.alt_filter(name=m.group('subject')))
            if new_t == t:
                continue
            extendeds.append(key)
            self.templates[f"{key}.1"] = t
            self.templates[f"{key}.2"] = new_t
        return extendeds

    def __call__(self, *args, **kwargs):
        result = []
        for arg in args:
            if arg in self.extendeds:
                for i in (1, 2):
                    r = super().__call__(f"{arg}.{i}", **kwargs)
                    if len(r) > 0:
                        break
            else:
                r = super().__call__(arg, **kwargs)
            if arg.startswith('subject_predicate_'):
                r = byify_p(r)
            result.extend(r)
        return result


kraken = Kraken()


# noinspection HttpUrlsUsage
class ActMetaData(DocumentMetaData):

    kraken = kraken
    ontology_pref = prefixes['cdm']

    domain = DressedAttribute(None, 'lxp')
    id_local = DressedAttribute('resource_legal_id_celex', 'eli')
    in_force = DressedAttribute('resource_legal_in-force', 'eli')
    _type_document = DressedAttribute('work_has_resource-type', 'eli')
    _first_date_entry_in_force = DressedAttribute(
        'resource_legal_date_entry-into-force', 'eli')
    _date_no_longer_in_force = DressedAttribute(
        'resource_legal_date_end-of-validity', 'eli')
    date_document = DressedAttribute('work_date_document', 'eli')
    date_publication = DressedAttribute('work_date_creation_legacy', 'eli')
    date_applicability = DressedAttribute(None, 'eli')
    _based_on = DressedAttribute('resource_legal_based_on_concept_treaty', 'eli')
    passed_by = DressedAttribute('work_created_by_agent', 'eli', True)
    serial_number = DressedAttribute('resource_legal_number_natural_celex', 'lxp')
    title_essence = DressedAttribute(None, 'lxp')
    title = DressedAttribute('title', 'eli')
    version = DressedAttribute(None, 'lxp')
    version_implements = DressedAttribute(None, 'lxp', True)
    source_url = DressedAttribute(None, 'lxp')
    pop_title = DressedAttribute(None, 'lxp')
    pop_acronym = DressedAttribute(None, 'lxp')
    id_human = DressedAttribute(None, 'lxp')
    source_iri = DressedAttribute(None, 'eli')
    is_about = DressedAttribute('is_about', 'eli', True)
    amends = DressedAttribute('resource_legal_amends_resource_legal', 'eli', True)
    amended_by = DressedAttribute('resource_legal_amends_resource_legal_by', 'eli', True)
    # WARNING: Citations need to be handled with care, result list can get too long.
    cites = DressedAttribute('work_cites_work', 'eli', True)
    cited_by = DressedAttribute('work_cites_work_by', 'eli', True)
    completes = DressedAttribute(
        'resource_legal_completes_resource_legal', 'eli', True)
    completed_by = DressedAttribute(
        'resource_legal_completes_resource_legal_by', 'eli', True)
    corrects = DressedAttribute(
        'resource_legal_corrects_resource_legal', 'eli', True)
    corrected_by = DressedAttribute(
        'resource_legal_corrects_resource_legal_by', 'eli', True)
    repeals = DressedAttribute(
        ('resource_legal_implicitly_repeals_resource_legal',
         'resource_legal_repeals_resource_legal'), 'eli', True)
    repealed_by = DressedAttribute(
        ('resource_legal_implicitly_repeals_resource_legal_by',
         'resource_legal_repeals_resource_legal_by'), 'eli', True)

    _referrers = ('amends', 'amended_by', 'completes', 'completed_by',
                  'corrects', 'corrected_by', 'repeals', 'repealed_by',
                  'cites', 'cited_by')

    @lru_cache()
    def as_anchor(self) -> Anchor:
        return Anchor.create(self.id_local, self.title, self.language)

    # noinspection PyPep8Naming
    @classmethod
    def from_ELI(cls, id_local, language):
        with open(os.path.join(ELI_PATH, f'{id_local}_{language}.json'),
                  encoding='utf-8') as f:
            amd = cls.from_dict(json.load(f))
        return amd

    @classmethod
    def from_dict(cls, d: dict) -> ActMetaData:
        self = super().from_dict(d)
        return self

    @classmethod
    def cached_retrieve(cls, id_local, language, file_path, only_local=False):
        try:
            with open(file_path, encoding='utf-8') as f:
                amd = cls.from_dict(json.load(f))
            return amd
        except FileNotFoundError:
            if only_local:
                amd = cls.from_ELI(id_local, language)
            else:
                try:
                    amd = cls.retrieve(id_local, language)
                except TimeoutError:
                    amd = cls.from_ELI(id_local, language)
        os.makedirs(file_path.replace('head.json', ''), exist_ok=True)
        with open(file_path, mode='w', encoding='utf-8') as f:
            json.dump(amd.to_dict(), f,
                      ensure_ascii=False, indent=2, default=default)
        return amd

    @classmethod
    @retry(exceptions=(URLError, XMLSyntaxError), tries=3, wait=3)
    def retrieve(cls, celex, language):
        self = cls(language)
        lang3 = country_mapping.get(two=language)
        self.source_iri = 'http://publications.europa.eu/resource/celex/' + celex
        self.id_local = celex
        results = cls.kraken('act_predicate_object', 'subject_predicate_act',
                             celex=celex, lang3=lang3)
        for p in ('title', 'is_about'):
            r = cls.kraken(f'act_{p}_lang', celex=celex,
                           language=language.lower(), lang3=lang3)
            results.extend([(p, v) for (v,) in r])
        if not results:
            raise EmptyMetaDataException(f'Empty set for {celex}.')
        for property_, value in results:
            if str(property_) == prefixes['owl'] + 'sameAs':
                if value.startswith(cls._eli_resource_trunc_cdm):
                    value = str(value).replace(cls._eli_resource_trunc_cdm,
                                               cls._eli_resource_trunc_eli)
                    self.source_iri = str(value)
                    continue
            elif property_.startswith(cls.ontology_pref):
                property_ = property_[len(cls.ontology_pref):]
            elif type(property_) is str:
                pass
            elif not property_.startswith('http'):
                property_ = property_.toPython()
            else:
                continue
            name = cls.get_cdm_2_attrib_name().get(property_)
            if name is None:
                continue
            if name == 'passed_by':
                value = self._resolve_passing_body(value)
                if value is None:
                    continue
            else:
                value = value.toPython()
            if cls.name_2_attribute()[name].multi:
                getattr(self, name).add(value)
            else:
                setattr(self, name, value)
        self.set_title_data()
        self.enhance_referrers()
        self.retrieve_citations()
        self.popularize()
        return self

    def retrieve_citations(self):
        lang3 = country_mapping.get(two=self.language)
        for predicate, template in [('cites', 'act_cites_title'),
                                    ('cited_by', 'title_cites_act')]:
            attribute = getattr(self, predicate)
            for celex, title in self.kraken(template,
                                            celex=self.id_local, lang3=lang3):
                attribute.add(Anchor.create(celex, title, self.language))

    def add_changers(self):
        """ might help for updating purposes. """
        raise NotImplementedError()

    def set_title_data(self):
        if not hasattr(self, 'title'):
            return
        if self.title is None:
            return
        if self.language == 'ES':
            # noinspection PyTypeChecker
            self.title = correct_no(self.title)
        parser = TitleParser.get(self.language)
        for tag in (r'<p class="lxp-title_essence">', '</p>'):
            self.title = self.title.replace(tag, '')
        data = parser(self.title)
        if data.get('id_human') is not None:
            self.id_human = data.get('id_human')
        if self.id_human == self.id_local or self.id_human is None:
            # noinspection PyTypeChecker
            self.id_human = CelexBase.from_string(self.id_local) \
                .human_id(self.language)
        self.title_essence = data.get('title_essence')
        if self.title_essence is not None:
            self.title = title_upmarker(self.title, self.title_essence)
        # TODO: Currently, the TitlesRetriever cannot yet handle celex
        # TODO:    as input. This is required in order to convert these
        # TODO:    parsed referrers to Anchors.
        # self.amends |= set(data.get('amends'))
        # self.repeals |= set(data.get('repeals'))

    _CELLAR_TRUNC = 'http://publications.europa.eu/resource/cellar/'
    _CELEX_TRUNC = 'http://publications.europa.eu/resource/celex/'

    def enhance_referrers(self):
        combined = reduce(
            lambda a, b: a | b,
            [set(d for d in getattr(self, r) if type(d) is not Anchor)
             for r in self._referrers]
        )
        cellar_2_anchor = TitlesRetriever(self.language, combined) \
            .get_anchors()
        for name in self._referrers:
            referrer = getattr(self, name)
            if len(referrer) == 0:
                continue
            # TODO: clarify: how to deal with referrals that are not provided
            #  via cellar ID
            for x in list(referrer):
                referrer.remove(x)
                try:
                    referrer.add(cellar_2_anchor[x])
                except KeyError:
                    self._logger.warning(f"No handling for reference {x}")

    def __init__(self, language, **kwargs):
        self._resolve_passing_body = Resolver('Corporate', language.lower())
        super().__init__(language, **kwargs)
        self.domain = 'eu'
        self.consist_in_force()

    def to_dict(self):
        d = super().to_dict()
        d['language'] = self.language
        return d

    @property
    def based_on(self):
        return self._based_on

    @based_on.setter
    def based_on(self, value):
        if type(value) is Anchor:
            self._based_on = value
        else:
            try:
                self._based_on = \
                    tmd.cached_retrieve(value, self.language).as_anchor()
            except KeyError:
                return

    def skip_external_citations(self):
        for attr in ('cites', 'cited_by'):
            ref = getattr(self, attr)
            filtered = {a for a in ref if a.href.startswith('/eu/')}
            if filtered == ref:
                continue
            setattr(self, attr, filtered)

    def popularize(self):
        """
        Assigns popular titles and acronym, if exist.
        """
        short_title = PopularTitles().get_short_title(
            str(self.id_local), self.language)
        if short_title is not None:
            pop_title, pop_acronym = short_title
            if pop_title != self.pop_title:
                self.pop_title = pop_title
            if pop_acronym != self.pop_acronym:
                self.pop_acronym = pop_acronym

    @property
    def type_document(self):
        return self._type_document

    @type_document.setter
    def type_document(self, value):
        self._type_document = value.split('/')[-1].split('_')[0]

    @property
    def first_date_entry_in_force(self):
        return self._first_date_entry_in_force

    @first_date_entry_in_force.setter
    def first_date_entry_in_force(self, value):
        """ If there is an existing date, select the earlier of the two. """
        if self._first_date_entry_in_force:
            if value > self._first_date_entry_in_force:  # no change required
                return
        if value <= date(1945, 1, 1):
            return
        self._first_date_entry_in_force = value

    @property
    def date_no_longer_in_force(self):
        return self._date_no_longer_in_force

    @date_no_longer_in_force.setter
    def date_no_longer_in_force(self, value):
        if str(value) == '9999-12-31':
            self._date_no_longer_in_force = None
            return
        if value <= date(1945, 1, 1):
            return
        self._date_no_longer_in_force = value
        if self.in_force and self._date_no_longer_in_force <= date.today():
            self.in_force = False

    @date_no_longer_in_force.deleter
    def date_no_longer_in_force(self):
        self._date_no_longer_in_force = None

    def coalesce(self, other):
        for name, value in self.items():
            if type(value) is set:
                value.update(getattr(other, name, {}))
            elif getattr(other, name, None) is not None and value is not None:
                setattr(self, name, value)

    _custom_namespace = {
        'eli': 'http://data.europa.eu/eli/ontology#',
        'lxp': 'http://lexparency.org/ontology#'
    }

    _predicate_pattern = re.compile(
        '^({})'.format('|'.join(_custom_namespace.values())))

    @classmethod
    def parse(cls, e: et.ElementBase):
        default_iri = 'http://lexparency.org'
        g = Graph()
        for pair in cls._custom_namespace:
            g.bind(*pair)
        g.parse(data=et.tostring(e, encoding='unicode'),
                publicID=default_iri,
                format='rdfa')
        self = cls(e.attrib['lang'].upper())
        anchors = defaultdict(dict)
        for s, p, o in g:
            if cls._predicate_pattern.match(str(p)) is None:
                continue
            predicate = cls._predicate_pattern.sub('', str(p))
            value = o.toPython()
            if str(s) == default_iri:
                if predicate not in self._referrers + ('based_on',):
                    # anchors have to be built first
                    attribute = getattr(self, predicate, None)
                    if type(attribute) is set:
                        attribute.add(value)
                    else:
                        setattr(self, predicate, value)
                else:
                    # noinspection PyStatementEffect
                    anchors[value]
            else:
                anchors[str(s)][predicate] = value
        anchors = {target: Anchor(target.replace(default_iri, ''),
                                  kwargs.get('id_human', target),
                                  kwargs.get('title'))
                   for target, kwargs in list(anchors.items())}
        for s, p, o in g:
            if cls._predicate_pattern.match(str(p)) is None:
                continue
            predicate = cls._predicate_pattern.sub('', str(p))
            if str(s) != default_iri:
                continue
            if predicate in self._referrers + ('based_on',):
                try:
                    getattr(self, predicate).add(anchors[str(o)])
                except AttributeError:
                    setattr(self, predicate, anchors[str(o)])
        return self

    def fill_implementeds(self):
        changers = set()
        for change in ('amended_by', 'repealed_by',
                       'corrected_by', 'completed_by'):
            changers.update(set(a.href for a in getattr(self, change)))
        # noinspection PyUnresolvedReferences
        for href in self.version_implements - changers:
            parsed_href = parse.unquote(href)
            text = parsed_href.strip('/').split('/')[-1].split(':')[-1]
            if corrigendum.match(text) is not None:
                text = CORRIGENDUM[self.language] + ' ' + text
            # noinspection PyUnresolvedReferences
            self.amended_by.add(Anchor(href, text, None))

    def remove_self_reference(self):
        self_ref = f'/eu/{self.id_local}/'

        def filtered(a_set):
            return {a for a in a_set if a.href != self_ref}

        for attr in self._referrers:
            setattr(self, attr, filtered(getattr(self, attr)))

    def remove_from_citations(self):
        """ if document is amended by another one, clear that there is a citation """
        other_refs = reduce(
            lambda x, y: x | y,
            [{a.href for a in getattr(self, attr)} for attr in self._referrers
             if not attr.startswith('cite')]
        )

        def filtered(cite_set):
            return {a for a in cite_set if a.href not in other_refs}

        for attr in self._referrers:
            if attr.startswith('cite'):
                setattr(self, attr, filtered(getattr(self, attr)))

    def consist_in_force(self):
        if self.repealed_by:
            self.in_force = False

    def cleanse(self):
        self.fill_implementeds()
        self.remove_self_reference()
        self.remove_from_citations()
        self.consist_in_force()


class TitlesRetriever:

    kraken = kraken

    def __init__(self, language, cellar_ids):
        self.lang_3 = country_mapping.get(two=language) \
            if len(language) == 2 else language
        self.lang_2 = country_mapping.get(three=self.lang_3)
        self.cellar_ids = cellar_ids

    @property
    def filter(self):
        return ' || '.join(map('?work = <{}>'.format, self.cellar_ids))

    @property
    def query(self):
        return self.kraken.queries['title_retriever_base'](lang_3=self.lang_3,
                                                           filter=self.filter)

    @retry(exceptions=(URLError, XMLSyntaxError, AttributeError), tries=3, wait=3)
    def get_anchors(self):
        if len(self.cellar_ids) == 0:
            return dict()
        result = self.kraken.sparql.query(self.query)
        return {
            str(cellar): Anchor.create(id_local.toPython(),
                                       to_python(title),
                                       self.lang_2)
            for cellar, id_local, title in result
        }


def set_logger(logger: logging.Logger):
    Anchor.logger = logger
    ActMetaData._logger = logger
    kraken.logger = logger
