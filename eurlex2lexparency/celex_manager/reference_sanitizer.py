from lxml import etree as et
from logging import getLogger

from lexref.utils import Singleton
from sqlalchemy.exc import IntegrityError

from eurlex2lexparency.celex_manager.model import SessionManager, DocumentElementID
from eurlex2lexparency.utils import xtml


class ReferenceSanitizer(metaclass=Singleton):
    def __init__(self):
        self.sm = SessionManager()
        self.logger = getLogger()

    @staticmethod
    def id_2_path(celex, id_):
        """The HTML-ID attributes within the refined.html documents follow
        a different convention as is finally used on the hosting engines.
        """
        if id_.startswith("toc-"):
            return f"/eu/{celex}/#{id_}"
        if id_ == "":
            return f"/eu/{celex}/"
        parts = id_.split("-", 1)
        if len(parts) == 1:
            leaf = parts[0]
            return f"/eu/{celex}/{leaf}/"
        leaf, sub = parts
        return f"/eu/{celex}/{leaf}/#{sub}"

    def get_relevant_existing_paths(self, celexes: set):
        result = set()
        with self.sm() as s:
            for celex in celexes:
                for r in s.query(DocumentElementID).filter(
                    DocumentElementID.celex == celex
                ):
                    result.add(self.id_2_path(celex, r.id))
        return result

    def cleanse(self, e: et.ElementBase):
        found_refs = {ref for ref in e.xpath("//a/@href") if ref.startswith("/eu/")}
        existing_paths = self.get_relevant_existing_paths(
            {ref.split("/")[2] for ref in found_refs}
        )
        for wrong_ref in found_refs - existing_paths:
            for a in e.xpath(f'//a[@href="{wrong_ref}"]'):
                xtml.unfold(a)

    def extract_ids(self, celex, e: et.ElementBase):
        current_ids = {e.attrib["id"] for e in e.xpath("//*[@id]")}
        current_ids.add("")  # References to the entire document.
        try:
            with self.sm() as s:
                stored_ids = {
                    r.id
                    for r in s.query(DocumentElementID).filter(
                        DocumentElementID.celex == celex
                    )
                }
                for id_ in current_ids - stored_ids:
                    if len(id_) > 50:
                        continue
                    s.add(DocumentElementID(celex=celex, id=id_))
        except (IntegrityError, UnicodeEncodeError):
            self.logger.warning(f"Could not store skeleton of {celex}")
