from lxml import etree as et
import unittest

from eurlex2lexparency.utils.xtml import concatenate_siblings


class TextXtmlUtils(unittest.TestCase):
    def test_concatenate_siblings(self):
        inp = et.fromstring(
            b'<html><p class="norm">Hallo Welt </p><p class="norm">wie gehts.</p><br>bla<p>Tschu mit u</p>'
            b'<p class="norm">Hallo Welt </p><p class="norm">wie gehts.</p></html>',
            parser=et.HTMLParser(),
        )
        output = et.fromstring(
            b'<html><body><p class="norm">Hallo Welt wie gehts.</p><br/>bla<p>Tschu mit u</p>'
            b'<p class="norm">Hallo Welt wie gehts.</p></body></html>',
            parser=et.HTMLParser(),
        )
        concatenate_siblings(inp, "p", **{"class": "norm"})
        self.assertEqual(et.tostring(inp), et.tostring(output))


if __name__ == "__main__":
    unittest.main()
