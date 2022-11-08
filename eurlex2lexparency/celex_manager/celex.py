from __future__ import annotations
import os
import re
from datetime import datetime, date
from enum import Enum
from itertools import product
from collections import namedtuple

from lexref.reflector import celex_2_id_human


class UnexpectedPatternException(Exception):
    pass


class Version(namedtuple("Version", ["consoli_date", "folder"])):
    @classmethod
    def create(cls, version):
        if type(version) == cls:
            return version
        if version == "initial" or version == date(1900, 1, 1):
            return cls(date(1900, 1, 1), "initial")
        elif type(version) is date:
            return cls(version, version.strftime("%Y%m%d"))
        elif type(version) is str:
            return cls(datetime.strptime(version, "%Y%m%d").date(), version)
        raise ValueError(f"Cannot instantiate Version from {version}.")

    @classmethod
    def able(cls, version):
        try:
            cls.create(version)
        except ValueError:
            return False
        return True


class CelexBase(
    namedtuple("CelexBase", ["pre", "year", "inter", "number", "extension"])
):

    pattern = re.compile(
        r"(?P<pre>[0-9])(?P<year>[0-9]{4})"
        r"(?P<inter>[A-Z]{1,2})(?P<number>[0-9]+)?"
        r"(?P<extension>\([0-9]+\))?"
    )

    @classmethod
    def from_string(cls, in_string: str) -> CelexBase:
        m = cls.pattern.match(in_string)
        if m is None:
            raise UnexpectedPatternException(
                'Celex candidate "{}" does not comply the celex pattern'.format(
                    in_string
                )
            )
        pre = int(m.group("pre"))
        year = int(m.group("year"))
        inter = m.group("inter")
        number = m.group("number")
        extension = m.group("extension")
        if number is not None:
            number = int(number)
        if extension is None:
            extension = ""
        self = cls(pre, year, inter, number, extension)
        if str(self) != str(in_string):
            raise UnexpectedPatternException(f"Could not correctly parse {in_string}")
        return self

    @property
    def path(self):
        return os.path.join(*self.map_str())

    def map_str(self):
        if self.number is None:
            return str(self.pre), str(self.year), self.inter, self.extension
        return (
            str(self.pre),
            str(self.year),
            self.inter,
            str(self.number).zfill(4),
            self.extension,
        )

    @staticmethod
    def wildcard_where(**where):
        result = "".join(
            [
                str(where[key]) if key in where else "*"
                for key in ("pre", "year", "inter", "number")
            ]
        )
        return re.sub(r"[*]+", "*", result)

    def __str__(self):
        return "".join(self.map_str())

    def human_id(self, language="EN") -> str:
        # noinspection PyBroadException
        try:
            return celex_2_id_human(str(self), language)
        except Exception:
            return "CELEX:" + str(self)


class AnnexType(Enum):
    none = 1
    corrigendum = 2
    consolidate = 3


class Annex(namedtuple("Annex", ["type", "value"])):
    """Holds type and value of a Celex's annex
    Examples:
        - for 32013R0575-20180205 the annex is of type "consolidate"
        - for  32013R0575R(02) the annex is of type "corrigendum"
    """

    corrigendum = re.compile(r"R\((?P<count>[0-9]+)\)")
    consolidate = re.compile("-(?P<date>[0-9]{8})")

    @classmethod
    def from_string(cls, in_string):
        if in_string == "":
            return cls(AnnexType.none, None)
        m = cls.corrigendum.match(in_string)
        if m is not None:
            return cls(AnnexType.corrigendum, int(m.group("count")))
        m = cls.consolidate.match(in_string)
        if m is not None:
            return cls(
                AnnexType.consolidate,
                datetime.strptime(m.group("date"), "%Y%m%d").date(),
            )
        raise UnexpectedPatternException(f"Could not parse annex {in_string}")

    def __str__(self):
        if self.type == AnnexType.none:
            return ""
        if self.type == AnnexType.corrigendum:
            return "R({})".format(str(self.value).zfill(2))
        if self.type == AnnexType.consolidate:
            return "-{}".format(self.value.strftime("%Y%m%d"))


empty_annex = Annex(AnnexType.none, None)


class CelexCompound(namedtuple("CelexCompound", ["base", "annex"])):

    pattern = re.compile(
        "^(?P<base>{})(?P<annex>{}|{}|)$".format(
            CelexBase.pattern.pattern,
            Annex.corrigendum.pattern,
            Annex.consolidate.pattern,
        )
    )

    @classmethod
    def from_string(cls, in_string):
        m = cls.pattern.match(in_string)
        if m is None:
            raise UnexpectedPatternException(
                '"{}" cannot be parsed (yet).'.format(in_string)
            )
        annex = Annex.from_string(m.group("annex"))
        base = m.group("base")
        if annex.type == AnnexType.consolidate:
            assert base[0] == "0"
            base = "3" + base[1:]
            # TODO: Clarify if only documents with first digit '3' can have
            #  consolidates. Otherwise, the data-model of the celex DB has to
            #  be revised (I think)
        return cls(CelexBase.from_string(base), annex)

    def __str__(self):
        if self.annex.type == AnnexType.consolidate:
            return "0" + str(self.base)[1:] + str(self.annex)
        return str(self.base) + str(self.annex)

    @property
    def compound(self):
        return self.annex.type != AnnexType.none

    @classmethod
    def get(cls, celex, annex_value=None) -> CelexCompound:
        if type(celex) is str:
            celex = CelexBase.from_string(celex)
        assert type(celex) is CelexBase
        if annex_value is None:
            annex = empty_annex
        elif type(annex_value) is date:
            annex = Annex(AnnexType.consolidate, annex_value)
        else:
            assert type(annex_value) is int
            annex = Annex(AnnexType.corrigendum, annex_value)
        return cls(celex, annex)

    def __hash__(self):
        return hash(str(self))

    @property
    def type(self):
        return self.annex.type


def expand(years, types, numbers):
    years = map(str, years)
    numbers = map(lambda n: str(n).zfill(4), numbers)
    return ["3{}{}{}".format(*tuple_) for tuple_ in product(years, types, numbers)]


if __name__ == "__main__":
    print(repr(CelexCompound.from_string("02016R0679-20160504")))
    print(repr(CelexCompound.from_string("32016R0679R(02)")))
    print(repr(CelexCompound.from_string("52021PC0212")))
