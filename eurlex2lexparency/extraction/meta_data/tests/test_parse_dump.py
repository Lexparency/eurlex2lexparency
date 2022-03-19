import unittest
import os
from lxml import etree as et

from eurlex2lexparency.extraction.meta_data.cdm_data import ActMetaData


class TestParseDump(unittest.TestCase):
    FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'stub_{}.html')

    @staticmethod
    def get_metas(sauce: str):
        e = et.fromstring(sauce, parser=et.HTMLParser())
        return sorted([et.tostring(m, encoding='unicode')
                       for m in e.xpath('/head/meta[@property]')])

    def setUp(self) -> None:
        self.keys = '12'
        self.raw = {
            key: et.ElementTree(file=self.FILE_PATH.format(key),
                                parser=et.HTMLParser(remove_blank_text=True)
                                ).getroot()
            for key in self.keys
        }
        self.parsed = {key: ActMetaData.parse(raw)
                       for key, raw in self.raw.items()}

    def test(self):
        for key in self.keys:
            in_metas = self.get_metas(et.tostring(self.raw[key]))
            out_metas = self.get_metas(self.parsed[key].to_html_stub())
            self.assertEqual(in_metas, out_metas)


if __name__ == '__main__':
    unittest.main()
