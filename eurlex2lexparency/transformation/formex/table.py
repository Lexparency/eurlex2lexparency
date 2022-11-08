"""
Transformation of formex table into html
TODO: Handle ACCV attributes.
"""
from lxml import etree as et

from eurlex2lexparency.utils import xtml
from eurlex2lexparency.transformation.utils.generic_transformer import XMLTransformer


class Caption(XMLTransformer):
    def __init__(self, element, target_tag="caption"):
        self.target_tag = target_tag
        super().__init__(element)

    def _transform(self):
        self.e.tag = self.target_tag
        xtml.flatten_by_paths(self.e, "./TI", "./TI/P")
        for sec_title in self.e.xpath("./STI"):
            sec_title.tag = "h3"
            xtml.flatten_by_paths(sec_title, "P")
            break


class Cell(XMLTransformer):
    def __init__(self, element: et.ElementBase, target_tag="td"):
        assert element.tag == "CELL"
        self.target_tag = target_tag
        super().__init__(element)

    def _transform(self):
        self.e.tag = self.target_tag
        for key, value in self.e.attrib.items():
            if key in ("COL", "TYPE"):
                self.e.attrib.pop(key)
            if key in ("COLSPAN", "ROWSPAN"):
                self.e.attrib[key.lower()] = self.e.attrib.pop(key)
        for ie in self.e.xpath("./IE"):
            assert (self.e.text or "").strip() == ""
            self.e.text = " "
            self.e.remove(ie)
            break


class FormexTableTransformer:
    def __init__(self, table: et.ElementBase):
        self.e = table
        self.e.tag = "table"
        for key in self.e.attrib:
            self.e.attrib.pop(key)
        self._handle_caption()
        self._handle_body()
        self.e.attrib["class"] = "table"

    def _handle_caption(self):
        for title in self.e.xpath("./TITLE[TI]"):
            Caption(title)
            break

    def _handle_body(self):
        body = self.e.xpath("./CORPUS")[0]
        body.tag = "tbody"
        for header in body.xpath('ROW[@TYPE="HEADER"]'):
            over_header = et.Element("thead")
            body.addprevious(over_header)
            over_header.append(header)
            header.tag = "tr"
            header.attrib.pop("TYPE", None)
            for cell in header:
                Cell(cell, "th")
            break  # If there are more than 1 header element, later stepp will raise a warning.
        for bulk in body.xpath("./BLK"):
            # e.g. used by CELEX:32006R1907
            for bulk_title in bulk.xpath("./TI.BLK"):
                row = et.Element("tr")
                bulk_title.addprevious(row)
                row.append(bulk_title)
                bulk_title.tag = "td"
                for attrib in bulk_title.attrib.keys():
                    bulk_title.attrib.pop(attrib)
                bulk_title.attrib["colspan"] = "2"
            xtml.unfold(bulk)
        for row in body.xpath("./ROW"):
            row.attrib.pop("TYPE", None)
            row.tag = "tr"
            for cell in row:
                Cell(cell)
