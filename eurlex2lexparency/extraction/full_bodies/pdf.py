import os
import requests
import logging

from eurlex2lexparency.extraction.generic import Retriever
from settings import LEXPATH
from eurlex2lexparency.celex_manager import CelexBase, Version
from eurlex2lexparency.celex_manager import SessionManager, Representation


class PDFLoader(Retriever):

    def __init__(self, local_path, url, logger=None):
        self.logger = logger or logging.getLogger()
        super().__init__(local_path, url)

    @property
    def local_file(self):
        return os.path.join(self.local_path, 'pdf.pdf')

    def open(self):
        if not os.path.isfile(self.local_file):
            raise FileNotFoundError

    def retrieve(self):
        os.makedirs(self.local_path, exist_ok=True)
        pdf = requests.get(self.url).content
        with open(self.local_file, mode='bw') as f:
            f.write(pdf)

    @classmethod
    def by(cls, celex, language, version='initial'):
        version = Version.create(version)
        celex = CelexBase.from_string(celex)
        with SessionManager()() as s:
            url = s.query(Representation).filter(
                Representation.celex == str(celex),
                Representation.date == version.consoli_date,
                Representation.language == language
            ).first().url_pdf
        return cls(
            os.path.join(LEXPATH, celex.path, language, version.folder, 'pdf'),
            url
        )
