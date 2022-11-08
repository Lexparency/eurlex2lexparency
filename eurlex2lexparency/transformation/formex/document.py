from copy import deepcopy

from lxml import etree as et
from typing import Dict
from collections import Counter
import re

from eurlex2lexparency.extraction.meta_data.handler import url_from_celex
from eurlex2lexparency.transformation.generic.definitions import TechnicalTerms

from ..utils import TransformingRepealerError
from eurlex2lexparency.utils import xtml
from ..utils.generics import LATINS_RE
from ..generic.document import DocumentTransformer
from .toc import EmbeddedContentsNode
from .article import Article

multi_blanks = re.compile(r"\s+")


class FormexTransformer(DocumentTransformer):
    def _raise_if_repealer(self):
        for info in self.source.xpath("/LEXP.COMBINED/CONS.ACT/INFO.CONSLEG"):
            if info.attrib["END"] == "REPEALED":
                raise TransformingRepealerError

    def transform(self):
        self._raise_if_repealer()
        self._document_preprocessing()
        title = self.locate_title()
        self.skeletorize()
        self.articles = self._split()
        # List of et-elements that form the leaves
        xtml.push(self.articles["PRE"].source, title)
        self._document_postprocessing()
        self.definitions = self.reference_definitions()
        self._warn_on_unhandled()
        self.link()
        self.embed()
        self.export()

    def _document_postprocessing(self):
        self._ht_elements()
        self.source.remove(self.source.find("./BIB.INSTANCE"))
        self._remove_heading_styling()
        xtml.unfold_all(self.source, ("TITLE", "TI", "DATE", "TXT"))

    def _renumber_generic_leaves(self):
        i = 1
        for e in self.source.xpath("//*[@id]"):
            e_id = e.attrib["id"]
            try:
                pre, post = e_id.split("_", 1)
            except ValueError:
                continue
            if pre != "L":
                continue
            try:
                int(post)
            except ValueError:
                continue
            e.attrib["id"] = f"L_{i}"
            i += 1

    def _remove_heading_styling(self):
        for heading_part in self.source.xpath(
            './/*[@class="lxp-ordinate"] | .//*[@class="lxp-title"]'
        ):
            while len(heading_part) == 1:
                if heading_part[0].tag in ("b", "i"):
                    xtml.unfold(heading_part[0])
                else:
                    break
            if len(heading_part) == 0:
                heading_part.text = heading_part.text.strip()

    def export(self):
        """Returns the html-version"""
        self.source.tag = "body"
        self.source.attrib.pop("id")
        sauce = """<!DOCTYPE html>
            <html lang="{lang}">
                <head>
                    <meta charset="UTF-8">
                    <title>Transformed document</title>
                </head>
                {body}
            </html>""".format(
            body=et.tostring(self.source, encoding="unicode", method="html"),
            lang=self.language.lower(),
        )
        sauce = multi_blanks.sub(" ", sauce)
        self.source = et.fromstring(sauce, parser=et.HTMLParser())

    def _ht_elements(self):
        for ht in self.source.xpath(".//HT"):
            type_ = ht.attrib["TYPE"]
            if type_ in ("SUP", "SUB"):
                ht.tag = ht.attrib.pop("TYPE").lower()
            if type_ in ("ITALIC", "BOLD"):
                ht.tag = type_[0].lower()
                ht.attrib.pop("TYPE")
            if type_ in ("NORMAL", "EXPANDED"):
                xtml.unfold(ht)
            if type_ == "UC":
                ht.text = ht.text.upper()
                xtml.unfold(ht)

    @staticmethod
    def _exec_deletion(o: et.PIBase, c: et.PIBase):
        assert len(o.xpath("ancestor::*")) <= len(c.xpath("ancestor::*"))
        while o.getparent() is not c.getparent():
            o.tail = None
            xtml.push(o.getnext(), o)
        o.tail = None
        for sibling in o.itersiblings():
            if sibling is c:
                break
            xtml.remove(sibling, keep_tail=False)

    def _handle_processing_instructions(self):
        pis = self.source.xpath("//processing-instruction()")
        id_2_pi = {pi.attrib["ID"]: pi for pi in pis if "ID" in pi.attrib}
        for pi in pis:
            if pi.attrib.get("ACTION") == "DELETED":
                self._exec_deletion(pi, id_2_pi[pi.attrib["IDREF"]])
            if pi.getparent() is None:
                continue  # e.g. for 32006R0166
            xtml.unfold(pi, processing_instruction=True)

    def _foonote_preprocessing(self):
        # inspired by https://lexparency.de/eu/32005R0111/ANX/
        for group in self.source.xpath("//GR.NOTES"):
            for note in group.xpath("./NOTE"):
                n_id = note.attrib["NOTE.ID"]
                for referrer in self.source.xpath(f'//NOTE[@NOTE.REF="{n_id}"]'):
                    referrer.append(deepcopy(note))
                    xtml.unfold(referrer)
            xtml.remove(group)

    def _extract_changers(self):
        for fc in self.source.xpath("//FAM.COMP"):
            for clx in fc.xpath(".//BIB.DATA/NO.CELEX/text()"):
                url = url_from_celex(self.language, clx)
                self.meta_data.version_implements.add(url)
            xtml.remove(fc)

    def _document_preprocessing(self):
        for ht in self.source.xpath('//HT[@TYPE="NORMAL"] | //HT[@TYPE="ITALIC"]'):
            if list(ht.iterancestors("FORMULA.S")) or list(ht.iterancestors("FORMULA")):
                continue
            if ht.text is None:
                continue
            if LATINS_RE.match(ht.text):
                xtml.unfold(ht)
        for img in self.source.xpath("//INCL.ELEMENT[@FILEREF]"):
            img.tag = "img"
            img.attrib["src"] = img.attrib.pop("FILEREF")
            for key in img.attrib:
                if key.isupper():
                    img.attrib.pop(key)
        self._handle_processing_instructions()
        for element in self.source.xpath("//GR.SEQ[LOC.NOTES[REF.NOTE]]"):
            assert et.tostring(element, method="text").strip() == b""
            xtml.remove(element)
        if self.source[0].tag == "CONS.ACT":
            self.source[0].tag = "ACT"
            for sub_annex in self.source.xpath(  # e.g. in CELEX:32006R1907
                "/LEXP.COMBINED/ACT/CONS.DOC/CONS.ANNEX/CONS.ANNEX"
            ):
                sub_annex.tag = "SUBDIV"
            annexes = self.source.xpath("/LEXP.COMBINED/ACT/CONS.DOC/CONS.ANNEX")
            if annexes:
                if len(annexes) > 1:
                    annexes_container = et.SubElement(self.source, "ANNEXES")
                else:
                    annexes_container = self.source
                for annex in annexes:
                    annex.tag = "ANNEX"
                    annexes_container.append(annex)
            xtml.unfold(self.source.find("./ACT/CONS.DOC"))
            for mesa_annex in self.source.xpath(".//QUOT.S//CONS.ANNEX"):
                mesa_annex.tag = "ANNEX"
            for cons_annex in self.source.xpath("//ANNEX/CONTENTS/CONS.ANNEX"):
                cons_annex.tag = "DIVISION"
            conses = set(
                e.tag
                for e in self.source.iterdescendants()
                if isinstance(e.tag, str) and e.tag.startswith("CONS.")
            )
            if conses:
                raise RuntimeError(
                    "Need further preprocessing. "
                    "Found CONS.* tags:\n{}".format(str(conses))
                )
        self._formex_references()
        for toc in self.source.xpath("//TOC"):
            # TODO: some acts (e.g. 32006R1907) have several tocs!
            #  handle them better
            xtml.remove(toc)
        self._extract_changers()
        for info in self.source.xpath(
            " | ".join(
                ("/LEXP.COMBINED/ACT/INFO.CONSLEG", "/LEXP.COMBINED/ACT/INFO.PROD")
            )
        ):
            xtml.remove(info)
        self._foonote_preprocessing()

    def _formex_references(self):
        for reference in self.source.xpath(".//REF.DOC.OJ"):
            reference.attrib.pop("PAGE.FIRST", None)
            reference.tag = "a"
            href = (
                "https://eur-lex.europa.eu/legal-content/"
                "{lang}/AUTO/?uri=OJ:{coll}:{year}:{issue}:TOC".format(
                    lang=self.language,
                    coll=reference.attrib.pop("COLL"),
                    year=reference.attrib.pop("DATE.PUB")[:4],
                    issue=reference.attrib.pop("NO.OJ"),
                )
            )
            reference.attrib["href"] = href

    def _warn_on_unhandled(self):
        c = Counter(
            e.tag
            for article in self.articles.values()
            for e in article.e.xpath(".//*")
            if e.tag.isupper()
        )
        if len(c):
            self.logger.warning(
                "Forgot to handle {}".format(
                    ", ".join(
                        "{}: {}".format(tag, count)
                        for tag, count in reversed(c.most_common())
                    )
                )
            )
        xtml.unfold_all(self.source, c.keys())

    def skeletorize(self):
        EmbeddedContentsNode(self.source, self.language)
        for search_path in ["/LEXP.COMBINED/ACT/ENACTING.TERMS", "/LEXP.COMBINED/ACT"]:
            for complex_element in self.source.xpath(search_path):
                xtml.unfold(complex_element)
        self._renumber_generic_leaves()

    def _split(self) -> Dict[str, Article]:
        return {
            leaf.attrib["id"]: Article(
                leaf, language=self.language, logger=self.logger, transform=True
            )
            for leaf in self.source.xpath(
                " | ".join(
                    "/LEXP.COMBINED{}/article".format("".join(["/div"] * k))
                    for k in range(0, 10)
                    # Currently deepest found chapter nesting: 6
                )
            )
        }

    def locate_title(self):
        title = self.source.find("./ACT/TITLE")
        ti = title.find("./TI")
        if ti is not None:
            xtml.unfold(ti)
        for paragraph in title.iterdescendants("P"):
            # Paragraphs are glued together, so words would be concatenated
            paragraph.tag = "p"
            paragraph.tail = (paragraph.tail or "") + "\n"
        title.tag = "div"
        title.attrib["class"] = "lxp-title"  # instead of property=eli:title
        return title

    def reference_definitions(self):
        """Find definitions"""
        terms = TechnicalTerms(self.language)
        for article in self.articles.values():
            article.reference_definitions(terms)

    def skeleton(self, fine=True):
        result = xtml.subskeleton(self.source)
        if fine:
            return result
        else:
            for leaf in result.xpath(
                "|".join(
                    (
                        '//*[@class="lxp-article"]',
                        '//*[@class="lxp-preamble"]',
                        '//*[@class="lxp-final"]',
                    )
                )
            ):
                heading = leaf[0]
                for sibling in heading.itersiblings():
                    xtml.remove(sibling)
        return result
