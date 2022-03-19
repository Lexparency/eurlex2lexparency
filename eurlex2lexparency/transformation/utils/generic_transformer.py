from abc import ABCMeta, abstractmethod
from lxml import etree as et


class XMLTransformer(metaclass=ABCMeta):

    def __init__(self, element: et.ElementBase):
        self.e = element
        self._transform()

    @abstractmethod
    def _transform(self):
        pass
