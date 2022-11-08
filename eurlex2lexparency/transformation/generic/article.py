"""
Proposal for further splitting of the current structure:
  - the liap module should take bigger part in the nesting.
  - the TableElement class shall assist more in the unfolding
    of the pseudotables.
"""
from functools import lru_cache
from typing import Union
from collections import Counter

from lexref.model import Value
from lxml import etree as et
import re
from operator import attrgetter
from dataclasses import dataclass, field
import logging

from eurlex2lexparency.transformation.generic.definitions import TechnicalTerms

from lexref import Reflector
from lexref.structures import Target

from eurlex2lexparency.utils.xtml import iter_table_columns
from eurlex2lexparency.utils import xtml
from ..utils.generics import VirtualMarkup, LATINS_RE
from ..config import PREAMBLE_NAMES


PATTERN = {
    "CT": {  # Correlation table
        "EN": re.compile("^Correlation table$", flags=re.I),
        "DE": re.compile("^Entsprechungstabelle$", flags=re.I),
        "ES": re.compile("^Tabla de correspondencias$", flags=re.I),
    },
    "AMNT": {  # Amendments
        "EN": re.compile("^Amendments? (of|to) ", flags=re.I),
        "DE": re.compile("^Änderung(en)? der ", flags=re.I | re.U),
        "ES": re.compile("^Modificaciones de(l| la)", flags=re.I),
    },
}


def data_title_2_sub_id(data_title):
    result = data_title.strip("(). " + chr(160))
    if " " in result:
        base, suffix = re.split(r"\s", result, 1)
        if LATINS_RE.match(suffix) is not None:
            suffix = Value.extract_as_number(suffix, "LATIN", "XX")
            return base + suffix
        return base
    return result


@dataclass
class Article:
    """This class is responsible for transformations on article level"""

    source: et.ElementBase
    language: str
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger())
    _footer: et.ElementBase = None

    REFLEX_KWARGS = dict(
        internet_domain="", min_role="leaf", only_treaty_names=True, unclose=True
    )

    @classmethod
    @lru_cache()
    def _annotator(cls, language) -> Reflector:
        return Reflector(language, "annotate", **cls.REFLEX_KWARGS)

    def _extract_hrefs(self, text: str):
        """Just a little helper function"""
        references = self._annotator(self.language)(text)[0]["references"]
        return [t["href"] for t in references]

    @property
    def id(self):
        return self.source.attrib["id"]

    @property
    def e(self) -> et.ElementBase:
        return self.source

    def _simplify_blanks(self):
        for element in self.source.iterdescendants():
            for text_type in ["text", "tail"]:
                if getattr(element, text_type) is not None:
                    setattr(
                        element,
                        text_type,
                        re.sub(r"\s+", " ", getattr(element, text_type)),
                    )

    def _finalize(
        self,
    ):
        self._simplify_blanks()
        self._set_ids()
        self._create_body()
        self._responsify()

    def _create_body(self):
        if self.id == "PRE":
            self.source.attrib["title"] = PREAMBLE_NAMES[self.language]
            self._recital()
            return
        body = et.Element("div", attrib={"class": "lxp-body"})
        heading = self.source.find('./div[@class="lxp-heading"]')
        if heading is not None:
            if (heading.tail or "").strip() != "":
                body.text = heading.tail.strip()
        for element in self.source.iterchildren():
            if element.attrib.get("class") != "lxp-heading":
                body.append(element)
        heading.addnext(body)

    def _recital(self):
        try:  # first come first served:
            item_list = self.source.xpath("./ol")[0]
        except IndexError:
            return
        item_list.attrib["class"] = "lxp-recitals"
        for item in item_list.xpath("./li"):
            item.attrib["class"] = "lxp-recital"

    @property
    def footer(self) -> et.ElementBase:
        if self._footer is None:
            base = self.source.find('./div[@class="lxp-body"]')
            if base is None:
                base = self.source
            self._footer = et.SubElement(base, "div", {"class": "article-footer"})
        return self._footer

    @property
    def container_context(self) -> Union[Target, None]:
        try:
            return Target.create(self.source.getparent().attrib["id"])
        except KeyError:
            return

    def embed(self):
        for anchor in self.source.xpath(".//a[@href and @title]"):
            if not anchor.attrib["href"].startswith("#"):
                if not anchor.attrib["href"].startswith("/"):
                    continue
            anchor.attrib["data-content-heading"] = anchor.attrib.pop("title")

    NON_ASCII = re.compile(r"[^\t-~]", flags=re.U)

    def _set_ids(self):
        """Assign IDs to each list item and article"""
        query = './/li[not(@id) and (not(parent::ul) or @class="definition")]'
        for list_item in self.source.xpath(query):
            list_item.attrib["id"] = "{}-{}".format(
                self.id,
                "-".join(
                    [
                        data_title_2_sub_id(title)
                        for title in list_item.xpath("ancestor-or-self::li/@data-title")
                    ]
                ),
            )
        # Override duplicate IDs
        query = './/li[@id and (not(parent::ul) or @class="definition")]'
        counter = Counter(li.attrib["id"] for li in self.source.xpath(query))
        for id_, count in counter.items():
            if count == 1:
                continue
            for k, dup in enumerate(self.source.xpath(f'//li[@id="{id_}"]')[1:]):
                dup.attrib["id"] = id_ + "--" + str(k + 1)
        # Enforce IDs to be ASCII:
        for li in self.source.xpath(query):
            li.attrib["id"] = self.NON_ASCII.sub("_z_", li.attrib["id"])

    @property
    def amends(self):
        title = self.source.find('./div[@class="lxp-heading"]/h2[@class="lxp-title"]')
        if title is None:
            return  # can't know ... probably not
        title_text = et.tostring(
            title, method="text", encoding="unicode", with_tail=False
        )
        if PATTERN["AMNT"][self.language].match(title_text.strip()) is None:
            return []
        references = self._annotator(self.language)(title_text)[0]["references"]
        return [t["href"] for t in references]

    def link(self):
        self._link_correlation_tables()
        amends = self.amends
        if amends is not None:
            if len(amends) > 1:
                """Article seems to amend more than one document. I.e. no clear
                context. Better skip this one."""
                return
        document_context = None
        container_context = self.container_context
        if amends:
            if amends[0].startswith("/eu/"):
                document_context = amends[0]
                container_context = None
        reflector = Reflector(
            self.language,
            "markup",
            container_context=container_context,
            document_context=document_context,
            **self.REFLEX_KWARGS,
        )
        if self.source.attrib["id"] == "PRE":
            subjects = [self.source]
        else:
            subjects = self.source.xpath(
                './div[@class="lxp-body"] '
                '| ./div[@class="lxp-heading"]/h2[@class="lxp-title"]'
            )
        for element in subjects:
            reflector(element)
        for misplaced in self.source.xpath('.//h1[@class="lxp-ordinate"]/a[@href]'):
            xtml.unfold(misplaced)

    def _link_correlation_tables(self):
        for table in self.source.xpath(".//table"):
            for column in iter_table_columns(table):
                head_text = et.tostring(
                    column[0], method="text", encoding="unicode"
                ).strip()
                head_refs = self._extract_hrefs(head_text)
                document_context = None
                if len(head_refs) == 1:
                    ref = head_refs.pop()
                    if ref.startswith("/eu/"):
                        document_context = ref
                else:
                    continue
                reflector = Reflector(
                    self.language,
                    "markup",
                    document_context=document_context,
                    **self.REFLEX_KWARGS,
                )
                for cell in column:
                    reflector(cell)

    def reference_definitions(self, terms: TechnicalTerms):
        no_definitions = (
            "lxp-math",
            "lxp-definition-term",
            "lxp-title",
            "lxp-ordinate",
        )
        for list_item in self.source.xpath(".//li"):
            if list_item.attrib.get("class") != "lxp-recital":
                terms.append(list_item)
        # aligning definition-links with order of def. appearance
        # is a first approximation to def.-scoping.
        if len(terms.definitions) == 0:
            return
        for descendant in self.source.xpath(".//*"):
            if descendant.attrib.get("class", "") in no_definitions:
                text_parts = ["tail"]
            else:
                text_parts = ["text", "tail"]
            for attrib_name in text_parts:
                if getattr(descendant, attrib_name) is None:
                    continue
                before_text = getattr(descendant, attrib_name)
                reference_map = terms.locate_technical_terms(before_text)
                # noinspection PyTypeChecker
                VirtualMarkup.add_markups(
                    attrib_name,
                    before_text,
                    descendant,
                    reference_map,
                    attrgetter("attrib"),
                )

    def _remove_close_references(self):
        """References to other paragraphs within the
        same article shall not have an anchor
        """
        for anchor in self.source.xpath(".//a[@href]"):
            if anchor.attrib["href"][1:] in [
                _el.attrib["id"] for _el in anchor.xpath("ancestor-or-self::li[@id]")
            ]:
                xtml.unfold(anchor)

    def _responsify(self):
        for element in self.source.xpath(
            './/table[@class="table"] | .//img[@width>=200]'
        ):
            if element.xpath("ancestor::table"):
                continue
            element.addnext(et.Element("div", {"class": "w3-responsive"}))
            if element.tag == "table":
                if "width" in element.attrib:
                    element.attrib.pop("width")
            container = element.getnext()
            container.append(element)
