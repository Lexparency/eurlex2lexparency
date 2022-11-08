import unittest
import os

from eurlex2lexparency.transformation.generic.test import TestTransformation
from eurlex2lexparency.transformation.html.document import (
    _ModernOriginalAct,
    _OldFashionedOriginalAct,
    _ModernConsolidatedAct,
    _OldFashionedConsolidatedAct,
    _ActProposal,
)


class TestHtmlTransformer(TestTransformation):
    DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
    language = "EN"

    def setUp(self):
        self.maxDiff = None
        super().setUp()


class TestModernOriginalTransformation(TestHtmlTransformer):
    raw = "modern_1_raw.html"
    refined = "modern_1_refined.html"
    transformer = _ModernOriginalAct

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestOldFashionedOriginalTransformation(TestHtmlTransformer):
    raw = "old_1_raw.html"
    refined = "old_1_refined.html"
    transformer = _OldFashionedOriginalAct

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestOldFashionedConsolidatedTransformation(TestHtmlTransformer):
    raw = "old_consolidated_raw.html"
    refined = "old_consolidated_refined.html"
    transformer = _OldFashionedConsolidatedAct
    language = "DE"

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestOldFashionedOriginalTransformationDde(TestHtmlTransformer):
    raw = "EUHb_de_raw.html"
    refined = "EUHb_de_refined.html"
    transformer = _OldFashionedOriginalAct
    language = "DE"

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestModernConsolidatedAct(TestHtmlTransformer):
    raw = "moderncons_1_raw.html"
    refined = "moderncons_1_refined.html"
    transformer = _ModernConsolidatedAct

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


class TestActProposal(TestHtmlTransformer):
    raw = "proposal_raw.html"
    refined = "proposal_refined.html"
    transformer = _ActProposal
    language = "DE"

    def test_skeleton(self):
        self._test_skeleton()

    def test_articles(self):
        self._test_articles()


if __name__ == "__main__":
    unittest.main()
