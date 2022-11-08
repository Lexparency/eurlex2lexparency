import os
import re
from unittest import TestCase
from abc import ABCMeta
from unittest.mock import Mock

from bs4 import BeautifulSoup
from lexref import Reflector
from lxml import etree as et

from eurlex2lexparency.transformation import DocumentTransformer
from eurlex2lexparency.transformation.generic.article import Article
from eurlex2lexparency.utils import xtml
from eurlex2lexparency.transformation.html.article import Article as HtmlArticle


def rm_blank_lines(text):
    return re.sub(r"\n\s*\n", "\n", text)


class TestTransformation(TestCase, metaclass=ABCMeta):
    raw = None
    refined = None
    language = None
    transformer = DocumentTransformer
    DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
    REFL_KWARGS = Article.REFLEX_KWARGS

    def print_actual(self):
        print(et.tostring(self.actual, encoding="unicode", method="html"), flush=True)

    @classmethod
    def get_parser(cls):
        if cls.raw.endswith(".html"):
            return et.HTMLParser(encoding="utf-8")
        if cls.raw.endswith(".xml"):
            return et.XMLParser()
        raise ValueError("No parser for file {}".format(cls.raw))

    def setUp(self):
        self.maxDiff = None
        Reflector.reset()
        document = et.ElementTree(
            file=os.path.join(self.DATA_PATH, self.raw), parser=self.get_parser()
        ).getroot()
        # noinspection PyArgumentList
        transformed = self.transformer(document, language=self.language, logger=Mock())
        try:
            transformed.transform()
        except Exception as e:
            transformed.dump(self.DATA_PATH)
            raise e
        transformed._insert_metas()
        sauce = BeautifulSoup(
            et.tostring(transformed.source, encoding="unicode", method="html"),
            features="html.parser",
        ).prettify()
        self.actual = et.fromstring(sauce, parser=et.HTMLParser())
        self.expected = et.ElementTree(
            file=os.path.join(self.DATA_PATH, self.refined),
            parser=et.HTMLParser(encoding="utf-8"),
        ).getroot()

    @classmethod
    def setUpClass(cls) -> None:
        HtmlArticle.TEST = True
        Article.REFLEX_KWARGS = dict(
            internet_domain="", min_role="leaf", only_treaty_names=True
        )

    @classmethod
    def tearDownClass(cls) -> None:
        Article.REFLEX_KWARGS = cls.REFL_KWARGS

    def _test_skeleton(self):
        for document in (self.expected, self.actual):
            for article in document.xpath("//article"):
                for subelement in article.iterchildren():
                    xtml.remove(subelement)
        self.assertEqual(
            rm_blank_lines(
                et.tostring(self.expected, encoding="unicode", method="html")
            ),
            rm_blank_lines(et.tostring(self.actual, encoding="unicode", method="html")),
        )

    def _test_articles(self):
        expected_articles = self.expected.xpath("//article")
        actual_articles = self.actual.xpath("//article")
        self.assertEqual(len(expected_articles), len(actual_articles))
        for expected, actual in zip(expected_articles, actual_articles):
            self.assertEqual(
                et.tostring(expected, encoding="unicode"),
                et.tostring(actual, encoding="unicode"),
            )
