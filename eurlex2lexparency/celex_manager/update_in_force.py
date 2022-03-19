from datetime import date
from collections import namedtuple, Counter
import pandas as pd
from time import sleep

from SPARQLWrapper.SPARQLExceptions import EndPointInternalError
from numpy import isnan, nan
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from eurlex2lexparency.utils import SparqlKraken
from eurlex2lexparency.celex_manager.model import SessionManager, Act, Changes
from eurlex2lexparency.utils import retry

ActStatus = namedtuple('ActStatus', ['celex', 'in_force'])


class InForceStatusUpdater(SparqlKraken):

    def __init__(self):
        super().__init__()
        self.sm = SessionManager()

    def in_force(self, celex):
        results = self.sparql.query(
            self.templates['celex_in_force'].format(celex=celex))
        for (value,) in results:
            return value.toPython()

    @classmethod
    def law_type_from_celex(cls, celex):
        if len(celex) < 6:
            return
        return celex[5]

    def update(self):
        comparer = self.comparison()
        values = Counter(comparer['remote'])
        self.logger.info(f'Stats overview: {values}')
        unfounds = []
        with self.sm() as s:
            for _, (celex, local, remote, m) in comparer.iterrows():
                if isnan(remote or nan) or remote == local:
                    continue
                act = s.query(Act).get((celex,))
                if act is None:
                    unfounds.append(celex)
                else:
                    act.in_force = remote
        self.deforce_repealed()
        self.logger.info('Could not find celexes ' + str(unfounds))

    def deforce_repealed(self):
        with self.sm() as s:
            celexes = {
                r[0] for r in s.query(Changes.celex_changee)
                .filter(Changes.change == 'repeals').distinct()
            }
            s.execute(update(Act).where(Act.celex.in_(celexes))
                      .values(in_force=False))

    @retry(EndPointInternalError, tries=3, wait=300)
    def _remote_status_for(self, law_type: str, year: int):
        return self.sparql.query(
            self.templates['in_force_for'].format(law_type=law_type, year=year))

    def iter_remote_status_for(self, law_type: str = None, year: int = None):
        if law_type is None:
            for lt in ('R', 'L'):
                for s in self.iter_remote_status_for(lt, year):
                    yield s
        elif year is None:
            for y in range(1955, date.today().year):
                for s in self.iter_remote_status_for(law_type, y):
                    yield s
                sleep(5)
        else:
            try:
                results = self._remote_status_for(law_type, year)
            except EndPointInternalError:
                self.logger.warning(
                    f"Could not obtain status info for law_type {law_type},"
                    f" year {year}.")
            else:
                for celex, status in results:
                    if status is not None:
                        status = status.toPython()
                    yield ActStatus(str(celex), status)

    @retry(OperationalError, tries=4, wait=60)
    def iter_local_status_for(self, law_type='_', year='____'):
        with self.sm() as s:
            status = [
                ActStatus(a.celex, a.in_force)
                for a in s.query(Act).filter(
                    Act.celex.like(f'3{year}{law_type}____'))]
        return status

    def comparison(self) -> pd.DataFrame:
        remote = {s.celex: s.in_force for s in self.iter_remote_status_for()}
        local = {s.celex: s.in_force for s in self.iter_local_status_for()}
        return pd.merge(
            pd.Series(data=local, name='local'),
            pd.Series(data=remote, name='remote'),
            how='outer', left_index=True, right_index=True, indicator=True
        ).reset_index().rename(columns={'index': 'celex'})


if __name__ == '__main__':
    InForceStatusUpdater().update()
