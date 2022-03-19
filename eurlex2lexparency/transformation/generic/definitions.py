import re
from collections import namedtuple
from typing import List
from lxml import etree as et

from lexref.utils import Span

SpanAttributes = namedtuple('SpanAttributes', ['span', 'attrib'])

normal_term = re.compile(r'^[/\sa-zA-Z0-9-]{,200}$')


def term_validity(term) -> bool:
    if normal_term.match(term) is None:
        return False
    try:
        int(term)
    except ValueError:
        pass
    else:
        return False
    if len(term) == 1 and term.lower() == term:
        return False
    return True


multi_blank = re.compile(r'\s+')


def add_delimiters(word: str) -> str:
    if len(word) == 1 or word == word.upper():
        return rf'\b{word}\b'
    return rf'\b{word}[a-z]{{,2}}\b'


_patterns = {
    'EN': {
        'definitions_title': 'Definition',
    },
    'DE': {
        'definitions_title': 'Definition',
    },
    'ES': {
        'definitions_title': 'Definición',
    }
}


class TechnicalTerms:

    def __init__(self, language):
        # TODO: Handle declination and plural of defined words
        self.language = language
        patterns = _patterns[self.language]
        self.definitions_title = patterns['definitions_title']
        self.definitions = {}

    def create_attribs(self, term, target):
        return {'href': '#' + target,
                'title': '{}: {}'.format(self.definitions_title, term)}

    def append(self, def_element: et.ElementBase):
        def_id = def_element.attrib.get('id')
        if def_id is None:
            return
        is_def = False
        for quotation in def_element.xpath(
                './span[@class="lxp-quotation"]'):  # side-effect!
            if len(quotation) > 0:
                continue
            term = multi_blank.sub(
                ' ', et.tostring(quotation, method='text',
                                 encoding='unicode', with_tail=False).strip())
            if not term_validity(term):
                continue
            self.definitions[term] = self.create_attribs(term, def_id)
            quotation.attrib['class'] = "lxp-definition-term"
            is_def = True
        if not is_def:
            return
        def_element.attrib['class'] = "lxp-definition"

    @property
    def pattern(self):
        return re.compile('|'.join(map(add_delimiters, self.definitions.keys())))

    def get_definition(self, word):
        for cut in range(3):
            key = word if cut == 0 else word[:-cut]
            try:
                result = self.definitions[key]
            except KeyError:
                continue
            if key != word:
                self.definitions[word] = result
            return result

    def locate_technical_terms(self, in_text: str) -> List[SpanAttributes]:
        if len(self.definitions) is None:
            return []
        term_stack = []
        for m in self.pattern.finditer(in_text):
            term_stack.append(SpanAttributes(
                Span(*m.span()), self.get_definition(m.group())))
        return term_stack
