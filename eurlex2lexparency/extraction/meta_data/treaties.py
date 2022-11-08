from datetime import timedelta
from urllib.error import URLError
from lxml.etree import XMLSyntaxError
from cachier import cachier

from eurlex2lexparency.extraction.meta_data.handler import (
    DocumentMetaData,
    Anchor,
    remote_url_from_celex,
    DressedAttribute,
)
from eurlex2lexparency.extraction.meta_data.short_titles import TreatyAcronyms
from eurlex2lexparency.utils.generics import retry
from eurlex2lexparency.utils.sparql_kraken import SparqlKraken

EU_AUTH = "http://publications.europa.eu/ontology/authority/"


class TreatyMetaData(DocumentMetaData):

    _SELF_HOSTED = ("TEU", "TFEU", "CHAR")
    ID_2_SOURCE_URL = {
        "EEA": "https://eur-lex.europa.eu/legal-content/{}/TXT/?uri=celex:21994A0103%2801%29".format,
        "EURATOM": "https://eur-lex.europa.eu/legal-content/{}/TXT/?uri=CELEX:12012A/TXT".format,
        "TEEC": "https://eur-lex.europa.eu/legal-content/{}/TXT/?uri=celex:11957E/TXT".format,
    }
    TRUNC = "http://publications.europa.eu/resource/authority/treaty/"

    source_iri = DressedAttribute(None, "eli")
    id_local = DressedAttribute(None, "eli")
    source_url = DressedAttribute(None, "eli")
    title = DressedAttribute(None, "eli")
    date_document = DressedAttribute(None, "eli")
    version = DressedAttribute(None, "lxp")
    pop_acronym = DressedAttribute(None, "lxp")

    kraken = type("Kraken", (SparqlKraken,), {})()

    @classmethod
    @retry(exceptions=(URLError, XMLSyntaxError), tries=3, wait=3)
    def retrieve(cls, resource_iri, language):
        self = cls(language.lower())
        self.source_iri = resource_iri
        local_iri = resource_iri.replace(cls.TRUNC, "")
        self.id_local = local_iri.split("_")[0]
        results = cls.kraken(
            "treaty_metadata", resource_iri=resource_iri, language=self.language
        )
        for s, p, o in results:
            if str(p) == f"{EU_AUTH}celex_root":
                self.source_url = remote_url_from_celex(
                    language=language.upper(), celex=str(o)
                )
            elif str(p) == "http://www.w3.org/2004/02/skos/core#prefLabel":
                self.title = o.toPython()
            elif str(p) == "http://purl.org/dc/terms/created":
                self.date_document = o.toPython()
                if "_" not in local_iri:
                    self.version = "initial"
                else:
                    # noinspection PyUnresolvedReferences
                    self.version = self.date_document.strftime("%Y%m%d")
        # noinspection PyTypeChecker
        self.pop_acronym = TreatyAcronyms.get(self.id_local, language.upper())
        if type(self.source_url) is not str:
            try:
                # noinspection PyTypeChecker
                self.source_url = cls.ID_2_SOURCE_URL[self.id_local](language)
            except KeyError:
                pass
        return self

    @property
    def self_hosted(self):
        return self.id_local in self._SELF_HOSTED

    def as_anchor(self) -> Anchor:
        return Anchor(
            f"/eu/{self.id_local}/" if self.self_hosted else self.source_url,
            self.pop_acronym,
            self.title,
        )


@cachier(stale_after=timedelta(50), pickle_reload=False)
def cached_retrieve(resource_iri, language) -> TreatyMetaData:
    amd = TreatyMetaData.retrieve(resource_iri, language)
    return amd
