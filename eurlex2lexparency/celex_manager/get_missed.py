from datetime import date
from functools import lru_cache
from abc import ABCMeta, abstractmethod
from itertools import product

from eurlex2lexparency.celex_manager.legislation_getter import LegislationGetter
from eurlex2lexparency.celex_manager.model import (
    SessionManager,
    Version,
    Act,
    Corrigendum,
    Changes,
)
from eurlex2lexparency.celex_manager.celex import (
    CelexCompound,
    UnexpectedPatternException,
    CelexBase,
)


class MissedGetter(LegislationGetter, metaclass=ABCMeta):

    YEARS = list(map(str, range(1950, date.today().year + 2)))
    INTERS = list("RLDF")
    TYPE = None

    def __init__(self):
        super().__init__()
        self.sm = SessionManager()

    @abstractmethod
    def _local(self):
        pass

    @abstractmethod
    def _remote(self):
        pass

    @property
    @lru_cache()
    def local(self):
        return self._local()

    @property
    @lru_cache()
    def remote(self):
        return self._remote()

    @abstractmethod
    def _pull_all_missings(self, missings):
        pass

    @classmethod
    def get(cls):
        self = cls()
        missings = self.remote - self.local
        self.logger.info(f"Missed {len(missings)} {self.TYPE}.")
        self._pull_all_missings(missings)
        superfluous = self.local - self.remote
        if superfluous:
            self.logger.warning(
                "Superfluous: \n  " + "\n  ".join(map(str, superfluous))
            )


class MissedVersionsGetter(MissedGetter):

    TYPE = "versions"

    def _local(self):
        result = set()
        with self.sm() as s:
            for v in s.query(Version):
                if v.date == date(1900, 1, 1):
                    continue
                try:
                    result.add(v.compound_celex)
                except UnexpectedPatternException:
                    pass
        return result

    def _remote(self):
        result = set()
        for year in self.YEARS:
            for c in self("missed_consolidates", year=year):
                result.add(CelexCompound.from_string(c[0].toPython()))
        return result

    def _pull_all_missings(self, missings):
        for missed in missings:
            self.logger.info(f"Pulling for {missed}.")
            self.pull_compound_celex_representations(missed)


class MissedActsGetter(MissedGetter):

    TYPE = "acts"

    def _local(self):
        result = set()
        with self.sm() as s:
            for a in s.query(Act):
                try:
                    result.add(CelexBase.from_string(a.celex))
                except UnexpectedPatternException:
                    pass
        return result

    def _remote(self):
        result = set()
        for year, inter in product(self.YEARS, self.INTERS):
            for (c,) in self("celexes_inter_year", year=year, inter=inter):
                result.add(CelexBase.from_string(c.toPython()))
        return result

    def _pull_all_missings(self, missings):
        for c in missings:
            self.pull_acts_representations(str(c))


class MissedCorrigendaGetter(MissedGetter):

    TYPE = "corrigendum"

    def _local(self):
        result = set()
        with self.sm() as s:
            for a in s.query(Corrigendum):
                try:
                    result.add(a.compound_celex)
                except UnexpectedPatternException:
                    pass
        return result

    def _remote(self):
        result = set()
        for year, inter in product(self.YEARS, self.INTERS):
            self.logger.info(f"Querying Corrigenda for ({year}, {inter})")
            for (c,) in self("corrigenda", year=year, inter=inter):
                result.add(CelexCompound.from_string(c.toPython()))
        return result

    def _pull_all_missings(self, missings):
        base_celexes = {c.base for c in missings}
        for celex in base_celexes:
            self.pull_all_corrigenda_representations(celex)


class MissedChangesGetter(MissedGetter):

    change_2_cdm = [
        ("amends", "resource_legal_amends_resource_legal"),
        ("completes", "resource_legal_completes_resource_legal"),
        ("repeals", "resource_legal_implicitly_repeals_resource_legal"),
        ("repeals", "resource_legal_repeals_resource_legal"),
    ]

    def _local(self):
        result = set()
        with self.sm() as s:
            for r in s.query(Changes):
                try:
                    result.add(
                        (
                            CelexBase.from_string(r.celex_changer),
                            r.change,
                            CelexBase.from_string(r.celex_changee),
                        )
                    )
                except UnexpectedPatternException:
                    pass
        return result

    def _remote(self):
        result = set()
        for year, (change, cdm) in product(self.YEARS, self.change_2_cdm):
            for changer, changee in self("changes_year", year=year, change=cdm):
                try:
                    result.add(
                        (
                            CelexBase.from_string(str(changer)),
                            change,
                            CelexBase.from_string(str(changee)),
                        )
                    )
                except UnexpectedPatternException:
                    pass
        return result

    def _pull_all_missings(self, missings):
        with self.sm() as s:
            celexes = set(a.celex for a in s.query(Act))
            for changer, change, changee in missings:
                if changer == changee:
                    continue
                celex_changer = str(changer)
                celex_changee = str(changee)
                for missing_celex in {celex_changer, celex_changee} - celexes:
                    celexes.add(missing_celex)
                    s.add(Act(celex=missing_celex))
                # noinspection PyArgumentList
                s.add(
                    Changes(
                        celex_changer=celex_changer,
                        change=change,
                        celex_changee=celex_changee,
                    )
                )


if __name__ == "__main__":
    MissedActsGetter.get()
    MissedVersionsGetter.get()
    MissedCorrigendaGetter.get()
    MissedChangesGetter.get()
