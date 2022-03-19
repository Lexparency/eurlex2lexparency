import datetime
import logging
from contextlib import contextmanager
from os import getpid

from sqlalchemy import Column, Date, Boolean, String, ForeignKey, Enum, \
    DateTime, create_engine, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func

from eurlex2lexparency.celex_manager.celex import CelexCompound
from settings import CELEX_CONNECT_STRING


Base = declarative_base()


class Act(Base):
    """ Acts live in an abstract (platonic) world. They are not bound to a
        language nor any version in time.
    """
    __tablename__ = 'act'

    celex = Column(String(15), primary_key=True)
    publication_date = Column(Date)
    in_force = Column(Boolean)

    versions = relationship('Version', order_by='Version.date',
                            back_populates='act')

    def representations(self, language: str):
        result = []
        # noinspection PyTypeChecker
        for version in self.versions:
            for rep in version.representations:
                if rep.language == language:
                    result.append(rep)
        result.sort(key=lambda x: x.date)
        return result


class Version(Base):
    __tablename__ = 'version'

    celex = Column(String(15), ForeignKey(Act.celex), primary_key=True)
    date = Column(Date, primary_key=True, default=datetime.date(1900, 1, 1))

    act = relationship(Act)

    representations = relationship(
        'Representation',
        primaryjoin="and_(Version.celex == Representation.celex,"
                    "Version.date == Representation.date)",
        uselist=True,
        back_populates='version'
    )


class Representation(Base):
    __tablename__ = 'representation'

    def __init__(self, **kwargs):
        if 'formex_available' not in kwargs:
            try:
                year = kwargs['date'].year
            except KeyError:
                year = 1900
            if year < 2004 and year != 1900:
                kwargs['formex_available'] = False
        super().__init__(**kwargs)

    celex = Column(String(15), ForeignKey(Version.celex), primary_key=True)
    date = Column(Date, ForeignKey(Version.date), primary_key=True,
                  default=datetime.date(1900, 1, 1))
    language = Column(String(2), primary_key=True)
    transformation = Column(Enum(
        'failed', 'stubbed', 'success_fmx', 'success_htm',
        'impossible', 'repealer', 'success'))
    timestamp_refined = Column(DateTime)
    uploaded = Column(Boolean, default=False)
    formex_available = Column(Boolean)  # is this document available in formex?
    url_html = Column(String(200))
    url_pdf = Column(String(200))

    version = relationship(
        Version,
        primaryjoin="and_(Version.celex == Representation.celex,"
                    "Version.date == Representation.date)",
        back_populates=''
    )

    @property
    def act(self):
        return self.version.act

    @property
    def in_force(self):
        return self.act.in_force

    @property
    def loaded(self):
        return self.transformation.startswith('success')

    @property
    def compound_celex(self):
        return CelexCompound.get(self.celex, self.date)


class Changes(Base):
    __tablename__ = 'changes'

    change_2_changed_by = {
        'amends': 'amended_by',
        'completes': 'completed_by',
        'corrects': 'corrected_by',
        'repeals': 'repealed_by',
        'cites': 'cited_by',
    }
    c_values = ('amends', 'completes', 'repeals')

    celex_changer = Column(String(15), ForeignKey(Act.celex), primary_key=True)
    change = Column(Enum(*c_values), primary_key=True)
    celex_changee = Column(String(15), ForeignKey(Act.celex), primary_key=True)

    def __init__(self, changer, change, changee):
        assert changer == changee
        # noinspection PyArgumentList
        super().__init__(celex_changer=changer,
                         change=change, celex_changee=changee)


class Corrigendum(Base):
    __tablename__ = 'corrigendum'

    celex = Column(String(15), ForeignKey(Act.celex), primary_key=True)
    number = Column(Integer, primary_key=True)

    @property
    def compound_celex(self):
        return CelexCompound.get(self.celex, self.number)


class Correpresentation(Base):
    __tablename__ = 'correpresentation'

    celex = Column(String(15), ForeignKey(Corrigendum.celex), primary_key=True)
    number = Column(Integer, ForeignKey(Corrigendum.number), primary_key=True)
    language = Column(String(2), primary_key=True)
    implemented = Column(Boolean)
    transformation = Column(Enum(
        'failed', 'stubbed', 'success_fmx', 'success_htm',
        'impossible', 'repealer', 'success'))
    formex_available = Column(Boolean)  # is this document available in formex?
    url_html = Column(String(200))
    url_pdf = Column(String(200))

    corrigendum = relationship(
        Corrigendum,
        primaryjoin="and_(Corrigendum.celex == Correpresentation.celex,"
                    "Corrigendum.number == Correpresentation.number)")

    @property
    def compound_celex(self):
        return self.corrigendum.compound_celex


class Citation(Base):
    __tablename__ = 'citation'

    celex = Column(String(15), primary_key=True)
    cites_celex = Column(String(15), primary_key=True)


class DocumentElementID(Base):
    __tablename__ = 'document_skeleton'

    celex = Column(String(15), ForeignKey(Act.celex), primary_key=True)
    id = Column(String(50), primary_key=True)


class Log(Base):
    __tablename__ = 'logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pid = Column(Integer, default=getpid())
    level = Column(Enum('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'), default='NOTSET')
    time = Column(DateTime, server_default=func.now())
    module = Column(String(50))
    function = Column(String(100))
    message = Column(String(500), nullable=False)


class TableLogHandler(logging.Handler):

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.Session = sessionmaker(bind=self.engine)

    def emit(self, record):
        s = self.Session()
        try:
            # noinspection PyTypeChecker
            s.add(Log(
                level=record.levelname,
                module=record.module,
                function=record.funcName,
                message=record.msg
            ))
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()


class SessionManager:

    engine = create_engine(CELEX_CONNECT_STRING)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def __call__(self):
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception as e:
            s.rollback()
            raise e
        finally:
            s.close()


if __name__ == '__main__':
    Base.metadata.create_all(SessionManager.engine)
    # DocumentElementID.__table__.create(SessionManager.engine)
