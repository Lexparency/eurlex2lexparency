import re
from collections import namedtuple
from functools import partial
from typing import Tuple

from lexref.structures import StdCoordinate
from lexref.token_sequences import TokenSequences
from lxml import etree as et

from lexref.utils import VirtualMarkup
from lexref.model import Value

from lexref.utils import Span


LATINS_RE = re.compile(
        Value.tag_2_pattern('ES')['LATIN'].pattern.strip('\\b') + '$')


def markup_quotation_marks(e: et.ElementBase):
    """
    :param e: Element whose quotation marks are to be marked up.
    """
    for element in e.xpath('.//*'):
        for attrib in ('text', 'tail'):
            if getattr(element, attrib) is not None:
                setattr(
                    element,
                    attrib,
                    standardize_quotation_marks(getattr(element, attrib))
                )
    quote_pattern = re.compile('(?<![a-z0-9])>>(.{,200}?)<<')
    for element in e.xpath('.//*'):
        for attrib_name in ('text', 'tail'):
            text_tail = getattr(element, attrib_name)
            if text_tail is None:
                continue
            # noinspection PyTypeChecker
            VirtualMarkup.add_markups(
                attrib_name,
                getattr(element, attrib_name),
                element,
                [OnlySpan(Span(*m.span()))
                 for m in quote_pattern.finditer(text_tail)],
                lambda x: {'class': 'lxp-quotation'},
                tag='span'
            )
        for sibling in element.itersiblings():
            if sibling.tag == 'span'\
                    and sibling.attrib.get('class') == 'lxp-quotation':
                sibling.text = sibling.text.strip('<>')
        for child in element.iterchildren():
            if child.tag == 'span'\
                    and child.attrib.get('class') == 'lxp-quotation':
                child.text = child.text.strip('<>')


def standardize_quotation_marks(in_string):
    for quote_mark in [chr(8231), "'", '"']:
        # TODO: This functionaly might be better placed within the
        #  semantics sub-package, since some decisions are language specific
        #  (not to modify expressions like "an institution's liabilities").
        in_string = re.sub(
            r'(?<![a-z0-9]){0}([^{0}]{{,200}}){0}(?=[\s),.])'.format(quote_mark),
            r'>>\g<1><<',
            in_string,
            flags=re.I
        )
    for quote_pair in [(chr(8216), chr(8217)), (chr(8220), chr(8221)),
                       (chr(8222), chr(8220))]:
        in_string = re.sub(
            r'(?<![a-z0-9]){0}([^{1}]{{,200}}){1}(?=[\s),.])'.format(*quote_pair),
            r'>>\g<1><<',
            in_string
        )
    return in_string


OnlySpan = namedtuple('OnlySpan', ['span'])


class HeadingAnalyzer:

    def __init__(self, language):
        self.language = language
        self.TokenSequences = partial(TokenSequences, language)

    def __call__(self, in_text: str) -> Tuple[StdCoordinate, str, str]:
        if not in_text or in_text.startswith('('):
            raise ValueError(f'Input not decomposable: {in_text}')
        first_second_rest = in_text.split(maxsplit=2)
        for _ in range(3 - len(first_second_rest)):
            first_second_rest.append('')
        first, second, rest = first_second_rest
        if LATINS_RE.match(rest):
            second += ' ' + rest
            rest = ''
        co_part = ' '.join((first, second)).strip()
        tss = self.TokenSequences(co_part)
        try:
            coordinate = tss[0][0]
        except IndexError:
            raise ValueError(f'This is not a coordinate: {co_part}.')
        else:
            if coordinate.axis.tag.value == 'named_entity':
                raise ValueError(f'References to named entities a no headers')
        span = coordinate.span
        if span.end != len(co_part):
            if span.end != len(first):
                raise ValueError(f'Input not decomposable: {in_text}')
            co_part = first
            rest = ' '.join((second.strip(), rest.strip()))
        co = coordinate.standardized(self.language)
        if len(rest) == 1:  # e.g. ANNEX II B
            co = StdCoordinate(co.axis, f'{co.value}_{rest}', co.role)
            co_part += f' {rest}'
            rest = None
        return co, co_part, rest or None
