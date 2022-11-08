"""
Some Directives seem to not to fit into the celex system:
 - VAT Directive (https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=LEGISSUM%3Al31057)
 - Blue Guide (https://ec.europa.eu/DocsRoom/documents/18027)
"""
import os
from collections import OrderedDict, defaultdict
from numpy import isnan
from singletonmetaclasss.singleton import Singleton
import pandas as pd
import lexref

from eurlex2lexparency.utils.generics import TwoWay


def coalesce(value):
    if type(value) is str:
        return value
    if value is None:
        return
    if isnan(value):
        return


class TreatyAcronyms(metaclass=Singleton):
    PATH = os.path.join(os.path.dirname(__file__), "static", "treaties.csv")

    def __init__(self):
        self.df = pd.read_csv(self.PATH).set_index(
            ["treaty", "language"], verify_integrity=True
        )

    @classmethod
    def get(cls, treaty: str, language: str) -> str:
        self = cls()
        return self.df.loc[(treaty, language)].abbrev


class PopularTitles(metaclass=Singleton):
    PATH_1 = os.path.join(
        os.path.dirname(lexref.__file__), "static", "named_entity.csv"
    )
    PATH_2 = os.path.join(os.path.dirname(__file__), "static", "short_titles.csv")

    def __init__(self):
        df = pd.concat(
            [
                pd.read_csv(self.PATH_2),
                pd.read_csv(self.PATH_1).rename(
                    columns={
                        "tag": "id_local",
                        "abbreviation": "pop_acronym",
                        "title": "pop_title",
                    }
                ),
            ]
        )
        self.st = defaultdict(OrderedDict)
        for _, row in df.iterrows():
            if row["id_local"] in self.st[row["language"]]:
                raise AssertionError(row["id_local"] + " duplicated!")
            self.st[row["language"]][row["id_local"]] = (
                coalesce(row["pop_title"]),
                coalesce(row["pop_acronym"]),
            )

    def get_short_title(self, id_, language, fallback_language="EN"):
        if fallback_language is None:
            return self.st[language].get(id_)
        return self.st[language].get(id_, self.st[fallback_language].get(id_))

    def get_acronym_celex(self, language):
        return TwoWay(
            ("acronym", "celex"),
            [
                (a.replace(" ", "-"), c)
                for c, (t, a) in self.st[language].items()
                if a is not None
            ],
        )


if __name__ == "__main__":
    pt = PopularTitles()
    celexes = set(pt.st["EN"]) | set(pt.st["DE"])
    result = {}
    for clx in celexes:
        result[clx] = pt.get_short_title(clx, "DE")
    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
