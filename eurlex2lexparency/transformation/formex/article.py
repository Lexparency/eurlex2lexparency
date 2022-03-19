from anytree import LevelOrderIter
from lxml import etree as et
from copy import deepcopy

from eurlex2lexparency.transformation.formex.toc import EmbeddedContentsNode
from eurlex2lexparency.utils import xtml
from ..generic.article import Article as AbstractArticle
from .formula import formex_to_latex
from .table import FormexTableTransformer
from .list import FormexListTransformer, paragraph_sequences_to_lists
from .quote import QuoteTransformer


class Article(AbstractArticle):

    def __init__(self, element: et.ElementBase,
                 language, transform=False, **kwargs):
        super().__init__(element, language, **kwargs)
        if transform:
            self.transform()

    def transform(self):
        # TODO: insert body-element per article (class="lxp-body")
        self._mesa_content()
        self.sub_leaf_titles()
        self._transform_lists()
        self._pack_quoted_contents()
        if self.id == 'PRE':
            self._preamble_processing()
        elif self.id == 'FIN':
            self._final_processing()
        self._paragraph_sequences_to_lists()
        self._handle_equations()
        self._transform_tables()
        self._definition_lists()
        self._handle_footnotes()
        self._resolve_article_substructure()
        self._post_processing()
        self._finalize()

    def _resolve_article_substructure(self):
        while self.source.xpath('.//DIVISION | .//ARTICLE'):
            node = EmbeddedContentsNode(
                self.source.xpath('.//DIVISION | .//ARTICLE')[0],
                self.language)
            for sub_node in LevelOrderIter(node):
                if sub_node.e.tag == 'article':
                    Article(sub_node.e, language=self.language,
                            logger=self.logger, transform=True)
                    sub_node.e.attrib['class'] = 'lxp-sub-article'
                if sub_node.e.tag == 'div' \
                        and sub_node.e.attrib['class'] == 'lxp-container':
                    sub_node.e.attrib['class'] = 'lxp-sub-container'

    @property
    def skeleton(self):
        return xtml.subskeleton(self.source)

    def sub_leaf_titles(self):
        for slt in self.source.xpath('.//TITLE[TI[NP]]'):
            xtml.unfold(slt[0])
            xtml.unfold(slt[0])
            no_p = slt[0]
            assert no_p.tag == 'NO.P'
            no_p.tag = 'span'
            no_p.attrib['class'] = 'lexp-item-label'
            xtml.unfold(slt[1])
            no_p_text = et.tostring(no_p, encoding='unicode', method='text', with_tail=False)
            slt.tag = 'h{}'.format(str(no_p_text.count('.') + 2))

    def _post_processing(self):
        for a in self.source.xpath('.//ALINEA[P]'):
            if (a.text or '').strip() == '' and a[0].tag == 'P':
                xtml.unfold(a[0])
        for p in self.source.xpath('.//ALINEA'):
            p.tag = 'p'
        self.source.tag = 'article'
        for li in self.source.xpath('.//*[@IDENTIFIER]'):
            li.attrib.pop('IDENTIFIER')
        self.source.attrib.pop('IDENTIFIER', None)
        for date in self.source.xpath('.//DATE'):
            date.tag = 'span'
            date.attrib['data-value'] = date.attrib.pop('ISO')
            date.attrib['data-type'] = 'date'
        if self.id.split('_')[0] in ('ANX', 'L'):
            # Move h2 element (secondary title) on top
            self._annex_handling()
        self._sub_divs()
        for p in self.source.xpath('.//P'):
            p.tag = 'p'
        for ft in self.source.xpath('.//FT[@TYPE="NUMBER" or @TYPE="DECIMAL"]'):
            ft.tag = 'span'
            ft.attrib['class'] = ft.attrib.pop('TYPE').lower()
        for ht in self.source.xpath('.//HT[@TYPE="BOLD"]'):
            parent = ht.getparent()
            if parent.tag in ('h1', 'h2', 'h3'):
                xtml.unfold(ht)
            else:
                ht.tag = 'b'
                ht.attrib.pop('TYPE')
        for title in self.source.xpath('.//STI'):
            title.tag = 'h3'
            xtml.unfold_redundant_paragraphs(title, 'p')

    @property
    def empty_preamble(self):
        if self.id != 'PRE':
            return False
        if et.tostring(self.source, method='text').strip() == '':
            return True
        return False

    def _mesa_content(self):
        for quote in self.source.xpath('.//QUOT.S'):
            for marker in quote.xpath('.//QUOT.START | .//QUOT.END'):
                xtml.remove(marker)
            quote.tag = 'div'
            quote.attrib['class'] = 'lxp-quote-block'
            if 'LEVEL' in quote.attrib:
                quote.attrib.pop('LEVEL')
            if quote[0].tag in ('DIVISION', 'ARTICLE', 'ANNEX'):
                for e in quote.xpath('./DIVISION | ./ARTICLE | ./ANNEX'):
                    node = EmbeddedContentsNode(e, self.language)
                    for sub_node in LevelOrderIter(node):
                        if sub_node.e.tag == 'article':
                            Article(sub_node.e, language=self.language,
                                    logger=self.logger, transform=True)
                            sub_node.e.attrib['class'] = 'lxp-mesa-article'
                        if sub_node.e.tag == 'div' \
                                and sub_node.e.attrib['class'] == 'lxp-container':
                            sub_node.e.attrib['class'] = 'lxp-mesa-container'
            elif quote[0].tag == 'PARAG':
                paragraph_sequences_to_lists(quote)

    def _definition_lists(self):
        for dlist in self.source.xpath('.//DLIST'):
            separator = dlist.attrib.pop('SEPARATOR', '')
            dlist.attrib.pop('TYPE', None)
            dlist.tag = 'ul'
            dlist.attrib['class'] = 'definitions'
            for item in dlist.xpath('./DLIST.ITEM'):
                if item[0].tag == 'PREFIX':
                    item.attrib['data-title'] = item[0].text or ''
                    xtml.remove(item[0])
                item.tag = 'li'
                item.attrib['class'] = 'definition'
                term = item.find('TERM')
                term.tag = 'span'
                term.attrib['class'] = 'definition-term'
                term.tail = ' {} '.format(separator) + (term.tail or '')
                body = item.find('DEFINITION')
                body.tag = 'span'
                body.attrib['class'] = 'definition-body'

    def _annex_handling(self):
        for child in self.source.iterchildren():
            if child.tag == 'BIB.INSTANCE':
                xtml.remove(child)
        for h in self.source.xpath('./h1 | ./h2'):
            for sub_element in h.xpath('./TI | ./TI/P | ./P'):
                xtml.unfold(sub_element)
        contents = self.source.find('./CONTENTS')
        if contents is not None:
            xtml.unfold(contents)
        self._annex_sub_structure()

    def _annex_sub_structure(self):
        # e.g. 31962R0031
        for sub_d in self.source.xpath('./DIVISION'):
            EmbeddedContentsNode(sub_d, self.language)
        for leaf in self.source.xpath('.//article'):
            Article(leaf, language=self.language,
                    logger=self.logger, transform=True)

    def _handle_footnotes(self):
        for k, note in enumerate(self.source.xpath(
                './/NOTE')):
            xtml.unfold_redundant_paragraphs(note, 'P')
            marker = et.Element('sup')
            marker.append(et.Element('a', {'href': f'#{self.id}-note_{k + 1}'}))
            marker[0].text = '({})'.format(k + 1)
            note.addprevious(deepcopy(marker))
            xtml.push(note, marker[0])
            note[0].tag = 'sup'
            note.attrib['id'] = note[0].attrib.pop('href')[1:]
            note.attrib['class'] = 'footnote'
            xtml.remove(note)
            note.tail = None
            self.footer.append(note)
            note.tag = 'p'
            for key in note.attrib:
                if key.isupper():
                    note.attrib.pop(key)

    def _sub_divs(self):
        for subdivision in self.source.xpath('./SUBDIV'):
            # TODO: adapt to new lxp-heading and sub-container convention!
            subdivision.tag = 'div'
            subdivision.attrib['class'] = 'fmx-subdiv'
            if subdivision[0].tag == 'TITLE':
                xtml.unfold_redundant_paragraphs(subdivision[0], 'TI', 'P')
                subdivision[0].tag = 'h3'

    def _final_processing(self):
        for element in self.source.xpath('|'.join(('.//SIGNATURE ',
                                                   './/SIGNATORY ',
                                                   './/PL.DATE'))):
            element.attrib['id' if element.tag == 'SIGNATURE' else 'class'] = \
                element.tag.lower()
            element.tag = 'div'
        self.source.attrib['class'] = 'lxp-final'
        heading = et.Element('div', attrib={'class': 'lxp-heading'})
        et.SubElement(heading, 'h1', attrib={'class': 'lxp-ordinate'}).text = \
            'Final'
        xtml.push(self.source, heading)

    def _preamble_processing(self):
        for element in self.source.xpath('|'.join(('.//PREAMBLE.INIT',
                                                   './/PREAMBLE.FINAL',
                                                   './/GR.CONSID.INIT'))):
            if element.tag == 'GR.CONSID.INIT':
                parent = element.getparent()
                if parent[0] == element and (parent.text or '').strip() == '':
                    parent.addprevious(element)
            element.attrib['id'] = element.tag.lower()
            element.tag = 'p'

    def _pack_quoted_contents(self):
        for start in self.source.xpath('.//QUOT.START'):
            end = self.source.find(
                './/QUOT.END[@ID="{}"]'.format(start.attrib['REF.END']))
            if end is None:
                self.logger.warning('Unmatched QUOT-Elements.')
                xtml.remove(start)
                continue
            assert end.attrib['REF.START'] == start.attrib['ID']
            QuoteTransformer(start, end, logger=self.logger)

    def _paragraph_sequences_to_lists(self):
        paragraph_sequences_to_lists(self.source)

    def _transform_tables(self):
        for table in self.source.xpath('.//TBL'):
            FormexTableTransformer(table)
        for table_group in self.source.xpath('.//GR.TBL'):
            table_group.tag = 'div'
            table_group.attrib['class'] = 'table-group'
            title = table_group.find('./TITLE')
            if title is not None:
                title.tag = 'h3'
                xtml.unfold_redundant_paragraphs(title, 'TI', 'P')

    def _transform_lists(self):
        for list_ in self.source.xpath('.//LIST '
                                       '| .//GR.SEQ '
                                       '| .//GR.VISA '
                                       '| .//GR.CONSID'):
            FormexListTransformer(list_)
        free_standing_list_item = self.source.find('.//NP[NO.P]')
        while free_standing_list_item is not None:
            list_ = et.Element('GR.SEQ')
            free_standing_list_item.addprevious(list_)
            for sibling in list_.itersiblings():
                if sibling.tag == 'NP':
                    list_.append(sibling)
                else:
                    break
            FormexListTransformer(list_)
            free_standing_list_item = self.source.find('.//NP[NO.P]')

    def _handle_equations(self):
        for formula in self.source.xpath('//FORMULA | //FORMULA.S'):
            formex_to_latex(formula)
