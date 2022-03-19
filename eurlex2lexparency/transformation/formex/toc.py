from functools import lru_cache
from anytree import NodeMixin, RenderTree
from lxml import etree as et

from lexref import Reflector

from eurlex2lexparency.utils import xtml
from eurlex2lexparency.transformation.utils.generics import HeadingAnalyzer


class StandardizationError(Exception):
    pass


@lru_cache()
def get_ordinate_standardizer(language):
    reflector = Reflector(language, 'annotate', only_treaty_names=True,
                          internet_domain='')

    def standardise(text):
        if len(text.split()) >= 4:
            raise StandardizationError(f'Could not standardize >>{text}<<.')
        try:
            href = reflector(text)[0]['references'][0]['href']
        except IndexError:
            raise StandardizationError(f'Could not standardize >>{text}<<.')
        if href.startswith('#toc-'):
            return href[5:]
        elif href.startswith('#'):
            return href[1:]

    return standardise


class EmbeddedContentsNode(NodeMixin):

    source_tag_to_target_tag = {
        'LEXP.COMBINED': 'div',
        'ANNEXES': 'Container',
        'DIVISION': 'Container',
        'ARTICLE': 'Leaf',
        'ANNEX': 'Leaf',
        'PREAMBLE': 'Leaf',
        'FINAL': 'Leaf',
    }

    def __init__(self, element: et.ElementBase, language, parent=None):
        self.language = language
        self.analyze = HeadingAnalyzer(self.language)
        self.e = element
        self.h1 = None
        self.h2 = None
        self._transform()
        self.parent = parent
        self.e.attrib['id'] = self.id
        if self.e.tag != 'LEXP.COMBINED':
            if self.e.tag in ('DIVISION', 'ANNEXES'):
                self.e.tag = 'div'
            else:
                self.e.tag = 'article'
        self.instantiate_children()

    def _transform(self):
        if self.e.tag == 'DIVISION':
            assert self.e[0].tag == 'TITLE'
            header = self.e[0]
            assert header[0].tag == 'TI'
            self.h1 = header[0]
            self.h2 = header.find('./STI')
            xtml.unfold(header)
        elif self.e.tag == 'ARTICLE':
            self.h1 = self.e[0]
            assert self.h1.tag == 'TI.ART'
            self.h2 = self.e.find('./STI.ART')
        elif self.e.tag == 'ANNEX':
            header = self.e.find('./TITLE')
            assert header in (self.e[0], self.e[1])  # header could be preceeded by a BIB.INSTANCE element.
            self.h1 = header[0]
            self.h2 = header.find('./STI')
            xtml.unfold(header)
            if self.h2 is None:
                self.h2 = self.e.find('./CONTENTS/GR.SEQ/TITLE/TI')
                if self.h2 is not None:
                    if self.h2.find('./NP') is not None:
                        self.h2 = None
                if self.h2 is not None:
                    xtml.unfold(self.h2.getparent())
        if self.e.tag == 'PREAMBLE':
            self.e.attrib['class'] = 'lxp-preamble'
            return
        if self.h1 is None:
            return
        if self.e.tag == 'DIVISION':
            self.e.attrib['class'] = 'lxp-container'
        else:
            self.e.attrib['class'] = 'lxp-article'
        heading = et.Element('div', attrib={'class': 'lxp-heading'})
        self.h1.tag = 'h1'
        self.h1.attrib['class'] = 'lxp-ordinate'
        xtml.cut_append(heading, self.h1)
        xtml.unfold_redundant_paragraphs(self.h1, 'P')
        if self.h2 is not None:
            self.h2.tag = 'h2'
            self.h2.attrib['class'] = 'lxp-title'
            xtml.cut_append(heading, self.h2)
            xtml.unfold_redundant_paragraphs(self.h2, 'P')
        xtml.push(self.e, heading)

    def instantiate_children(self):
        cls = type(self)
        for child in self.e.xpath('|'.join(['./ACT/PREAMBLE',
                                            './ACT/FINAL',
                                            './ACT/ENACTING.TERMS/ARTICLE',
                                            './ACT/ENACTING.TERMS/DIVISION',
                                            './ANNEX',
                                            './DIVISION',
                                            './ARTICLE',
                                            './ANNEXES'])):
            cls(child, self.language, parent=self)

    def __repr__(self):
        return '<{} id="{}" ordinate="{}" title="{}">'.format(self.e.tag, self.id, self.ordinate, self.title)\
            .replace(' title="None"', '').replace(' ordinate="None"', '').replace(' id="None"', '')

    def __str__(self):
        return str(RenderTree(self))

    @property
    @lru_cache(maxsize=1000)
    def title(self):
        if self.h2 is not None:
            return et.tostring(self.h2, method='text', encoding='unicode').strip()

    @property
    @lru_cache(maxsize=1000)
    def ordinate(self):
        if self.e.tag in ['FINAL', 'PREAMBLE', 'ANNEXES']:
            return self.e.tag.capitalize()
        if self.e.tag == 'LEXP.COMBINED':
            return
        return et.tostring(self.h1, method='text', encoding='unicode').strip()

    @property
    @lru_cache(maxsize=1000)
    def standardized_ordinate(self):
        if self.e.tag in ('ARTICLE', 'ANNEX', 'DIVISION'):
            if self.ordinate == 'ANNEXES':  # TODO: Adapt to other languages!
                return 'ANX_0'  # Annex-article for Annex-contents table, as in 32017R0745
            try:
                return self.analyze(self.ordinate)[0].collated
            except ValueError:
                return 'L_' + str(id(self.e))
        if self.e.tag in ('PREAMBLE', 'FINAL'):
            return self.e.tag[:3]
        if self.e.tag == 'ANNEXES':
            return 'ANX'
        return

    @property
    @lru_cache(maxsize=1000)
    def id(self):
        if self.e.tag == 'LEXP.COMBINED':
            return 'toc'
        if self.standardized_ordinate.split('_')[0] \
                in ('L', 'PRE', 'ART', 'ANX', 'FIN') and self.e.tag != 'ANNEXES':
            # self.e.attrib['id'] = self.standardized_ordinate
            return self.standardized_ordinate
        return 'toc-{}'.format('-'.join(node.standardized_ordinate or '' for node in self.path[1:]))
