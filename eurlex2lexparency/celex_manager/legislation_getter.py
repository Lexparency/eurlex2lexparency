from eurlex2lexparency.utils import SparqlKraken
from eurlex2lexparency.celex_manager.celex import CelexCompound, UnexpectedPatternException, AnnexType, CelexBase
from datetime import date
from collections import namedtuple
from typing import List

from eurlex2lexparency.celex_manager.eurlex import country_mapping, PersistableHit, PreLegalContentXmlDataBase, query_templates
from eurlex2lexparency.utils import FullMonth


def lang_2(lang):
    return country_mapping.get(three=lang.rsplit('/', 1)[-1])


class CompoundHit(
      namedtuple('Hit', ['celex', 'work_date', 'languages']),
      PersistableHit):
    in_force = None
    publication_date = None


class ActHit(
      namedtuple('Hit', ['celex', 'in_force', 'publication_date', 'languages']),
      PersistableHit):
    work_date = None


class Hits(dict):

    def append(self, hit: PersistableHit):
        try:
            found = self[hit.celex]
        except KeyError:
            self[hit.celex] = hit
        else:
            found.languages.update(hit.languages)


class LegislationGetter(SparqlKraken):

    def __init__(self, logger=None):
        super().__init__(logger)
        self.lcxdb = PreLegalContentXmlDataBase()

    def _iter_acts(self, month: FullMonth, act_types: tuple):
        result = Hits()
        for act_type in act_types:
            results = self('act',
                           first=month.first.strftime('%Y-%m-%d'),
                           ultimo=month.ultimo.strftime('%Y-%m-%d'),
                           act_type=act_type,
                           year=month.year)
            hits = Hits()
            for celex, in_force, day, lang in results:
                hits.append(ActHit(
                    CelexCompound.from_string(celex),
                    in_force.toPython() if in_force is not None else None,
                    day.toPython(),
                    {lang_2(lang)}
                ))
            self.logger.info(f'Obtained {len(hits)} acts '
                             f'for month {month} and type {act_type}.')
            result.update(hits)
        return result.values()

    def pull_acts_representations(self, celex: str):
        self.lcxdb.pull_all_hits(query_templates['celex_wild_card'].format(celex))
        results = self('act_consolidates', celex=celex)
        for c_celex, day, lang in results:
            try:
                compound = CelexCompound.from_string(c_celex.toPython())
            except UnexpectedPatternException:
                continue
            CompoundHit(compound, day.toPython(), {lang_2(lang)}).persist()

    def pull_compound_celex_representations(self, cc: CelexCompound):
        assert cc.type is AnnexType.consolidate
        results = self('cons_celex_lang', comp_celex=str(cc))
        for day, lang in results:
            CompoundHit(cc, day.toPython(), {lang_2(lang)}).persist()

    def pull_all_corrigenda_representations(self, celex: CelexBase):
        results = self('corr_celex_lang', celex=str(celex))
        for number, day, lang in results:
            CompoundHit(CelexCompound.get(celex, number.toPython()),
                        day.toPython(), {lang_2(lang)}).persist()

    def _iter_conslegs(self, month: FullMonth, act_types: tuple):
        results = self('consleg',
                       first=month.first.strftime('%Y-%m-%d'),
                       ultimo=month.ultimo.strftime('%Y-%m-%d'))
        hits = Hits()
        for celex, day, lang in results:
            try:
                compound = CelexCompound.from_string(celex.toPython())
            except UnexpectedPatternException:
                continue
            if act_types:
                if compound.base.inter not in act_types:
                    continue
            hits.append(CompoundHit(compound, day.toPython(), {lang_2(lang)}))
        self.logger.info(f'Obtained {len(hits)} consolidations '
                         f'for month {month} and types {act_types}.')
        return hits.values()

    def iter_hits(self, months: List[FullMonth], act_types: tuple):
        for my_iter in (self._iter_acts, self._iter_conslegs):
            for m in months:
                for hit in my_iter(m, act_types):
                    yield hit

    @classmethod
    def update_recent_months(cls, trail: int, act_types: tuple):
        assert trail >= 1
        self = cls()
        month = FullMonth.instantiate(date.today())
        months = []
        for k in range(1, trail + 1):
            months.append(month)
            month = month.previous()
        for h in self.iter_hits(sorted(months), act_types=act_types):
            h.persist()


if __name__ == '__main__':
    lg = LegislationGetter()
    for clx in ('32009R0810',):
        lg.pull_acts_representations(clx)
