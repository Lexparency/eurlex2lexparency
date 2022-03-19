import logging
import re
from functools import lru_cache
from typing import List, Dict
from urllib.parse import urlencode, parse_qs, urlparse

from lxml import etree as et
from abc import ABCMeta
from datetime import date, datetime

from eurlex2lexparency.extraction.meta_data.title_parsing import TitleParser


hosted_celex = re.compile(r"^3(19|20)[0-9]{2}[RLFD][0-9]{4}$")
_typoed_celex = re.compile(r"^3(?P<yy>[0-9]{2})(?P<remainder>[RLFD][0-9]{4})$")
corrigendum = re.compile(r"^[0-9]{5}[RLFD][0-9]{4}R(?P<number>\([0-9]{1,2}\))$")
html_tag = re.compile('<[^>]*>')
# the following pattern should not match the word "no". Neither any other word
# starting with "no..." like, "norma". Note that preceding non-breaking spaces
# do not match "\b". Therefore, the cumbersome negative lookbehind assertion.
wrong_no = re.compile(r'(?<![A-Za-zóéíá])(n[. ]{,2}°|n\. ?o)', flags=re.I | re.U)


def correct_no(inp: str):
    if inp is None:
        return
    return wrong_no.sub(chr(8470), inp)


def strip_tags(inp):
    if inp is None:
        return inp
    return html_tag.sub('', inp).strip()


def remote_url_from_celex(language, celex):
    return f"https://eur-lex.europa.eu/legal-content/{language}/ALL/?" \
           + urlencode({'uri': f'CELEX:{celex}'})


def url_from_celex(language, celex):
    if hosted_celex.match(celex) is not None:
        return f'/eu/{celex}/'
    m = _typoed_celex.match(celex)
    if m is not None:
        if m.group('yy') < '45':
            return '/eu/320' + m.group('yy') + m.group('remainder') + '/'
        return '/eu/319' + m.group('yy') + m.group('remainder') + '/'
    return remote_url_from_celex(language, celex)


def href_2_celex(ref):
    return parse_qs(urlparse(ref).query)['uri'][0].replace('celex:', '')


def default(x):
    if type(x) is date:
        return x.strftime('%Y-%m-%d')
    return x


def uniquify(elements):
    return sorted({et.tostring(e): e for e in elements}.values(),
                  key=lambda el: et.tostring(el))


CORRIGENDUM = {
    'DE': 'Berichtigung',
    'EN': 'Corrigendum',
    'ES': 'Corrección de errores',
}


class Anchor:

    __slots__ = ['href', 'text', 'title']

    def __init__(self, href, text, title):
        self.href = href
        self.text = strip_tags(text)
        self.title = strip_tags(title)

    logger = logging.getLogger()

    @classmethod
    def create(cls, id_local, long_title, language):
        parser = TitleParser.get(language)
        corr = corrigendum.match(id_local)
        if language == 'ES':
            long_title = correct_no(long_title)
        if corr is not None:
            return cls(
                remote_url_from_celex(language=language, celex=id_local),
                CORRIGENDUM[language] + ' ' + corr.group('number'), None)
        try:
            title_data = parser(long_title)
        except (ValueError, IndexError, AttributeError, TypeError):
            cls.logger.warning(f'Unable to parse {repr(long_title)}')
            title_data = dict()
        href = url_from_celex(language, id_local)
        # TODO: Handle references to the Treaties
        return cls(
            href,
            title_data.get('id_human', id_local),
            title=title_data.get('title_essence', long_title)
        )

    @property
    def hosted(self):
        return self.href.startswith('/eu/')

    def to_rdfa(self, relationship, language) -> List[et.ElementBase]:
        """ E.g.
        <meta property="eli:cites" resource="th://x.co/doc1"/>
        <meta about="th://x.co/doc1" property="lxp:id_human" content="Act I"/>
        <meta about="th://x.co/doc1" property="eli:title" content="First Act"/>
        """
        result = [et.Element('meta', attrib={'property': relationship,
                                             'resource': self.href}),
                  et.Element('meta', attrib={'about': self.href,
                                             'content': self.text,
                                             'lang': language,
                                             'property': 'lxp:id_human'})]
        if self.title is not None:
            result += [et.Element('meta', attrib={'about': self.href,
                                                  'content': self.title,
                                                  'lang': language,
                                                  'property': 'eli:title'})]
        return result

    def to_dict(self):
        result = {'href': self.href, 'text': self.text, 'title': self.title}
        if self.title is None:
            result.pop('title')
        return result

    @classmethod
    def from_dict(cls, d):
        if 'title' not in d:
            d['title'] = None
        return cls(**d)

    def __repr__(self):
        return self.__class__.__name__ \
               + f'(href="{self.href}",' \
                 f' text="{self.text}",' \
                 f' title="{self.title}")'

    def __eq__(self, other):
        return repr(self) == repr(other)

    def __hash__(self):
        return hash(self.href)


STUB_TEMPLATE = """
<!DOCTYPE html>
<html lang="{language}"
      vocab="http://schema.org/"
      prefix="eli: http://data.europa.eu/eli/ontology# lxp: http://lexparency.org/ontology#">
 <head>{head}</head>
</html>
"""


class DressedAttribute:

    __slots__ = ['cdm_sources', 'prefix', 'multi']

    def __init__(self, cdm_sources, prefix, multi=False):
        if type(cdm_sources) is str:
            self.cdm_sources = (cdm_sources,)
        elif cdm_sources is None:
            self.cdm_sources = ()
        else:
            assert type(cdm_sources) is tuple
            self.cdm_sources = cdm_sources
        self.prefix = prefix
        self.multi = multi

    @staticmethod
    def is_void(value):
        if value is None:
            return True
        if type(value) in (set, tuple, list):
            return len(value) == 0
        return False


class InconsistentDataError(Exception):
    pass


class DocumentMetaData(metaclass=ABCMeta):

    _logger = logging.getLogger()

    _prefixes = [("eli", "http://data.europa.eu/eli/ontology#"),
                 ("lxp", "http://lexparency.org/ontology#")]

    def get_prefixes(self):
        return self._prefixes

    def plausibility_check(self):
        for name, value in self.items():
            if type(value) is date:
                if value.year < 1950:
                    delattr(self, name)

    @classmethod
    def iter_attributes(cls, hide_=True):
        for name, value in cls.__dict__.items():
            if type(value) is DressedAttribute:
                if name.startswith('_') and hide_:
                    yield name[1:], value
                else:
                    yield name, value

    @classmethod
    @lru_cache()
    def name_2_attribute(cls, hide_=True) -> Dict[str, DressedAttribute]:
        return {name: value for name, value in cls.iter_attributes(hide_=hide_)}

    cdm_2_attrib_name = None

    @classmethod
    def get_cdm_2_attrib_name(cls):
        if type(cls.cdm_2_attrib_name) is dict:
            return cls.cdm_2_attrib_name
        result = {}
        for name, value in cls.iter_attributes():
            for source in value.cdm_sources:
                result[source] = name
        cls.cdm_2_attrib_name = result
        return result

    _eli_resource_trunc_cdm = 'http://publications.europa.eu/resource/eli/'
    _eli_resource_trunc_eli = 'http://data.europa.eu/eli/'

    def __init__(self, language, **kwargs):
        self.language = language

        for name, attribute in self.name_2_attribute(hide_=False).items():
            key = name
            if name.startswith('_'):
                key = name[1:]
            setattr(self, name, kwargs.get(key, set() if attribute.multi else None))

    def items(self):
        for name, _ in self.iter_attributes():
            value = getattr(self, name)
            if value is None:
                continue
            if type(value) in (set, list):
                if len(value) == 0:
                    continue
            yield name, value

    def __repr__(self):
        result = [f'{name}=' + repr(value)
                  for name, value in self.items()
                  if not DressedAttribute.is_void(value)]
        result.insert(0, 'language=' + repr(self.language))
        return self.__class__.__name__ + '({})'.format('\n, '.join(result))

    def to_dict(self):
        def _to_json(a):
            if type(a) in (str, int, float, bool, date):
                return a
            if type(a) is Anchor:
                return a.to_dict()
            if type(a) in (set, list, tuple):
                return list({hash(i): _to_json(i) for i in a}.values())
            raise RuntimeError(f'What about {a}?')

        return {name: _to_json(attribute) for name, attribute in self.items()
                if not DressedAttribute.is_void(attribute)}

    @classmethod
    def from_dict(cls, d: dict):
        for key, value in d.items():
            if type(value) is dict:
                d[key] = Anchor.from_dict(value)
            elif type(value) is list:
                if len(value) > 0:
                    if type(value[0]) is dict:
                        d[key] = {Anchor.from_dict(i) for i in value}
                    else:
                        d[key] = set(value)
                else:
                    d[key] = set()
            elif (key.startswith('date_')
                  or key.endswith('_date')
                  or '_date_' in key) \
                    and type(value) is not date:
                d[key] = datetime.strptime(value, '%Y-%m-%d').date()
        return cls(**d)

    def to_rdfa(self):
        result = []
        for name, attribute in self.items():
            if type(attribute) is Anchor:
                result.extend(
                    attribute.to_rdfa('eli:' + name, self.language.lower()))
            elif type(attribute) in (list, set):
                for item in attribute:
                    if type(item) is Anchor:
                        result.extend(
                            item.to_rdfa(f'eli:{name}', self.language.lower()))
                    else:
                        result.append(self.attribute_2_meta(name, item))
            else:
                result.append(self.attribute_2_meta(name, attribute))
        return uniquify(result)

    def attribute_2_meta(self, name, attribute):

        def type_and_string(value):
            if type(value) is date:
                return 'date', value.strftime('%Y-%m-%d')
            if type(value) is int:
                return 'integer', str(value)
            if type(value) is bool:
                return 'boolean', str(value).lower()
            return None, str(value)

        prefix = self.name_2_attribute()[name].prefix
        meta_element = et.Element('meta', {'property': f'{prefix}:{name}'})
        t, v = type_and_string(attribute)
        if (v.startswith('http://') or v.startswith('https://') or v.startswith('/eu/')) \
                and name not in ('source_url', 'source_iri'):
            key = 'resource'
        else:
            key = 'content'
        meta_element.attrib[key] = v
        if t is None and key == 'content':
            meta_element.attrib['lang'] = self.language.lower()
        elif t is not None:
            meta_element.attrib['datatype'] = 'xsd:' + t
        return meta_element

    def dumps(self):
        return '\n'.join(
            map(lambda x: et.tostring(x, encoding='unicode', method='html'),
                self.to_rdfa()))

    def to_html_stub(self):
        return STUB_TEMPLATE.format(language=self.language, head=self.dumps())

    def join(self, it, relax=False):
        for name, attribute in self.iter_attributes():
            my_value = getattr(self, name)
            its_value = getattr(it, name)
            if attribute.multi:
                my_value.update(set(its_value))
            elif None in (my_value, its_value) and my_value != its_value:
                setattr(self, name, my_value or its_value)
            else:
                if my_value != its_value and not relax:
                    raise InconsistentDataError(f'{name}: {my_value} != {its_value}')
        return self  # You know. For chaining.


def byify_p(results):
    return [(str(p) + '_by', o) for p, o in results]
