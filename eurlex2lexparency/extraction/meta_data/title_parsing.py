import re
import dateparser
from functools import lru_cache

from lexref import Reflector

title_suffix = ["Text with EEA relevance", "Text von Bedeutung für den EWR"]


def post_fix_title_essence(essence: str):
    essence = re.sub(" ?zur ?$", "", essence, flags=re.I)
    if essence.strip() == "":
        return
    return essence


def post_fix_title(title: str) -> str:
    title = title.replace("</p>,", ",</p>")
    title = title.replace(" zur</p> ", "</p> zur ")
    title = title.replace(r'<p class="lxp-title_essence">Zur</p>', "zur")
    title = title.replace(
        r' <p class="lxp-title_essence">)', r') <p class="lxp-title_essence">'
    )
    title = title.replace("( ", " (")
    title = title.replace(
        r'<p class="lxp-title_essence"> )', r') <p class="lxp-title_essence">'
    )
    title = title.replace(" sowie zur</p> ", "</p> sowie zur ")
    for suffix in title_suffix:
        for initial in (f" ({suffix})</p>", f" {suffix}</p>", f" ({suffix}. )</p>"):
            title = title.replace(initial, f"</p> ({suffix})")
        title = title.replace(f" {suffix}", f" ({suffix})")
    return title


def title_upmarker(long_title: str, essence: str):
    if essence is None:
        return long_title
    l_long_title = long_title.lower()
    l_essence = essence.lower().strip()
    if l_essence not in l_long_title or '<p class="lxp-title_essence">' in l_long_title:
        return long_title
    start = l_long_title.find(l_essence)
    end = start + len(l_essence)
    return post_fix_title(
        long_title[:start]
        + '<p class="lxp-title_essence">'
        + essence
        + "</p>"
        + long_title[end:]
    )


def beautify_id_human(id_human):
    if id_human.replace(" ", "").isalpha():
        return id_human
    axis, value = id_human.split(" ", 1)
    axis = axis.capitalize()
    return "{} {}".format(axis, value)


def align_decision_ref(id_human, title):
    """In German, decisions are either referred to as 'Beschluss' or
    'Entscheidung'. This function shall align the term used in the
    title with the term used in id_human.
    """
    if "Beschluss" in title:
        return id_human
    return id_human.replace("Beschluss ", "Entscheidung ")


class TitleParser:
    def __init__(self, language):
        self.language = language
        self.reflector = Reflector(
            self.language, "annotate", only_treaty_names=True, internet_domain=""
        )
        self.title_part_pattern = TitleParts(self.language)

    @classmethod
    @lru_cache()
    def get(cls, language):
        return cls(language)

    def get_refs(self, text):
        return self.reflector(text)[0]["references"]

    def get_ids(self, text):
        return [
            r["href"].replace("/eu/", "").strip("/")
            for r in self.get_refs(text)
            if not r["href"].startswith("#")
        ]

    def __call__(self, long_title):
        result = {}
        long_title = re.sub(r"\s", " ", long_title)
        m_date = self.title_part_pattern.long_date.search(long_title)
        if m_date is not None:
            result["date_document"] = dateparser.parse(
                m_date.group(), languages=[self.language.lower()]
            ).date()
            title_start = m_date.end() + 1
        else:
            title_start = 0
        ma = self.title_part_pattern.amending.search(long_title)
        mr = self.title_part_pattern.repealing.search(long_title)
        title_annex_start = min(
            len(long_title) if ma is None else ma.start(),
            len(long_title) if mr is None else mr.start(),
        )
        title = long_title[title_start:title_annex_start].strip(" \n,;:.")
        if title:
            result["title_essence"] = post_fix_title_essence(
                title[0].upper() + title[1:]
            )
        # Determine human readable document ID
        try:
            id_human = self.get_refs(long_title[:title_annex_start])[0]["title"]
        except IndexError:
            pass
        else:
            result["id_human"] = align_decision_ref(
                beautify_id_human(id_human), long_title
            )

        match_count = (ma is not None) + (mr is not None)
        a, r = [], []
        if match_count == 2:
            if ma.start() < mr.start():
                a = self.get_ids(long_title[ma.start() : mr.start()])
                r = self.get_ids(long_title[mr.start() :])
            else:
                r = self.get_ids(long_title[mr.start() : ma.start()])
                a = self.get_ids(long_title[ma.start() :])
        elif ma is not None:
            a = self.get_ids(long_title[ma.start() :])
        elif mr is not None:
            r = self.get_ids(long_title[mr.start() :])
        self.clean_up(a)
        result["amends"] = a
        self.clean_up(r)
        result["repeals"] = r
        return result

    @staticmethod
    def clean_up(references):
        """
        Since the document titles are often extremely decorated with
         all types of adjectives, such as
            - Commision Regulation ...
            - Implementing Council Regulation ...
        and many more, the reference location scheme is unable to identify
            - "Annex I to Council Regulation 0815"
        as a single neighbourhood of reference tokens. Therefore, since
        reference identification for the metadata is crucial, this
        function cleans up the first result of the found references.
        """
        pops = []
        for k, reference in enumerate(references):
            try:
                axis, ordinate = reference.split("_", 1)
            except ValueError:
                continue
            if axis in ("PND", "DID"):
                references[k] = ordinate
            elif axis in ("PRE", "ART", "ANX"):
                pops.append(reference)
        for pop in reversed(pops):
            references.remove(pop)


class TitleParts:
    def __init__(self, language):
        self._language = language
        if self._language == "EN":
            months = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            self.repealing = re.compile("(,| and )?repealing ", flags=re.I)
            self.amending = re.compile("(,| and )?amending ", flags=re.I)
            self.title_amendment = re.compile(
                "(,| and )?(repealing|amending) ", flags=re.I
            )
            self.long_date = re.compile(
                r"[0-9]{{1,2}}\.?\s({0})\s[0-9]{{4}}".format("|".join(months)),
                flags=re.I,
            )
        elif self._language == "ES":
            months = [
                "enero",
                "febrero",
                "marzo",
                "abril",
                "mayo",
                "junio",
                "julio",
                "agosto",
                "septiembre",
                "octubre",
                "noviembre",
                "diciembre",
            ]
            self.repealing = re.compile(
                "((y )?por (el|la) que se |que |y se )?deroga", flags=re.I
            )
            self.amending = re.compile(
                "((y )?por (el|la) que se |que |y se )?modifican?", flags=re.I
            )
            self.title_amendment = re.compile(
                "((y )?por (el|la) que se |que )?(modifica|deroga)", flags=re.I
            )
            self.long_date = re.compile(
                r"[0-9]{{1,2}}\sde\s({0})\sde\s[0-9]{{4}}".format("|".join(months)),
                flags=re.I,
            )
        elif self._language == "DE":
            months = [
                "Januar",
                "Februar",
                "März",
                "April",
                "Mai",
                "Juni",
                "Juli",
                "August",
                "September",
                "Oktober",
                "November",
                "Dezember",
            ]
            self.repealing = re.compile("((und)? zur )?Aufhebung", flags=re.I)
            self.amending = re.compile("((und)? zur )?(Abä|Ä)nderung", flags=re.I)
            self.title_amendment = re.compile(
                "((und)? zur )?((Abä|Ä)nderung|Aufhebung)", flags=re.I
            )
            self.long_date = re.compile(
                r"[0-9]{{1,2}}\.\s({0})\s(19|20)[0-9]{{2}}".format("|".join(months)),
                flags=re.I,
            )
        else:
            raise NotImplementedError(
                "It seems that the time has come "
                "to implement language {}".format(self._language)
            )
