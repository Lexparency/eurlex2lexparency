from lxml import etree as et
from enum import Enum
import logging

from eurlex2lexparency.utils import xtml
from eurlex2lexparency.utils.xtml import unfold


class _QuotationClass(Enum):
    inline = 'span'
    block = 'div'


class QuoteTransformer:

    start_to_type = {
        'QUOT.START': _QuotationClass.inline,
        'QUOT.S': _QuotationClass.block
    }

    def __init__(self, start: et.ElementBase, end: et.ElementBase,
                 logger=None):
        self.logger = logger or logging.getLogger()
        self.open = start
        self.close = end
        self.type = self.start_to_type[self.open.tag]
        self._transform()

    def _remove_attribs(self):
        for element in (self.open, self.close):
            for key in element.attrib:
                if key.isupper():
                    element.attrib.pop(key, None)

    def _transform(self):
        if self.open.getparent() == self.close.getparent():
            self._transform_siblings()
        else:
            self._transform_skewed_pair()

    def _transform_skewed_pair(self):
        self.logger.warning("Moving skew quotation marks!")
        fca = self.first_common_ancestor
        if fca == self.open.getparent():
            if (self.close.tail or '').strip() in ',;.':
                # move the closing element
                for ancestor in reversed(self.close.xpath('ancestor::*')):
                    if ancestor != fca:
                        ancestor.addnext(self.close)
                    else:
                        break
                else:  # if no break occurs
                    raise RuntimeError('Could not bring quotes on same level.')
            elif (self.open.tail or '').strip() == '':
                # move opening element down.
                while self.close.getparent() != self.first_common_ancestor:
                    adjacent = self.open.getnext()
                    if adjacent is None:
                        break
                    xtml.push(adjacent, self.open)
        fca = self.first_common_ancestor
        if fca == self.open.getparent() == self.close.getparent():
            self._transform_siblings()
        else:
            # OK. Maybe that's a cheap way ... should work
            xtml.remove(self.open)
            xtml.remove(self.close)

    def _transform_siblings(self):
        self._remove_attribs()
        self.open.tag = self.type.value
        self.open.attrib['class'] = 'lxp-quotation'
        # subsequent transformation asserts open and close are siblings
        self.open.text = self.open.tail
        self.open.tail = None
        for sibling in self.open.itersiblings():
            if sibling == self.close:
                unfold(sibling)
                break
            self.open.append(sibling)

    @property
    def first_common_ancestor(self):
        common_ancestor = None
        for open_ancestor, close_ancestor in zip(self.open.xpath('ancestor::*'),
                                                 self.close.xpath('ancestor::*')):
            if open_ancestor == close_ancestor:
                common_ancestor = open_ancestor
            else:
                break
        return common_ancestor
