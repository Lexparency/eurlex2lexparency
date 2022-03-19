import urllib3
import certifi
import os
from lxml import etree as et
from math import ceil
from time import sleep
from hashlib import sha256
from functools import lru_cache
import datetime
import logging
from typing import Iterable

from sqlalchemy.exc import OperationalError

from eurlex2lexparency.celex_manager.celex import CelexBase, CelexCompound, \
    UnexpectedPatternException, AnnexType
from settings import LEXPATH
from eurlex2lexparency.utils.eurlex_request_lock import eurlex_request_queue

from eurlex2lexparency.utils.generics import get_fallbacker, wait_until_tomorrow, \
    get_file_content, TwoWay, retry
from .model import Act, Version, Representation, SessionManager, Corrigendum, \
    Correpresentation

session = SessionManager()


class PersistableHit:
    celex: CelexCompound
    languages: Iterable
    in_force: bool
    publication_date: datetime.date
    work_date: datetime.date

    default_date = datetime.date(1900, 1, 1)

    @retry(OperationalError, tries=3, wait=60)
    def persist(self):
        celex = str(self.celex.base)
        with session() as s:
            record = s.query(Act).get((celex,))
            if record is None:
                if self.celex.type == AnnexType.none:
                    s.add(Act(celex=celex,
                              publication_date=self.publication_date,
                              in_force=self.in_force))
                else:
                    s.add(Act(celex=celex))
            elif self.celex.type == AnnexType.none:
                if self.in_force is not None:
                    record.in_force = self.in_force
                if self.publication_date is not None:
                    record.publication_date = self.publication_date
            if self.celex.type in (AnnexType.consolidate, AnnexType.none):
                if self.celex.type == AnnexType.consolidate:
                    v_date = self.work_date
                else:
                    v_date = self.default_date
                version = s.query(Version).get((celex, v_date))
                if version is None:
                    s.add(Version(celex=celex, date=v_date))
                for language in self.languages:
                    record = s.query(Representation).get((
                        celex, v_date, language))
                    if record is None:
                        s.add(Representation(celex=celex,
                                             date=v_date,
                                             language=language))
            elif self.celex.type == AnnexType.corrigendum:
                c_number = self.celex.annex.value
                corrigendum = s.query(Corrigendum).get((celex, c_number))
                if corrigendum is None:
                    s.add(Corrigendum(celex=celex, number=c_number))
                for language in self.languages:
                    record = s.query(Correpresentation) \
                        .get((celex, c_number, language))
                    if record is None:
                        s.add(Correpresentation(celex=celex,
                                                number=c_number,
                                                language=language))


MODULE_PATH = os.path.dirname(os.path.realpath(__file__))

# noinspection HttpUrlsUsage
namespaces = {'ns1': 'http://www.w3.org/2003/05/soap-envelope',
              'ns2': 'http://eur-lex.europa.eu/search'}
parser = et.XMLParser(remove_blank_text=True, encoding='utf-8')


class InconsistentUpdate(Exception):
    pass


class UnexpectedResponse(Exception):
    pass


class RequestLimitReached(Exception):
    pass


country_mapping = TwoWay(('three', 'two'), [
    ('BUL', 'BG'), ('HRV', 'HR'), ('CES', 'CS'), ('DAN', 'DA'), ('NLD', 'NL'),
    ('ENG', 'EN'), ('EST', 'ET'), ('FIN', 'FI'), ('FRA', 'FR'), ('DEU', 'DE'),
    ('ELL', 'EL'), ('HUN', 'HU'), ('GLE', 'GA'), ('ITA', 'IT'), ('LAV', 'LV'),
    ('LIT', 'LT'), ('MLT', 'MT'), ('POL', 'PL'), ('POR', 'PT'), ('RON', 'RO'),
    ('SLK', 'SK'), ('SLV', 'SL'), ('SPA', 'ES'), ('SWE', 'SV')
])


def multi_celex_query(celexes):
    if len(celexes) > 100:
        raise RuntimeError('List of requested celexes too long')
    return '<![CDATA[{}]]>'.format(' OR '.join(map('DN = {}'.format, celexes)))


query_templates = {
    'celex_wild_card':  # used
    '<![CDATA[DN = {0} OR DN-old = {0} ORDER BY DN ASC]]>',
    'consleg_celex_wild_card':
    '<![CDATA[DTS_SUBDOM = CONSLEG AND BF = {0}* ORDER BY BF ASC]]>',
    'consleg_celex_year':  # used
    '<![CDATA[DTS_SUBDOM = CONSLEG AND BF = 3* '
        'AND DD_YEAR = {} ORDER BY DD ASC, BF ASC]]>',
    'all_versions_wild_card':
        '<![CDATA[(DTS_SUBDOM = CONSLEG '
        'AND BF = {0}*) OR (DN = {0} OR DN-old = {0})]]>'
}


class EurLexWebServiceHit(PersistableHit):

    def __init__(self, source):
        if et.iselement(source):
            self.e = source
        else:
            if os.path.isfile(source):
                sauce = get_file_content(source)
            else:
                sauce = source
            self.e = et.fromstring(sauce, parser=parser)

    def __str__(self):
        return et.tostring(self.e, pretty_print=True, encoding='unicode')

    @property
    def in_force(self):
        try:
            return eval(self.work.xpath(
                './ns2:RESOURCE_LEGAL_IN-FORCE/ns2:VALUE',
                namespaces=namespaces)[0].text.capitalize())
        except IndexError:
            return

    @property
    @lru_cache(maxsize=1)
    def celex(self) -> CelexCompound:
        return CelexCompound.from_string(
            self.work.xpath('./ns2:ID_CELEX/ns2:VALUE',
                            namespaces=namespaces)[0].text)

    @property
    def publication_date(self):
        path = ('RESOURCE_LEGAL_PUBLISHED_IN_OFFICIAL-JOURNAL',
                'EMBEDDED_NOTICE', 'WORK', 'DATE_PUBLICATION', 'VALUE')
        try:
            return datetime.datetime.strptime(
                self.work.xpath('./ns2:{}/text()'.format('/ns2:'.join(path)),
                                namespaces=namespaces)[0],
                '%Y-%m-%d').date()
        except IndexError:
            return None

    @property
    def work(self):
        return self.e.xpath('./ns2:content/ns2:NOTICE/ns2:WORK',
                            namespaces=namespaces)[0]

    @property
    def work_date(self):
        e = self.work.xpath('./ns2:WORK_DATE_DOCUMENT', namespaces=namespaces)[0]
        day = int(e.xpath('./ns2:DAY', namespaces=namespaces)[0].text)
        month = int(e.xpath('./ns2:MONTH', namespaces=namespaces)[0].text)
        year = int(e.xpath('./ns2:YEAR', namespaces=namespaces)[0].text)
        return datetime.date(year, month, day)

    @property
    def languages(self):
        path = ('WORK_HAS_EXPRESSION', 'EMBEDDED_NOTICE', 'EXPRESSION',
                'EXPRESSION_USES_LANGUAGE', 'OP-CODE')
        languages_raw = self.work.xpath(
            './ns2:{}/text()'.format('/ns2:'.join(path)), namespaces=namespaces)
        return [country_mapping.get(three=lr) for lr in languages_raw]


class DoQueryResult:
    """Class to convert response from doQuery action to a python object"""

    def __init__(self, response_text, logger=None):
        self._r_tree = et.ElementTree(
            et.fromstring(response_text, parser=parser))
        self.logger = logger or logging.getLogger()
        try:
            self._search_results = self._r_tree.xpath(
                '/ns1:Envelope/ns1:Body/ns2:searchResults',
                namespaces=namespaces
            )[0]
        except IndexError:
            fail_reason = self._r_tree.xpath(
                '/ns1:Envelope/ns1:Body/ns1:Fault/ns1:Reason/ns1:Text',
                namespaces=namespaces
            )[0]
            if fail_reason.text == 'The maximum number of call is reached ' \
                                   'for web service demands':
                raise RequestLimitReached
            else:
                raise UnexpectedResponse(
                    'New fail reason: {}'.format(fail_reason.text))
        else:
            self._total_hits = self._search_results.xpath(
                './ns2:totalhits', namespaces=namespaces)[0]
            self._page = self._search_results.xpath(
                './ns2:page', namespaces=namespaces)[0]
            self._page_size = self._search_results.xpath(
                './ns2:numhits', namespaces=namespaces)[0]
            self.hits = dict()
            for hit in map(EurLexWebServiceHit, self._search_results.xpath(
                    'ns2:result', namespaces=namespaces)):
                try:
                    key = str(hit.celex)
                except UnexpectedPatternException as e:
                    self.logger.error(str(e))
                    continue
                self.hits[key] = hit

    @property
    def page(self):
        return int(self._page.text)

    @property
    def search_language(self):
        return self._search_results.xpath('./ns2:language',
                                          namespaces=namespaces)[0].text

    @property
    def total_hits(self):
        return int(self._total_hits.text)

    @total_hits.setter
    def total_hits(self, value):
        if self.total_hits > value:
            raise InconsistentUpdate(
                'The new value of "total_hits" should not decrease.')
        self._total_hits.text = str(value)

    @property
    def page_size(self):
        return int(self._page_size.text)

    @page_size.setter
    def page_size(self, value):
        if self.page_size > value:
            raise InconsistentUpdate(
                'The new value of "page_size" should not decrease.')
        self._page_size.text = str(value)

    @property
    def total_pages(self):
        return int(ceil(self.total_hits / self.page_size))

    def __str__(self):
        return et.tostring(self._r_tree, encoding='unicode', pretty_print=True)

    def pages_left_to_go(self, page):
        return self.total_pages - page

    def store_results_to(self, path, split=True):
        fallbacker = get_fallbacker(self.logger)
        if split:
            for celex, hit in self.hits.items():
                file_path = os.path.join(path, str(hit.celex) + '.xml')
                with open(file_path, mode='w', encoding='utf-8') as f:
                    f.write(str(hit))
                fallbacker(hit.persist)()
        else:
            self._r_tree.write(path, encoding='utf-8')

    def extend(self, response):
        """ Consistently merge self with response object.
        :param response: (DoQueryResult)
            Object to me merged into self.
        """
        assert isinstance(response, DoQueryResult)
        assert self.search_language == response.search_language
        for key, hit in response.hits.items():
            if key in self.hits:  # Update the existing hit
                self._search_results.remove(self.hits[key].e)
                self.hits.pop(key)
            else:
                self.total_hits += 1
                self.page_size += 1
            self._search_results.append(hit.e)
            self.hits[key] = hit


class DoQueryResults(DoQueryResult):

    def __init__(self, arg):
        if os.path.isfile(arg):
            self.file_path = arg
            super().__init__(get_file_content(arg, encoding='utf-8'))
        elif type(arg) is str:
            super().__init__(arg)

    def __del__(self):
        if hasattr(self, 'file_path'):
            self.store_results_to(self.file_path, split=False)


class DoQuery:
    """ Class for a callable to execute doQuery (EUR-Lex SOAP service). """

    max_page_size = 100
    envelope_template = get_file_content(
        os.path.join(MODULE_PATH, 'doQuery_envelope_template.xml'))

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger()
        self.http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where()
        )
        self._url = 'https://eur-lex.europa.eu/EURLexWebService'
        # noinspection HttpUrlsUsage
        self._headers = {
            'Content-Type':
                'application/soap+xml; charset=utf-8;'
                'action="http://eur-lex.europa.eu/EURLexWebService/doQuery"',
            'SOAPAction': '"http://eur-lex.europa.eu/EURLexWebService/doQuery"'
        }

    def __call__(self, query, page=1,
                 page_size=max_page_size, search_language='en'):
        search_language = search_language.lower()
        assert len(search_language) == 2
        page_size = min(page_size, self.max_page_size)
        # TODO: Implementation of parameter excludeAllConsleg
        eurlex_request_queue.wait()
        r = self.http.request(
            'POST',
            self._url,
            body=self.envelope_template.format(
                query=query,
                page=page,
                size=page_size,
                language=search_language
            ),
            headers=self._headers
        )
        if (r.status, r.reason) not in [(200, 'OK'),
                                        (500, 'Internal Server Error')]:
            raise RuntimeError(
                'Request status and reason is {}, {}'.format(r.status, r.reason))
        return DoQueryResult(r.data, logger=self.logger)


def total_pages(total_hits, page_size):
    return int(ceil(total_hits / page_size))


class PreLegalContentXmlDataBase:
    niceness = 5
    db_path = os.path.join(LEXPATH, 'PRE')
    logger = None
    inquirer = None

    def __init__(self):
        for sub_path in ('queries', 'elements'):
            os.makedirs(os.path.join(self.db_path, sub_path), exist_ok=True)
        if self.logger is None:
            type(self).logger = logging.getLogger()
        if self.inquirer is None:
            type(self).inquirer = DoQuery(logger=self.logger)

    def do_query(self, query, page=1):
        try:
            return self.inquirer(query, page)
        except RequestLimitReached:
            self.inquirer.logger.info('Request limit reached '
                                      '(waiting until next day '
                                      f'for query {query}).')
            wait_until_tomorrow(goodwill=15)
            self.inquirer.logger.info('Resuming result collection.')
            return self.inquirer(query, page)

    def pull_all_hits(self, query, resume=False):
        query_hash = sha256(bytes(query, encoding='utf-8')).hexdigest()
        file_path = os.path.join(self.db_path, 'queries', f'{query_hash}.xml')
        if os.path.isfile(file_path) and resume:
            hit_list = DoQueryResults(file_path)
            start_page = max(1, int(float(hit_list.page_size)
                                    / self.inquirer.max_page_size))
            hit_list.extend(self.do_query(query, page=start_page))
            start_page += 1
            self.logger.info(f'Resuming query <{query}> ({query_hash}) '
                             f'from page {start_page}.')
        else:
            self.logger.info(f'A new start for query <{query}> ({query_hash}).')
            hit_list = self.do_query(query)
            hit_list.store_results_to(file_path, split=False)
            hit_list = DoQueryResults(file_path)
            start_page = 2

        for page in range(start_page, hit_list.total_pages + 1):
            hit_list.extend(self.do_query(query, page=page))
            sleep(self.niceness)
        hit_list.store_results_to(os.path.join(self.db_path, 'elements'))

    def get_celexes_where(self, resume=False, consleg=False, **where):
        wild_card = CelexBase.wildcard_where(**where)
        template_key = 'consleg_celex_wild_card' if consleg else 'celex_wild_card'
        query = query_templates[template_key].format(wild_card).replace('**', '*')
        self.pull_all_hits(query, resume=resume)

    def get_conslegs_from(self, year, resume=False):
        query = query_templates['consleg_celex_year'].format(year)
        self.pull_all_hits(query, resume=resume)


if __name__ == '__main__':
    a = EurLexWebServiceHit(os.path.join(LEXPATH, 'PRE',
                                         'elements', '02015R0848-20180726.xml'))
    print(a.publication_date)
    a.persist()
