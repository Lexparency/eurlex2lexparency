from unittest import main
import os

from eurlex2lexparency.transformation.generic.test import TestTransformation
from eurlex2lexparency.transformation.formex.document import FormexTransformer


class TestFormexTransformation(TestTransformation):
    raw = 'document_1.xml'
    refined = 'document_1.html'
    DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    transformer = FormexTransformer
    language = 'EN'

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestFormexCapitalRequirementsGerman(TestTransformation):
    raw = 'crr.xml'
    refined = 'crr.html'
    DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    transformer = FormexTransformer
    language = 'DE'

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestFormexMifidGerman(TestTransformation):
    raw = 'mifid_ii.xml'
    refined = 'mifid_ii.html'
    DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    transformer = FormexTransformer
    language = 'DE'

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestFormexVisaKodexGerman(TestTransformation):
    raw = 'visakodex.xml'
    refined = 'visakodex.html'
    DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
    transformer = FormexTransformer
    language = 'DE'

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


if __name__ == '__main__':
    main()
