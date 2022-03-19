from functools import lru_cache
from lxml import etree as et

from eurlex2lexparency.utils import xtml
from eurlex2lexparency.transformation.utils.generic_transformer import XMLTransformer
from eurlex2lexparency.utils.xtml import unfold, unfold_redundant_paragraphs, remove
from eurlex2lexparency.transformation.formex.table import Caption


class FormexListTransformer(XMLTransformer):

    def __init__(self, element: et.ElementBase):
        self.original_tag = element.tag
        super().__init__(element)
        self.e.attrib.pop('LEVEL', None)

    @property
    @lru_cache(maxsize=1)
    def type(self):
        return self.e.attrib.pop('TYPE', None)

    @property
    @lru_cache(maxsize=1)
    def target_tag(self):
        if self.type in ("alpha", "ALPHA", "ARAB", "roman", "ROMAN", "OTHER") \
                or self.e.tag in ('GR.SEQ', 'GR.CONSID'):
            return 'ol'
        else:
            if self.type in ("DASH", "NONE"):
                self.e.attrib['class'] = self.type.lower()
            return 'ul'  # side-effect!

    list_tag_to_item_tag = {
        'LIST': 'ITEM',
        'GR.SEQ': 'NP',
        'GR.VISA': 'VISA',
        'GR.CONSID': 'CONSID',
    }

    @property
    def item_tag(self):
        """ Provide expected item tag, depending on original tag. """
        return self.list_tag_to_item_tag[self.original_tag]

    def label_of(self, item: et.ElementBase):
        if self.original_tag in ('GR.CONSID', 'LIST'):
            return item.find('./NP/NO.P')
        if self.original_tag == 'GR.SEQ':
            return item.find('./NO.P')
        return

    def _preprocessing(self):
        if self.e.tag == 'GR.SEQ':
            for number in self.e.xpath('NO.GR.SEQ'):
                p = number.getnext()
                if p.tag != 'P':
                    return
                number.tag = 'NO.P'
                p.tag = 'NP'
                p.insert(0, number)
                proximate = p.getnext()
                if proximate is not None:
                    if proximate.tag == 'LIST':
                        p.append(proximate)

    def _transform(self):
        self._preprocessing()
        self.e.tag = self.target_tag
        for item in self.e.iterchildren(self.item_tag):
            if self.target_tag == 'ol':
                label = self.label_of(item)
                if label is not None:
                    unfold_redundant_paragraphs(label, 'HT')
                    if len(label) > 0:
                        if label[0].tag == 'img':
                            label.tag = 'span'
                            label.attrib['class'] = 'lexp-item-label'
                            next_ = label.getnext()
                            if next_.tag in ('P', 'TXT'):
                                unfold(next_)
                        else:
                            item.attrib['data-title'] = \
                                et.tostring(label, encoding='unicode',
                                            method='text', with_tail=False)
                            # TODO: log a warning here
                            remove(label)
                    else:
                        item.attrib['data-title'] = label.text
                        remove(label)
            unfold_redundant_paragraphs(item, 'NP', 'NO.P', 'TXT', 'ALINEA', 'P')
            item.tag = 'li'
        self._unfold_embedder()
        self._transform_caption()

    def _unfold_embedder(self):
        parent = self.e.getparent()
        if parent.tag == 'P' and (parent.text or '').strip() == '':
            if (self.e.tail or '').strip() == '' and len(parent) == 1:
                unfold(parent)
            else:
                parent.addprevious(self.e)
                if self.e.tail is not None:
                    parent.text = self.e.tail + (parent.text or '')
                    self.e.tail = None

    def _transform_caption(self):
        for title in self.e.xpath('./TITLE[TI[P]]'):
            Caption(title, 'h3')


def paragraph_sequences_to_lists(parent):

    def _to_item(parag: et.ElementBase):
        assert parag[0].tag == 'NO.PARAG'
        label = parag[0]
        parag.attrib['data-title'] = label.text.strip('"')
        xtml.remove(label)
        parag.tag = 'li'
        xtml.unfold_redundant_paragraphs(parag, 'ALINEA', 'P')

    p1 = parent.find('./PARAG[NO.PARAG]')
    while p1 is not None:
        # It could be that two sequences of PARAG elements are separated by
        # a different type of element, e.g. ALINEA; therefore, a simple
        # iteration over the siblings would append elements to the list,
        # that actually don't belong there. Therefore this cumbersome
        # structure.
        list_ = et.Element('ol')
        p1.addprevious(list_)
        list_.append(p1)
        _to_item(p1)
        for item in list_.itersiblings('PARAG'):
            _to_item(item)
            list_.append(item)
        p1 = parent.find('./PARAG[NO.PARAG]')
