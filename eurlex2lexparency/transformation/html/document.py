""" Classes for standardization of legal content.
    TODO: Relocation of footnotes for old-version documents.
"""
from lxml import etree as et
from abc import ABCMeta, abstractmethod
from enum import Enum
import re
from typing import Dict
from warnings import warn
from copy import deepcopy

from eurlex2lexparency.extraction import textify
from eurlex2lexparency.extraction.meta_data.handler import href_2_celex, url_from_celex
from eurlex2lexparency.transformation.generic import definitions

from eurlex2lexparency.utils import xtml
from ..utils.generics import LATINS_RE, markup_quotation_marks
from ..generic.document import DocumentTransformer
from ..config import PREAMBLE_NAMES, TOC_HEADS
from .article import Article
from .toc import TableOfContents, NodeMarker


class CreepyRedirectException(Exception):
    def __init__(self, message, target):
        super().__init__(message, target)
        self.target = target


class CreepyNotFoundException(Exception):
    def __init__(self, message, format_):
        super().__init__(message, format_)
        self.format = format_


class DocumentType(Enum):
    NEW_ORIG = 1
    OLD_ORIG = 2
    NEW_CONS = 3


class _Document(DocumentTransformer, metaclass=ABCMeta):
    """This class is responsible for the transformations on document level"""

    doc_type = None
    itemization_type = None

    def standardize_items(self):
        alph = re.compile(r"([0-9]+|[a-z]|[ivx]+)\)")
        nump = re.compile(r"([1-9][0-9]+)\.{}{{3}}".format(chr(160)))
        for d in self.source.iterdescendants():
            if d.text is None:
                continue
            if alph.match(d.text):
                d.text = "(" + d.text
            if nump.match(d.text):
                d.text = nump.sub(r"(\g<1>)", d.text, count=1)

    def transform(self):
        self.standardize_items()
        self._document_pre_processing()
        self.locate_title()
        self.skeletorize()
        self.articles = self._split()
        self.reference_definitions()
        self.link()
        self.embed()

    def _split(self) -> Dict[str, Article]:
        return {
            article.attrib["id"]: Article(
                article, self.itemization_type, self.language, logger=self.logger
            )
            for article in self.source.xpath(".//article")
        }

    def make_preamble(self, title):
        # insert and prepare preamble
        xtml.push(
            self.source.find("./body"),
            et.Element(
                "article", attrib={"class": "lxp-preamble", "id": "PRE", "title": title}
            ),
        )
        preamble = self.source.find('./body/article[@id="PRE"]')
        for sibling in preamble.itersiblings():
            if sibling.attrib.get("class") in ("lxp-container", "lxp-article"):
                break
            preamble.append(sibling)
        else:  # no break occurred
            raise RuntimeError("Document is just a gigantic preamble?")

    def _document_pre_processing(self):
        """Prepare data, so the optimist is not disappointed

        1. Remove empty paragraph elements
        2. Unfold nested leaves.
            Some parts of an eur-lex document (mainly annexes) are
            aggregated into div elements. However, since the subsequent
            transformation procedures assume that article content
            relies flat within the document, those div elements are
            unfolded.
        3. Remove crappy contents table.
            Some eur-lex documents contain a crappy version of a
            contents table. Since this transformation routine is able
            to construct its contents table by itself, the provided
            version is deleted
        4. Standardize quotation marks
        """
        body = self.source.find("body")
        class_freq = xtml.analyze_attrib_frequency(body, "class")
        for p in body.xpath(".//p"):  # 1
            if p.text is None or (p.text == "" and len(p) == 0):
                xtml.unfold(p)
        if "separator" in class_freq:  # 2
            for separator in body.xpath('//hr[@class="separator"]'):
                neighbours = [separator.getprevious(), separator.getnext()]
                for neighbour in neighbours:
                    if (
                        neighbour.tag == "div"
                        and neighbour.attrib.get("class") != "final"
                    ):
                        annex_titles = neighbour.xpath('./p[@class="long-title"]')
                        if len(annex_titles) in (1, 2):
                            xtml.migrate_attributes(
                                annex_titles[0],
                                "class",
                                {"long-title": "leaf-heading-ordinate"},
                            )
                            if len(annex_titles) == 2:
                                xtml.migrate_attributes(
                                    annex_titles[0],
                                    "class",
                                    {"long-title": "leaf-heading-title"},
                                )
                        elif len(annex_titles) > 2:
                            warn("Suspiciously many header elements " "for an annex")
                        xtml.unfold(neighbour)
                xtml.remove(separator)
        self._remove_crappy_contents_table(body, class_freq)
        markup_quotation_marks(body)

    @abstractmethod
    def _remove_crappy_contents_table(self, body, class_freq):
        pass

    def skeletorize(self):
        def custom_textify(e):
            e_copy = deepcopy(e)
            xtml.strip_subelements(
                e_copy,
                "|".join(
                    (
                        './/a[@class="footnote" or @class="marker-start"]',
                        './/span[@class="marker-end"]',
                    )
                ),
            )
            return textify(e_copy, with_tail=False, simplify_blanks=True)

        # preparation of the marker
        marker = NodeMarker(
            self._heading_title_eligibility,
            self._heading_ordinate_eligibility,
            custom_textify,
            language=self.language,
        )
        # Marking the header elements
        body = self.source.find("body")
        for element in list(body.iterchildren()):
            marker(element.getprevious(), element, element.getnext())

        TableOfContents.collect_from(body)
        self.make_preamble(PREAMBLE_NAMES[self.language].capitalize())

    @abstractmethod
    def _heading_ordinate_eligibility(self, element):
        pass

    @abstractmethod
    def _heading_title_eligibility(self, element, doc_type):
        pass

    def reference_definitions(self):
        """Find definitions"""
        terms = definitions.TechnicalTerms(self.language)
        for article in self.articles.values():
            article.reference_definitions(terms)


class _ModernOriginalAct(_Document):

    doc_type = DocumentType.NEW_ORIG
    itemization_type = "tabled"
    classes_old_to_new = {
        "doc-sep": "separator",
        "note": "footnote",
        "ti-section-1": "container-heading-ordinate",
        "ti-section-2": "container-heading-title",
        "ti-art": "leaf-heading-ordinate",
        "sti-art": "leaf-heading-title",
        "ti-grseq-1": "leaf-heading-title",
        "doc-ti": "long-title",
    }

    def transform(self):
        super().transform()
        self._relocate_footnotes()

    def locate_title(self):
        # cdm = CoverDataManager(self.language)
        # long_title = ' '.join(
        #     textify(par, with_tail=False, simplify_blanks=True)
        #     for par in self.source.xpath('/html/body/p[@class="long-title"]')[:3]
        # ).replace('  ', ' ')
        # cdm.set('long_title', long_title)
        # return cdm.md
        pass

    def _remove_crappy_contents_table(self, body, class_freq):
        if "ti-tbl" in class_freq:  # 3
            toc_head = body.find('.//p[@class="ti-tbl"]')
            toc_parent = toc_head.getparent()
            if textify(toc_head) in TOC_HEADS[self.language]:
                for sibling in toc_head.xpath("following-sibling::*"):
                    if sibling.tag != "table":
                        break
                    toc_parent.remove(sibling)
                toc_parent.remove(toc_head)

    def _relocate_footnotes(self):
        body = self.source.find("body")
        for footnote in body.xpath('.//p[@class="footnote" and a]'):
            first_anchor = footnote.xpath(".//a[@href]")[0]
            footnote_mark = body.find(
                './/a[@id="' + first_anchor.attrib.get("href")[1:] + '"]'
            )
            if footnote_mark is None:
                self.logger.warning(
                    "Reference "
                    + first_anchor.attrib.get("href")
                    + " within footnote does not point anywhere."
                )
                continue
            xtml.unfold(first_anchor)
            footnote.attrib["id"] = "footnote:" + re.sub(
                r"\s|\(|\)", "", textify(footnote_mark, with_tail=False)
            )
            footnote_mark.attrib["href"] = "#" + footnote.attrib.get("id")
            footnote_home = self.articles[
                footnote_mark.xpath("ancestor::article/@id")[0]
            ]
            footnote_home.footer.append(footnote)

    def _heading_ordinate_eligibility(self, element):
        return element.attrib.get("class", "").endswith("ordinate")

    def _heading_title_eligibility(self, element, doc_type):
        if doc_type == "container":
            return element.attrib.get("class") == "container-heading-title"
        return element.tag == "p" and element.attrib.get("class") not in [
            None,
            "normal",
        ]

    def _document_pre_processing(self):
        # standardize classes for headers
        for element in self.source.xpath(".//*[@class]"):
            xtml.migrate_attributes(element, "class", self.classes_old_to_new)
        super()._document_pre_processing()


class _OldFashionedOriginalAct(_Document):

    doc_type = DocumentType.OLD_ORIG
    itemization_type = "flat"

    def _heading_ordinate_eligibility(self, element):
        return len(element) <= 2

    def _remove_crappy_contents_table(self, body: et.ElementBase, class_freq):
        toc_head_texts = set(TOC_HEADS[self.language])
        texts = set(t.strip() for t in body.xpath(".//p/text()"))
        if len(toc_head_texts & texts) > 0:
            toc_head = [
                e for e in body.xpath(".//p") if e.text.strip() in toc_head_texts
            ][0]
            neigbour = toc_head.getnext()
            if neigbour.text == ">TABLE>":
                neigbour.getparent().remove(neigbour)
                toc_head.getparent().remove(toc_head)
                return
            elif neigbour.text == "Page":  # TODO: internationalize
                removables = [neigbour]
                toc_node_pattern = re.compile(r" \. [0-9]+$")
                for node_candidate in neigbour.itersiblings("p"):
                    if toc_node_pattern.search(node_candidate.text):
                        removables.append(node_candidate)
                    else:
                        parent = neigbour.getparent()
                        for removable in removables:
                            parent.remove(removable)
                        return
            raise NotImplementedError(
                "Table of contents removal for old-style documents "
                "not yet implemented"
            )

    item_label_p = re.compile(r"\([0-9a-z]{1,2}\)", flags=re.I)

    def _heading_title_eligibility(self, element, doc_type):
        """A simple, rule-based expert-feeling inspired model
        to recognize title phrases
        """
        text = textify(element, with_tail=False, simplify_blanks=True)
        lengths = len(text.split())
        if lengths == 0:
            return 0
        score = 1 / float(lengths)
        if text[0] == chr(9660) and len(text) <= 3:
            return 0
        if self.item_label_p.match(text) is not None:
            return 0
        if text.endswith(".") or text.endswith(":") or "," in text or ";" in text:
            return 0
        if text.isupper():
            return 4 * score
        if "." in text:
            for part in text.split(".")[1:]:
                if part.strip()[0].isupper():  # Contains phrases
                    return 0
        return score

    def locate_title(self):
        # cdm = CoverDataManager(self.language)
        # for element in self.source.xpath('/html/head/meta[@name and @content]'):
        #     key = element.attrib['name'].split('.')[1]
        #     content = element.attrib['content']
        #     if key in ['title', 'identifier', 'type']:
        #         continue
        #     if key == 'description':
        #         cdm.set('long_title', content)
        #     elif key == 'identifier':
        #         cdm.set('source_url', content)
        #     else:
        #         cdm.set(key, content)
        # return cdm.md
        pass

    def _document_pre_processing(self):
        super()._document_pre_processing()
        for paragraph in self.source.xpath("//p[.//p]") + self.source.xpath(
            '//div[@id="TexteOnly"]'
        ):
            xtml.unfold(paragraph)
        for txt_te in self.source.xpath("//txt_te"):
            xtml.unfold(txt_te)
        for h1 in self.source.xpath("//h1"):
            xtml.unfold(h1)  # contains just the celex number
            break


class _OldFashionedConsolidatedAct(_OldFashionedOriginalAct):
    def _document_pre_processing(self):
        for p in self.source.xpath("//p[@style]"):
            p.attrib.pop("style")
        super()._document_pre_processing()


class _ModernConsolidatedAct(_ModernOriginalAct):

    doc_type = DocumentType.NEW_CONS
    itemization_type = "flat"
    classes_old_to_new = {
        "norm": "normal",
        "subscript": "sub",
        "borderOj": "table",
        "title-annex-1": "leaf-heading-ordinate",
        "title-annex-2": "leaf-heading-title",
        "superscript": "super",
        "separator-short": "separator",
        "title-division-1": "container-heading-ordinate",
        "title-division-2": "container-heading-title",
        "title-article-norm": "leaf-heading-ordinate",
        "stitle-article-norm": "leaf-heading-title",
        "title-doc-first": "long-title",
    }

    def _extract_changers(self):
        for modifier_head in self.source.xpath('.//p[@class="hd-modifiers"]'):
            modifiers_table = modifier_head.getnext()
            xtml.remove(modifier_head)
            for href in modifiers_table.xpath(".//@href"):
                try:
                    clx = href_2_celex(href)
                except KeyError:
                    continue
                url = url_from_celex(self.language, clx)
                self.meta_data.version_implements.add(url)
            xtml.remove(modifiers_table)

    def _document_pre_processing(self):
        for ht in self.source.xpath('//span[@class="norm"] | //span[@class="italics"]'):
            if LATINS_RE.match(ht.text):
                xtml.unfold(ht)
        paragraph = self.source.find('.//p[@class="disclaimer"]')
        if paragraph is not None:
            paragraph.getparent().remove(paragraph)
        for anchor in self.source.xpath('//a[span[@class="superscript"]]'):
            # Standardize footnote
            assert len(anchor) == 1
            xtml.unfold(anchor.find("span"))
            lead = xtml.get_lead(anchor)
            if lead.strip().endswith("("):
                xtml.set_lead(anchor, lead.strip()[:-1])
                if anchor.tail is not None:
                    anchor.tail = anchor.tail.replace(")", "", 1)
                anchor.text = "({})".format(anchor.text.strip())
            anchor.attrib["class"] = "footnote"
        for anchor in self.source.xpath('.//span[a[span[@class="boldface"]]]'):
            # standardize insertion/change markers
            if len(anchor) != 1:
                self.logger.warning(
                    "Could not standardise element\n{}".format(
                        et.tostring(anchor, encoding=str, method="html")
                    )
                )
                continue
            xtml.unfold(anchor.find("a"))
            xtml.unfold(anchor.find("span"))
            anchor.tag = "a"
            if anchor.text.strip()[0] == chr(9658):
                anchor.text = anchor.text.strip()
                anchor.attrib["class"] = "marker-start"
        for paragraph in self.source.xpath(
            './/p[@class="title-annex-1"][span[@class="italics"]]'
        ):
            xtml.unfold(paragraph.find('span[@class="italics"]'))
        for span in self.source.xpath('.//span[@class="boldface"]'):
            text = span.text.strip()
            if text:
                if text[0] == chr(9668):
                    span.text = chr(9668)
                    span.attrib["class"] = "marker-end"
        for paragraph in self.source.xpath('.//p[@class="modref"]'):
            anchor = paragraph.find("a")
            if anchor is not None:
                anchor.attrib["class"] = "marker-start"
                xtml.unfold(paragraph)
        for paragraph in self.source.xpath('.//p[@class="arrow"]'):
            paragraph.getparent().remove(paragraph)
        for div in self.source.xpath('.//div[@style or @class="centered"]'):
            xtml.unfold(div)
        for span in self.source.xpath(".//span[@style]"):
            if span.text.strip() == "":
                xtml.unfold(span)
        for paragraph in self.source.xpath('.//p[@class="container-center"]'):
            xtml.unfold(paragraph)
        for paragraph in self.source.xpath(".//p[br]"):
            # remove elements of type <p>\n<br></p>
            if len(paragraph) == 1:
                if (paragraph.text or "").strip() == "":
                    if (paragraph.find("br").tail or "").strip() == "":
                        paragraph.getparent().remove(paragraph)
        super()._document_pre_processing()
        self._extract_changers()
        preamble_div = self.source.find('./body/div[@class="preamble"]')
        if preamble_div is not None:
            for sibling in preamble_div.itersiblings(preceding=True):
                if sibling.attrib.get("class") == "reference":
                    continue
                xtml.remove(sibling)
            xtml.unfold(preamble_div)
        crappy_toc = self.source.find('.//table/tr/td/p[@class="title-toc"]')
        if crappy_toc is not None:
            xtml.remove(crappy_toc.getparent().getparent().getparent())


class _ActProposal(_ModernOriginalAct):

    doc_type = DocumentType.NEW_CONS
    itemization_type = "flat"

    def _document_pre_processing(self):
        for p in self.source.xpath(".//p[@class]"):
            if not p.attrib["class"].startswith("li ManualNumPar"):
                continue
            p.attrib["class"] = p.attrib["class"].replace("li ManualNumPar", "li Point")
        for comment in self.source.xpath("//comment()"):
            xtml.remove(comment)
        xtml.flatten_by_paths(
            self.source,
            './/div[@class="contentWrapper"]',
            './/div[@class="content"]',
            ".//span[count(@*)=0]",
        )
        for element in self.source.xpath('.//p[@class="SectionTitle"]'):
            if element.attrib["class"] != "SectionTitle":
                continue
            element.attrib["class"] = "container-heading-ordinate"
            neighbour = element.getnext()
            if neighbour.attrib["class"] == "SectionTitle":
                neighbour.attrib["class"] = "container-heading-title"
        for element in self.source.xpath(
            './/p[@class="Titrearticle"] | .//p[@class="Annexetitre"]'
        ):
            element.attrib["class"] = "leaf-heading-ordinate"
            title = element.find("./br")
            if title is not None:
                title.tag = "p"
                title.attrib["class"] = "leaf-heading-title"
                title.text, title.tail = title.tail.strip(), ""
                for sibling in title.itersiblings():
                    title.append(sibling)
                    if sibling.tag == "br":
                        sibling.tail = " " + sibling.tail
                        xtml.unfold(sibling)
                element.addnext(title)
        for footnote in self.source.xpath('//span[@class="FootnoteReference"]'):
            anchor = footnote.find('./a[@class="footnoteRef"]')
            if anchor is None:
                continue
            footnote.tag = "a"
            anchor.tag = "sup"
            footnote.attrib["href"] = anchor.attrib.pop("href")
            footnote.attrib["id"] = anchor.attrib.pop("id")
            anchor.attrib.pop("class")
            footnote.attrib.pop("class")
        footnotes = self.source.find('.//dl[@id="footnotes"]')
        if footnotes is not None:
            footnotes.tag = "div"
            for dd in footnotes.xpath("./dd"):
                dd.tag = "p"
                dd.attrib["class"] = "footnote"
                span = dd.find('./span[@class="num"]')
                if span is not None:
                    span.attrib.pop("class")
                    a = span.find("./a")
                    span.tag = "a"
                    a.tag = "sup"
                    span.attrib["href"] = a.attrib.pop("href")
        super()._document_pre_processing()

    def _heading_title_eligibility(self, element, doc_type):
        return element.attrib.get("class", "").endswith("-heading-title")

    def standardize_items(self):
        pass  # implement the items-nesting here. Should work in this case.
