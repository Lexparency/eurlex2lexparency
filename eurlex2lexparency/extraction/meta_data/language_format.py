import os
from lxml import etree as et
from urllib.parse import urljoin
from collections import defaultdict
from datetime import date

from eurlex2lexparency.extraction import textify
from eurlex2lexparency.extraction.generic import FormatsNotLoaded, Formats
from eurlex2lexparency.celex_manager.model import SessionManager, Representation
from eurlex2lexparency.extraction.meta_data.eli_data import EurLexDocumentLandingPage
from eurlex2lexparency.utils.generics import SwingingFileLogger


class EurLexLanguagesAndFormats:
    """self.url is actually the celex id"""

    def __init__(self, local_path, celex, consoli_date=date(1900, 1, 1)):
        os.makedirs(local_path, exist_ok=True)
        self.logger = SwingingFileLogger.get("rdf", local_path)
        self.celex = celex
        self.consoli_date = consoli_date
        self.landing_page = EurLexDocumentLandingPage.construct_from(
            local_path, celex, consoli_date
        ).document
        self.sessionator = SessionManager()
        self.languages_to_formats = dict()
        try:
            self.load_local()
        except FormatsNotLoaded:
            self.retrieve_online()

    def load_local(self):
        with self.sessionator() as s:
            for row in s.query(Representation).filter(
                Representation.celex == self.celex,
                Representation.date == self.consoli_date,
            ):
                # the value "None" means unloaded, since at the persist-step
                # None-values are converted to empty strings.
                if row.url_html is None and len(self.languages_to_formats) == 0:
                    raise FormatsNotLoaded
                self.languages_to_formats[row.language] = Formats(
                    row.url_html or None, row.url_pdf or None
                )
        if len(self.languages_to_formats) == 0:
            raise FormatsNotLoaded("Nothing found.")

    def guessed_url(self, language, fmt):
        """Guesses url from the observed systematic by eur-lex
        :param language: DE, EN, ES, ...
        :param fmt: HTML or PDF
        :return: tue guessed URL for the sought-after document.
        """
        if self.consoli_date == date(1900, 1, 1):
            celex = self.celex
        else:
            celex = "".join(
                ("0", self.celex[1:], "-", self.consoli_date.strftime("%Y%m%d"))
            )
        return (
            f"https://eur-lex.europa.eu/"
            f"legal-content/{language}/TXT/{fmt}/?uri=CELEX:{celex}"
        )

    def guess(self):
        """Fallback method, if retrieve online fails."""
        with self.sessionator() as s:
            for row in s.query(Representation).filter(
                Representation.celex == self.celex,
                Representation.date == self.consoli_date,
            ):
                self.languages_to_formats[row.language] = Formats(
                    self.guessed_url(row.language, "HTML"),
                    self.guessed_url(row.language, "PDF"),
                )

    def retrieve_online(self):
        # noinspection PyBroadException
        try:
            self._retrieve_online()
        except Exception:
            self.logger.error("Could not load the format's URLs.", exc_info=True)
            self.guess()
        self.persist()

    def _retrieve_online(self):
        rows = [
            div
            for div in self.landing_page.xpath('//div[@id="PP2Contents"]')[0].xpath(
                ".//div[@class]"
            )
            # mimicking selector string "div.PubFormat", including possibility
            # that some divs have several classes:
            if "PubFormat" in div.attrib["class"].split()
        ]
        languages = [
            textify(el, with_tail=False, simplify_blanks=True)
            for el in rows[0].xpath(".//ul/li")
        ]
        languages_and_formats = defaultdict(list)
        languages_and_formats["languages"] = languages
        for row in rows[1:]:
            format_ = et.tostring(row[0], method="text", encoding="unicode").strip()
            for data in row[1].xpath("./ul/li"):
                if data.attrib.get("class") == "disabled":
                    languages_and_formats[format_].append(None)
                else:
                    url = data.xpath("./a/@href")[0]
                    languages_and_formats[format_].append(
                        urljoin(self.landing_page.url, url).replace("&from=EN", "")
                    )
        formats = [key for key in languages_and_formats.keys() if key != "languages"]
        deletables = []
        for k, language in enumerate(languages_and_formats["languages"]):
            for format_ in formats:
                if languages_and_formats[format_][k]:
                    break
            else:  # if no break occurs
                deletables.append(k)
        for index in reversed(deletables):
            for value in languages_and_formats.values():
                value.pop(index)
        for key in tuple(languages_and_formats.keys()):
            if key not in ("languages", "PDF", "HTML"):
                languages_and_formats.pop(key)
        for fmt in ("PDF", "HTML"):
            languages_and_formats[fmt] = (
                [None] * len(languages_and_formats["languages"])
                if languages_and_formats[fmt] == []
                else languages_and_formats[fmt]
            )
        for language, pdf, html in zip(
            languages_and_formats["languages"],
            languages_and_formats["PDF"],
            languages_and_formats["HTML"],
        ):
            self.languages_to_formats[language] = Formats(html, pdf)

    def persist(self):
        no_formats = Formats("", "")
        with self.sessionator() as s:
            for row in s.query(Representation).filter(
                Representation.celex == self.celex,
                Representation.date == self.consoli_date,
            ):
                # Empty string means that the information has been downloaded
                # but no URL available
                formats = self.languages_to_formats.get(row.language, no_formats)
                row.url_html = formats.html or ""
                row.url_pdf = formats.pdf or ""


if __name__ == "__main__":
    from settings import LEXPATH
    from eurlex2lexparency.celex_manager.celex import CelexBase

    c = CelexBase.from_string("32013R0575")
    ellaf = EurLexLanguagesAndFormats(
        os.path.join(LEXPATH, c.path), str(c), date(2013, 6, 28)
    )
