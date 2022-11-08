import os
from collections import Counter
from typing import Dict, List
from lxml import etree as et
from abc import ABCMeta, abstractmethod
import logging
from string import ascii_lowercase

from eurlex2lexparency.extraction.meta_data.cdm_data import ActMetaData
from eurlex2lexparency.transformation.config import FINAL_TITLE
from eurlex2lexparency.utils import xtml
from .article import Article


class SimpleDocument:
    def __init__(self, source: et.ElementBase, language: str, logger=None):
        self.source = source
        self.language = language
        self.meta_data = ActMetaData(self.language)
        self.articles: Dict[str, Article] = {}
        self.definitions: List[et.ElementBase] = []
        self.logger = logger or logging.getLogger()

    @property
    def stubbed(self):
        return self.source.find("body") is None

    @classmethod
    def load(cls, file_path: str):
        source = et.ElementTree(
            file=file_path, parser=et.HTMLParser(encoding="utf-8")
        ).getroot()
        language = source.attrib["lang"]
        self = cls(source=source, language=language)
        self.articles = {
            e.attrib["id"]: Article(source=e, language=language)
            for e in source.xpath('//article[@class!="lxp-mesa-article" and @id]')
        }
        self.meta_data = ActMetaData.parse(source)
        self.definitions = source.xpath('.//*[@class="lxp-definition"]')
        return self

    @property
    def metas_inserted(self):
        return "prefix" in self.source.attrib

    def _insert_metas(self):
        if self.metas_inserted:
            return
        head = self.source.find("./head")
        self.source.attrib["vocab"] = "http://schema.org/"
        self.source.attrib["lang"] = self.language.lower()
        self.source.attrib["prefix"] = " ".join(
            map(lambda args: "{}: {}".format(*args), self.meta_data.get_prefixes())
        )
        for meta in self.meta_data.to_rdfa():
            head.append(meta)

    def cleanse(self, domain, id_local):
        for anchor in self.source.xpath(f'//a[@href="/{domain}/{id_local}/"]'):
            xtml.unfold(anchor)
        targets = set(
            href[1:] for href in self.source.xpath("//a/@href") if href.startswith("#")
        )
        ids = set(self.source.xpath("//*/@id"))
        unfounds = targets - ids
        self.logger.info(f"There are {len(unfounds)} unfound reference targets.")
        for href in unfounds:
            for anchor in self.source.xpath(f'//a[@href="#{href}"]'):
                xtml.unfold(anchor)

    def dump(self, target_path):
        """Write result to storage"""
        self._insert_metas()
        et.ElementTree(self.source).write(
            os.path.join(target_path, "refined.html"), encoding="utf-8"
        )

    def dumps(self):
        self._insert_metas()
        return et.tostring(self.source, method="html", encoding="utf-8")


class DocumentTransformer(SimpleDocument, metaclass=ABCMeta):
    @abstractmethod
    def transform(self):
        pass

    def embed(self):
        """Embedding of the core attributes.
        Note that the order matters. E.g., the definition embedding makes
        use of the element IDs, but these are changed when doing the
        embedding of the articles.
        """
        # assignment of self.cover.meta.id is done within md.py
        for article in self.articles.values():
            article.embed()
        self.make_toc_ids_unique()
        self.make_final()

    @abstractmethod
    def locate_title(self):
        pass

    @abstractmethod
    def _split(self):
        """Instead of returning a ready-made article list, it should just
        append to the default one."""
        pass

    @abstractmethod
    def skeletorize(self):
        """Locates Section and Article headings and feeds them
        to a toc-instance."""
        pass

    @abstractmethod
    def reference_definitions(self) -> List[et.ElementBase]:
        """Find definitions"""
        pass

    def link(self):
        for article in self.articles.values():
            article.link()

    def make_toc_ids_unique(self):
        for it in ("container", "article"):
            ids = Counter(self.source.xpath(f'//*[@class="lxp-{it}"]/@id'))
            for id_, count in ids.items():
                if count == 1:
                    continue
                self.logger.warning(
                    f"Change duplicate id: {id_} " f"(appears {count} times)"
                )
                for i, element in enumerate(
                    self.source.xpath(f'//*[@class="lxp-{it}" and @id="{id_}"]')[1:]
                ):
                    element.attrib["id"] = id_ + ascii_lowercase[i]

    def make_final(self):
        for final in self.source.xpath(
            '//article[@id="FIN"]'
            '/div[@class="lxp-heading"]'
            '/h1[@class="lxp-ordinate"]'
        ):
            final.text = FINAL_TITLE[self.language]
