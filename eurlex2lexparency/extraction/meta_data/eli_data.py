import os
from lxml import etree as et
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF
import re
from datetime import date
import requests
from abc import ABC

from eurlex2lexparency.extraction.meta_data.graph_data import new_graph
from eurlex2lexparency.utils import prefixes
from eurlex2lexparency.extraction.generic import Retriever
from eurlex2lexparency.utils import remove
from eurlex2lexparency.celex_manager import CelexCompound


def construct_url_from(celex, consoli_date, language='EN'):
    if consoli_date != date(1900, 1, 1):
        celex_ext = str(CelexCompound.get(celex, consoli_date))
    else:
        celex_ext = celex
    return f'https://eur-lex.europa.eu/legal-content/' \
           f'{language}/ALL/?uri=CELEX:{celex_ext}'


class UrlConstructor(Retriever, ABC):

    @classmethod
    def construct_from(cls, local_path, celex, consoli_date):
        return cls(local_path, construct_url_from(celex, consoli_date))


class EurLexDocumentLandingPage(UrlConstructor):

    @property
    def file_name(self):
        return os.path.join(self.local_path, 'landing.html')

    def open(self):
        return et.ElementTree(file=self.file_name).getroot()

    def retrieve(self):
        landing_page = et.ElementTree(et.fromstring(
            requests.get(self.url).text,
            parser=et.HTMLParser(encoding='utf-8')))
        text = landing_page.find('.//div[@id="text"]')
        if text is not None:
            text.getparent().remove(text)
        os.makedirs(self.local_path, exist_ok=True)
        landing_page.write(self.file_name)
        return landing_page.getroot()


class DocumentEliData(UrlConstructor):

    def __init__(self, local_path, url):
        super().__init__(local_path, url)
        self.landing_page = EurLexDocumentLandingPage(local_path, url).document

    @property
    def file_name(self):
        return os.path.join(self.local_path, 'eli.ttl')

    @staticmethod
    def uri_ref(uri):
        return URIRef(re.sub('^eli:', prefixes['eli'], uri))

    def open(self):
        with open(self.file_name, encoding='utf-8') as f:
            g = Graph().parse(file=f, format='turtle')
        return g

    def retrieve(self):
        g = new_graph()
        for instance in self.landing_page.xpath('/html/head/meta[@about and @typeof]'):
            g.add((
                self.uri_ref(instance.attrib['about']),
                RDF.type,
                self.uri_ref(instance.attrib['typeof'])
            ))
            remove(instance)
        for triple in self.landing_page.xpath(
                '/html/head/meta[@about and @property and @resource]'):
            p = triple.attrib['property']
            if p == 'eli:uri_schema':
                o = Literal(triple.attrib['resource'])
            else:
                o = self.uri_ref(triple.attrib['resource'])
            g.add((
                self.uri_ref(triple.attrib['about']),
                self.uri_ref(p),
                o
            ))
        for triple in self.landing_page.xpath(
                '/html/head/meta'
                '[@about and @property and @content and @datatype]'):
            g.add((
                self.uri_ref(triple.attrib['about']),
                self.uri_ref(triple.attrib['property']),
                Literal(triple.attrib['content'],
                        datatype=self.uri_ref(triple.attrib['datatype']))
            ))
        for triple in self.landing_page.xpath(
                '/html/head/meta[@about and @property and @content and @lang]'):
            g.add((
                self.uri_ref(triple.attrib['about']),
                self.uri_ref(triple.attrib['property']),
                Literal(triple.attrib['content'], lang=triple.attrib['lang'])
            ))

        g.serialize(destination=self.file_name, format='turtle')

        return g
