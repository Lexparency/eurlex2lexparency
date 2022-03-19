import logging
import re

from lxml import etree as et

from eurlex2lexparency.transformation import DocumentTransformer
from eurlex2lexparency.transformation.config import repealed_by
from eurlex2lexparency.transformation.formex.document import FormexTransformer
# noinspection PyProtectedMember
from eurlex2lexparency.transformation.html.document import CreepyNotFoundException, \
    CreepyRedirectException, _OldFashionedOriginalAct, _ModernOriginalAct, \
    _ModernConsolidatedAct, _ActProposal, _OldFashionedConsolidatedAct
from eurlex2lexparency.transformation.utils import TransformingRepealerError
from eurlex2lexparency.utils import xtml


def get_transformer(element: et.ElementBase,
                    language, logger) -> DocumentTransformer:
    """ Factory to check for the correct transformer to be used """
    fmt = {'html': 'html', 'LEXP.COMBINED': 'fmx'}[element.tag]
    standardizer = get_standardizer(language, fmt)
    if element.tag == 'html':
        if standardizer is not None:
            element = et.fromstring(
                standardizer(et.tostring(element, method='html', encoding='unicode')),
                parser=et.HTMLParser()
            )
        class_freq = xtml.analyze_attrib_frequency(element, 'class')
        if "alert alert-warning" in class_freq:
            div = element.xpath('//div[@class="alert alert-warning"]')
            if 'The requested document does not exist.' in \
                    et.tostring(div, encoding='unicode', method='text'):
                raise CreepyNotFoundException('Not Found', 'html')
            href = str(div.xpath('./a/@href')[0])
            raise CreepyRedirectException('Eurlex redirects.', href)
        if len(element.xpath('//txt_te')) == 1:
            return _OldFashionedOriginalAct(element, language, logger=logger)
        if 'ti-art' in class_freq:
            # New style document class. As used in CRR
            return _ModernOriginalAct(element, language, logger=logger)
        if 'title-article-norm' in class_freq:
            # New style consolidated. As consolidated CRR
            return _ModernConsolidatedAct(element, language, logger=logger)
        if {'Normal', 'num'}.issubset({i[0] for i in class_freq.most_common(10)}):
            return _ActProposal(element, language, logger=logger)
        p = len(element.xpath('//p'))
        p_style = len(element.xpath('//p[@style]'))
        if 1. - 2. * (p - p_style) / (p + p_style) > 0.9:
            return _OldFashionedConsolidatedAct(element, language, logger=logger)
        try:
            if element.find('./body/p[@class="hd-modifiers"]')\
                    .text.lower().startswith(repealed_by[language]):
                raise TransformingRepealerError
        except AttributeError:
            pass
        raise NotImplementedError("New transform type found.")
    elif element.tag == 'LEXP.COMBINED':
        if standardizer is not None:
            element = et.fromstring(
                standardizer(et.tostring(element, encoding='unicode')),
                parser=et.XMLParser()
            )
        return FormexTransformer(element, language, logger=logger)
    else:
        raise NotImplementedError("New transform type found.")


def transform(element: et.ElementBase,
              language, logger=None) -> DocumentTransformer:
    transformer = get_transformer(
        element, language, logger or logging.getLogger())
    transformer.transform()
    return transformer


def get_standardizer(language, fmt='html'):
    if language == 'ES':
        n_o = {'html': 'n<span class="super">o</span>',
               'fmx': 'n.<HT TYPE="SUP">o</HT>'}[fmt]

        def standardizer(in_string):
            """ n°, n<span class="super">o</span>   --> chr(8470) """
            result = re.sub(n_o, chr(8470), in_string, flags=re.IGNORECASE)
            if fmt == 'html':
                result = re.sub(r'>([0-9]+|[a-z])\)', r'>(\g<1>)', result)
            return result
    else:
        standardizer = None
    return standardizer
