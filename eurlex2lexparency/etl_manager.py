import os
from argparse import ArgumentParser
from datetime import date

import requests
from urllib.parse import urljoin
import json
import logging
from sqlalchemy import or_, update, delete, and_
from sqlalchemy.exc import OperationalError

from eurlex2lexparency.celex_manager.model import SessionManager, Representation, Act, \
    Version as ActVersion
from eurlex2lexparency.celex_manager.celex import Version, CelexBase, UnexpectedPatternException
from .etl import AbstractAct, PhysicalAct, UploadError
from settings import LEXPATH, LANG_2_ADDRESS
from eurlex2lexparency.utils.generics import retry, get_fallbacker


class EtlManager:
    DATA_PATH = LEXPATH

    def __init__(self):
        self.logger = logging.getLogger('etl')
        self.sm = SessionManager()
        fallbacker = get_fallbacker(self.logger, exceptions=Exception)
        self.process_act = fallbacker(self.process_act)

    def inform_unavailability(self, celex, version: Version, language):
        if version.folder == 'initial':
            self.logger.warning(
                f'Informing unavailability does not work for initial versions '
                f'currently: ({celex}, {version.folder}, {language}).')
            return
        previous = None
        with self.sm() as s:
            for r in s.query(Representation)\
                .filter(Representation.celex == celex,
                        Representation.language == language,
                        Representation.date < version.consoli_date):
                previous = Version.create(r.date)
        if previous is None:
            self.logger.warning(
                f'Could not find previous version to: '
                f'({celex}, {version.folder}, {language}).')
            return
        requests.post(
            urljoin(LANG_2_ADDRESS[language],
                    f'/_unavailable/eu/{celex}/{version.folder}'),
            headers={"Content-type": "application/json"},
            data=json.dumps({
                'after': previous.folder,
                'date_document': version.consoli_date.strftime('%Y-%m-%d')})
        )

    def delete_representation(self, celex: str, version: date, language: str):
        with self.sm() as s:
            s.execute(delete(Representation, whereclause=and_(
                Representation.celex == celex,
                Representation.date == version,
                Representation.language == language
            )))

    def process_act(self, celex, version: Version, language) -> PhysicalAct:
        specification = f"{celex} ({version.folder}), {language}"
        self.logger.info(f"Processing {specification}.")
        try:
            path = os.path.join(self.DATA_PATH, CelexBase.from_string(celex).path)
        except UnexpectedPatternException:
            path = os.path.join(self.DATA_PATH, celex)
        acd = AbstractAct(celex, path)
        instance = acd.instantiate(language, version)
        self.logger.info(f"Successfully refined {specification}.")
        return instance

    @retry(OperationalError, tries=3, wait=10)
    def get_celex_version_list(self, language, celex=None, version=None,
                               only_enforced=False, upload=False):
        """ See __call__ method """
        version = Version.create(version) if version is not None else None
        with self.sm() as s:
            q = s.query(Representation)\
                .filter(Representation.language == language)
            if version is not None:
                q = q.filter(Representation.date == version.consoli_date)
            if only_enforced:
                q = q.join(Representation.version).join(ActVersion.act)\
                    .filter(Act.in_force)
            if celex is None:
                if upload:
                    # noinspection PyUnresolvedReferences
                    q = q.filter(Representation.uploaded.isnot(True))\
                        .filter(or_(
                            ~Representation.transformation.in_(
                                ('failed', 'repealer', 'impossible')),
                            Representation.transformation.is_(None)))
                else:
                    q = q.filter(Representation.transformation.is_(None))
            else:
                if type(celex) is str:
                    celex = [celex]
                # noinspection PyUnresolvedReferences
                q = q.filter(Representation.celex.in_(celex))
            cv = sorted(set((representation.celex,
                             version or Version.create(representation.date))
                            for representation in q))
        return cv

    def __call__(self, celex, language, version=None, upload=False, rm_local=False):
        """ Perform ETL to given celex list.
            :param celex: string that complies the celex format.
            :param version: (string) parameter to determine, whether
                 - the latest version
                 - the initial version
                 - the full history of all versions
                 shall be loaded.
            :param language: (Two character string), e.g. EN, DE
            :param upload: Indicates whether the document shall be uploaded
                after being transformed.
            :param rm_local: Shall the existing files be deleted first?
        """
        cv = self.get_celex_version_list(
            version=version, celex=celex, language=language, upload=upload)
        if rm_local:
            for celex, version in cv:
                self.remove_transformed(celex, language, version)
        for celex, version in cv:
            d = self.process_act(celex, version, language)
            if d is None:
                continue
            if d.transformation_status in ('repealer', 'failed'):
                continue
            if upload and not d.uploaded:
                try:
                    d.upload(LANG_2_ADDRESS[language])
                except UploadError as e:
                    self.logger.error(str(e))
                    self.inform_unavailability(celex, version, language)

    @staticmethod
    def set_in_force(celex, language, value):
        r = requests.put(
            urljoin(LANG_2_ADDRESS[language], f'_metadata/eu/{celex}/'),
            params={'in_force': str(value)})
        r.raise_for_status()

    def remove_transformed(self, celex, language, version: Version = None):
        with self.sm() as s:
            if version is None:
                versions = [Version.create(v.date)
                            for v in s.query(Act).get((celex,)).versions]
            else:
                versions = [version]
            # noinspection PyUnresolvedReferences
            s.execute(update(Representation)
                      .where(Representation.celex == celex)
                      .where(Representation.language == language)
                      .where(Representation.date.in_([v.consoli_date
                                                      for v in versions]))
                      .values(transformation=None))
        for v in versions:
            file_path = os.path.join(
                LEXPATH, CelexBase.from_string(celex).path, language,
                v.folder, 'refined.html')
            if os.path.isfile(file_path):
                os.remove(file_path)

    def delete(self, celex, language, version: Version = None, rm_local=False):
        if rm_local:
            self.remove_transformed(celex, language, version)
        path = f'eu/{celex}/'
        if version is not None:
            path = path + version
        r = requests.delete(urljoin(LANG_2_ADDRESS[language], path))
        if r.status_code not in (200, 404):
            r.raise_for_status()
        with self.sm() as s:
            u = update(Representation) \
                .where(Representation.celex == celex) \
                .where(Representation.language == language.upper())
            if version is not None:
                u = u.where(Representation.date == version.consoli_date)
            s.execute(u.values(uploaded=False))

    def all_failed(self, celex, language) -> bool:
        with self.sm() as s:
            status = [
                r for r in s.query(Representation)
                .filter(Representation.celex == celex)
                .filter(Representation.language == language)
                if r.transformation != 'failed']
        return not bool(status)

    def reupload(self, celex, language, rm_local=False):
        self(celex, language, rm_local=rm_local)
        if self.all_failed(celex, language):
            return
        self.delete(celex, language)
        self(celex, language, upload=True)


def parse_args():
    parser = ArgumentParser(
        description="Performs ETL on optionally provided list of documents.")

    parser.add_argument('--version', default=None,
                        help='Determine document\'s version to be etelled '
                             '(initial, latest, history, YYYYmmdd).',)
    parser.add_argument('--language', help='of the document.', default='EN')
    parser.add_argument(
        '--celex',
        help="CSV list of IDs to be processed."
             "If omitted: processing all untouched documents"
    )
    parser.add_argument(
        '--rm_local',
        help="If set, the already existing ",
        action="store_true"
    )
    parser.add_argument(
        '--upload',
        help="If set, the transformed documents are uploaded.",
        action="store_true"
    )
    args = parser.parse_args()

    if args.celex:
        args.celex = args.celex.split(',')
    return args


if __name__ == '__main__':
    etl = EtlManager()
    parsed = parse_args()
    etl(**parsed.__dict__)
