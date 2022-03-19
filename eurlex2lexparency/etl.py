import os
from datetime import date
from operator import attrgetter
from shutil import rmtree
from lxml import etree as et
import requests
from urllib.parse import urljoin

from eurlex2lexparency.celex_manager.reference_sanitizer import ReferenceSanitizer
from eurlex2lexparency.transformation.special_treatments import treat
from eurlex2lexparency.transformation.generic.document import SimpleDocument
from eurlex2lexparency.transformation.html.document import CreepyRedirectException, \
    CreepyNotFoundException
from eurlex2lexparency.transformation import TransformingRepealerError
from eurlex2lexparency.celex_manager.model import SessionManager, Act, \
    Representation, Version as ActVersion
from eurlex2lexparency.celex_manager.celex import CelexBase, Version, UnexpectedPatternException
from eurlex2lexparency.transformation.conductor import transform
from eurlex2lexparency.extraction.meta_data.language_format import\
    EurLexLanguagesAndFormats
from eurlex2lexparency.extraction.meta_data.eli_data import construct_url_from
from eurlex2lexparency.extraction.meta_data import cdm_data
from eurlex2lexparency.extraction.full_bodies.html import HTMLoader
from eurlex2lexparency.extraction.full_bodies.formex import FormexLoader
from eurlex2lexparency.extraction.generic import FormatNotAvailable, Formats
from lexref.utils import limit_recursion_depth

from eurlex2lexparency.utils.generics import retry, SwingingFileLogger


class UnavailableRepresentation(Exception):
    pass


class UploadError(Exception):
    pass


@retry((FileNotFoundError, OSError), wait=3)
def load_source(sauce) -> SimpleDocument:
    return SimpleDocument.load(sauce)


rs = ReferenceSanitizer()


class AbstractAct:

    addb = SessionManager()  # abstract document data base
    domain = 'eu'

    def __init__(self, celex: str, local_path: str):
        """ That's right, the local path belongs to the abstract abstract.
        But only the path until the further language branching starts. Yeah,
        "abstract" doesn't mean that abstract. Not in the sense of
        "transcendent". It just means abstract in the sense that it is
        language- or version- agnostic. Note that any abstract is ultimately
        defined via its language- or version- representations. Without
        that, it can't exist.

        :param celex: (string) Document identifier
        :param local_path: (string) (language-agnostic) path to store the
            document.
        """
        self.celex = celex
        self.local_path = local_path
        os.makedirs(os.path.join(self.local_path, 'RDF'), exist_ok=True)
        self.representations = self.get_language_representations()

    @property
    def languages(self):
        return self.representations[Version.create('initial').consoli_date]\
            .keys()

    @property
    def in_force(self):
        with self.addb() as s:
            r = s.query(Act).filter(Act.celex == self.celex).first().in_force
        return r

    @property
    def publication_date(self):
        with self.addb() as s:
            r = s.query(Act).filter(Act.celex == self.celex).first()\
                .publication_date
        return r

    @in_force.setter
    def in_force(self, value):
        with self.addb() as s:
            r = s.query(Act).filter(Act.celex == self.celex).first()
            r.in_force = value

    def get_language_representations(self):
        with self.addb() as s:
            act = s.query(Act).get((self.celex,))
            if act is None:
                raise RuntimeError('Unknown document: {}.'.format(self.celex))
            consolidates = set([representation.date
                                for representation in act.versions])
        return {
            consoli_date: EurLexLanguagesAndFormats(
                os.path.join(self.local_path, 'RDF',
                             Version.create(consoli_date).folder),
                self.celex,
                consoli_date=consoli_date
            ).languages_to_formats
            for consoli_date in sorted(consolidates)
        }

    def latest(self, language=None):
        if language is None:
            return max(self.representations.keys())
        with self.addb() as s:
            result = max([
                r.date
                for r in s.query(Representation).filter(
                    Representation.celex == self.celex,
                    Representation.language == language
                )
                if r.transformation != 'repealer' and r.url_html != ''
            ])
        return result

    def latest_available(self, language: str):
        with self.addb() as s:
            try:
                result = max([
                    Version.create(r.date)
                    for r in s.query(Representation).filter(
                        Representation.celex == self.celex,
                        Representation.language == language,
                        Representation.transformation.in_(
                            ('stubbed', 'success_fmx', 'success_htm', 'success')
                        ))])
            except ValueError:
                result = None
        return result

    def get_meta_data(self, language):
        file_path = os.path.join(self.local_path, language, 'head.json')
        return cdm_data.ActMetaData.cached_retrieve(self.celex, language, file_path)

    def instantiate(self, language, version='latest'):
        """
        :param language: (string) Two letter country code. E.g.: DE, EN
        :param version: (date or string) indicating the version to be processed.
        :return: PhysicalAct (extracted, transformed, and loaded)
        """
        if version == 'latest':
            version = self.latest(language)
        version = Version.create(version)
        if version.consoli_date not in self.representations:
            raise UnavailableRepresentation(
                'There is no version {} for celex {}'
                .format(str(version), self.celex))
        if language not in self.representations[version.consoli_date]:
            raise UnavailableRepresentation(
                'Version {} for celex {} is not available in language {}.'
                .format(version.folder, self.celex, language))
        try:
            return PhysicalAct(self, language, version)
        except TransformingRepealerError:
            self.in_force = False
            if version == 'latest':
                return self.instantiate(language, version=self.latest(language))
            else:
                raise


class PhysicalAct:

    def __init__(self, abstract: AbstractAct, language, version):
        """ Spatial- and time-like fixed representation of the abstract
        :param abstract: (AbstractAct) underlying abstract abstract
        :param language: (string) Two-letter country code.
        :param version: (string or date) indicating the (consolidated) version
            of the abstract.
        """

        self.abstract = abstract
        self.language = language
        self.version = Version.create(version)
        self.local_path = os.path.join(self.abstract.local_path,
                                       self.language, self.version.folder)
        os.makedirs(self.local_path, exist_ok=True)
        self.logger = SwingingFileLogger.get('etl', self.local_path)
        try:
            self.formats = self.abstract\
                .representations[self.version.consoli_date][self.language]
        except KeyError:
            raise UnavailableRepresentation(
                '{} does not seem to exist.'.format(str(self)))
        self.local_path = os.path.join(self.abstract.local_path,
                                       self.language, self.version.folder)
        try:
            self.document = SimpleDocument.load(
                os.path.join(self.local_path, 'refined.html'))
        except (FileNotFoundError, OSError):
            self.document = self._instantiate_carefully()
            if self.formats.html is None and not self.formex_may_available:
                self.formex_available = False
                self._dump_stub()
        else:
            if self.transformation_status is None:
                if self.document.stubbed:
                    self.transformation_status = 'stubbed'
                else:
                    self.transformation_status = 'success'

    def __repr__(self):
        return f"PhysicalAct({self.abstract.celex}, {self.version}, {self.language})"

    def fall_back_meta_data(self) -> cdm_data.ActMetaData:
        try:
            celex_object = CelexBase.from_string(self.abstract.celex)
        except UnexpectedPatternException:
            type_document = None
            serial_number = None
        else:
            type_document = {
                'R': 'REG', 'D': 'DEC', 'L': 'DIR'}.get(celex_object.inter)
            serial_number = celex_object.number
        with self.abstract.addb() as s:
            act = s.query(Act).get((self.abstract.celex,))
            date_publication = act.publication_date
        if self.version.folder != 'initial':
            date_document = self.version.consoli_date
        else:
            date_document = date_publication
        return cdm_data.ActMetaData(
            self.language,
            in_force=self.abstract.in_force,
            date_document=date_document,
            date_publication=date_publication,
            type_document=type_document,
            serial_number=serial_number)

    @limit_recursion_depth(2)
    def _instantiate_carefully(self):
        # noinspection PyBroadException
        try:
            self._instantiate()
        except TransformingRepealerError:
            self.transformation_status = 'repealer'
            if self.abstract.in_force:
                self.abstract.in_force = False
            return
        except CreepyRedirectException as e:
            self.url_html = e.target
            self.cleanup(os.path.join(self.local_path, 'htm'))
            self._instantiate_carefully()
        except CreepyNotFoundException as e:
            self.set_to_non_existence(e.format)
            self._dump_stub()
        except Exception:
            self._dump_stub()
            self.logger.error(f'Could not transform {self}.\n', exc_info=True)
        return SimpleDocument.load(
            os.path.join(self.local_path, 'refined.html'))

    def _dump_stub(self):
        """ This is a fallback-action, to be performed, if
        :return: SimpleDocument with just a head-Element in the source
        """
        def inner():
            html = et.Element('html', lang=self.language)
            html.append(et.Element('head'))
            dt = SimpleDocument(source=html, language=self.language)
            dt.meta_data.join(self._get_meta_data())
            return dt

        try:
            inner().dump(self.local_path)
        except Exception:
            self.transformation_status = 'failed'
            raise
        else:
            self.transformation_status = 'stubbed'

    def _carefully_load(self):
        """
        :return: Instance of HTMLLoader or FormexLoader
        """
        try:
            if not self.formex_may_available:
                raise FormatNotAvailable
            fmt_dir = os.path.join(self.local_path, 'fmx')
            os.makedirs(fmt_dir, exist_ok=True)
            dl = FormexLoader(
                fmt_dir,
                url=self.abstract.celex
                if self.version.folder == 'initial'
                else '0{}-{}'.format(self.abstract.celex[1:],
                                     self.version.folder),
                language=self.language,
                logger=self.logger
            )
        except FormatNotAvailable:
            self.formex_available = False
            if self.formats.html is None:
                raise
            fmt_dir = os.path.join(self.local_path, 'htm')
            os.makedirs(fmt_dir, exist_ok=True)
            dl = HTMLoader(
                os.path.join(self.local_path, 'htm'),
                url=self.formats.html,
                logger=self.logger
            )
        else:
            self.formex_available = True
        return dl

    def _transform(self, dl):
        try:
            document = transform(dl.document, self.language, logger=self.logger)
        except Exception as e:
            if self.formex_available:
                # Did this failure happen with formex input?
                # Use HTML as fallback:
                self.logger.error(
                    'Error occurred during processing formex version of'
                    ' {} ({})'.format(self.abstract.celex, self.version.folder),
                    exc_info=True
                )
                if self.formats.html is None:
                    raise e
                dl = HTMLoader(os.path.join(self.local_path, 'htm'),
                               url=self.formats.html, logger=self.logger)
                document = transform(
                    dl.document, self.language, logger=self.logger)
            else:
                raise e
        return document, dl

    def _get_meta_data(self) -> cdm_data.ActMetaData:
        cdm_data.set_logger(self.logger)
        self.logger.info("Collecting meta-data.")
        meta_data = self.abstract.get_meta_data(self.language)
        if self.abstract.in_force is not None \
                and self.abstract.in_force != meta_data.in_force:
            meta_data.in_force = self.abstract.in_force
        if self.version.folder != 'initial':
            meta_data.date_document = self.version.consoli_date
        elif meta_data.date_document is None:
            meta_data.date_document = self.abstract.publication_date
        meta_data.version = self.version.folder
        meta_data.source_url = construct_url_from(
            # Was agreed with Daniel Liebig (Buzer), to always link to the initial
            # overview page.
            self.abstract.celex, date(1900, 1, 1), self.language)
        meta_data.coalesce(self.fall_back_meta_data())
        meta_data.set_title_data()
        meta_data.popularize()  # useful if new short titles have been configured
        meta_data.skip_external_citations()
        return meta_data

    def _instantiate(self):
        document, dl = self._transform(self._carefully_load())
        treat[self.abstract.celex](document.source)
        created_format = os.path.split(dl.local_path)[-1]
        # load (well, store to local storage ... not yet to elasticsearch)
        document.meta_data.join(self._get_meta_data())
        document.meta_data.cleanse()
        if 'initial' != self.version.folder:
            # substitute preamble
            try:
                previous_preamble = self.get_previous_preamble(self.version)
            except FileNotFoundError as e:
                self.logger.warning(e)
            else:
                current_preamble = document.source.xpath('//*[@id="PRE"]')[0]
                current_preamble.addnext(previous_preamble)
                current_preamble.getparent().remove(current_preamble)
        document.cleanse(self.abstract.domain, self.abstract.celex)
        rs.extract_ids(self.abstract.celex, document.source)
        rs.cleanse(document.source)
        document.dump(self.local_path)
        self.transformation_status = 'success_{}'.format(created_format)

    def get_previous_preamble(self, version: Version):
        # Attention: Some kind of hotfix. Since consolidated versions often do
        # not have a full preamble
        # TODO: Make this step dependant on how large the preamble of the
        #  new document actually is
        base_path = os.path.dirname(self.local_path)
        versions = [
            Version.create(d) for d in os.listdir(base_path)
            if Version.able(d) and os.path.isdir(os.path.join(base_path, d))
        ]
        versions.sort(key=attrgetter('consoli_date'))
        for v in versions:
            if v == version:
                raise FileNotFoundError('No previous preamble found.')
            source_ = os.path.join(self.abstract.local_path, self.language,
                                   v.folder, 'refined.html')
            try:
                d = load_source(source_)
            except (FileNotFoundError, OSError):
                continue
            else:
                recitals = d.source.find('.//ol[@class="lxp-recitals"]')
                if recitals is None:
                    continue
                return d.articles['PRE'].source

    def set_to_non_existence(self, format_):
        folder = format_
        with self.abstract.addb as s:
            r = s.query(Representation).get((
                self.abstract.celex, self.version.consoli_date, self.language))
            if format_ in ('html', 'htm'):
                r.url_html = ''
                folder = 'htm'
            elif format_ == 'pdf':
                r.url_pdf = ''
                folder = 'pdf'
            elif format_ in ('formex', 'fmx'):
                r.formex_available = False
                folder = 'fmx'
        self.cleanup(os.path.join(self.local_path, folder))

    def cleanup(self, path=None):
        path = path or self.local_path
        for element in os.listdir(path):
            full_path = os.path.join(path, element)
            if os.path.isdir(full_path):
                rmtree(full_path)
            else:
                assert os.path.isfile(full_path)
                if not element.endswith('.log'):
                    os.remove(full_path)

    @property
    def url_html(self):
        return self.formats.html

    @url_html.setter
    def url_html(self, value):
        self.formats = Formats(value, self.formats.pdf)
        self.abstract.representations[
            self.version.consoli_date][self.language] = self.formats
        with self.abstract.addb() as s:
            this = s.query(Representation).get((
                self.abstract.celex, self.version.consoli_date, self.language))
            this.url_html = value

    @property
    def formex_available(self):
        with self.abstract.addb() as s:
            this = s.query(Representation).get((
                self.abstract.celex, self.version.consoli_date, self.language))
            result = this.formex_available
        return result

    @formex_available.setter
    def formex_available(self, value):
        with self.abstract.addb() as s:
            r = s.query(Representation).filter(
                Representation.celex == self.abstract.celex,
                Representation.language == self.language,
                Representation.date == self.version.consoli_date
            ).first()
            r.formex_available = value

    @property
    def formex_may_available(self):
        if self.formex_available is not None:
            return self.formex_available
        if self.version.consoli_date.year >= 2004:
            return True
        with self.abstract.addb() as s:
            this = s.query(ActVersion).get((
                self.abstract.celex, self.version.consoli_date))
            if this.act.publication_date.year >= 2004:
                result = True
            else:
                result = False
        return result

    def __str__(self):
        return 'PhysicalAct(celex={}, language={}, version={})'.format(
            self.abstract.celex,
            self.language,
            self.version.consoli_date
        )

    @property
    def standard_filters(self):
        return (Representation.celex == self.abstract.celex,
                Representation.language == self.language,
                Representation.date == self.version.consoli_date)

    @property
    def uploaded(self) -> bool:
        with self.abstract.addb() as s:
            r = s.query(Representation).filter(*self.standard_filters).first()\
                .uploaded
        return r

    @uploaded.setter
    def uploaded(self, value: bool):
        with self.abstract.addb() as s:
            r = s.query(Representation).filter(*self.standard_filters).first()
            r.uploaded = value

    @property
    def transformation_status(self):
        # TODO: merge the behaviour of these two properties.
        with self.abstract.addb() as s:
            r = s.query(Representation).filter(*self.standard_filters).first()\
                .transformation
        return r

    @transformation_status.setter
    def transformation_status(self, value):
        with self.abstract.addb() as s:
            r = s.query(Representation).filter(*self.standard_filters).first()
            r.transformation = value

    def upload(self, address: str):
        """
            1. Do the actual upload
            2. Update the "uploaded" field.
        """
        if self.uploaded:
            self.logger.warning(f"{self} is already uploaded.")
        r = requests.post(
            urljoin(address, 'eu/'),
            headers={"Content-type": "text/html; charset=UTF-8"},
            data=self.document.dumps()
        )
        if r.status_code == 200:
            self.uploaded = True
        else:
            self.transformation_status = 'failed'
            raise UploadError("Something went wrong on uploading: "
                              f"status: {r.status_code}, text: {r.text}")
