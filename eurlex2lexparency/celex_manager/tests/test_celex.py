import unittest
from datetime import date

from eurlex2lexparency.celex_manager.celex import CelexCompound, CelexBase, Annex, empty_annex, \
    UnexpectedPatternException, AnnexType

_pattern_test_data = {
    '32013R0575': CelexCompound(
        CelexBase(3, 2013, 'R', 575, ''),
        empty_annex),
    '02013R0575-20170315': CelexCompound(
        CelexBase(3, 2013, 'R', 575, ''),
        Annex(AnnexType.consolidate, date(2017, 3, 15))),
    '32013R0575R(01)': CelexCompound(
        CelexBase(3, 2013, 'R', 575, ''),
        Annex(AnnexType.corrigendum, 1)),
    '31972A0722(05)': CelexCompound(
        CelexBase(3, 1972, 'A', 722, '(05)'),
        empty_annex),
    '31972A0722(05)R(01)': CelexCompound(
        CelexBase(3, 1972, 'A', 722, '(05)'),
        Annex(AnnexType.corrigendum, 1)),
}

_not_yet_valid = ['12012A/TXT']


class TestCelex(unittest.TestCase):

    def test_pattern_parsing(self):
        for key, value in _pattern_test_data.items():
            self.assertEqual(str(CelexCompound.from_string(key)), str(value),
                             f'Failed for {key}')

    def test_not_yet_valid(self):
        for key in _not_yet_valid:
            with self.assertRaises(UnexpectedPatternException) as context:
                CelexCompound.from_string(key)
            self.assertTrue(' cannot be parsed (yet).' in str(context.exception))

    def test_parse_consolidates_extra(self):
        self.assertEqual(
            str(_pattern_test_data['02013R0575-20170315'].base),
            '32013R0575'
        )


if __name__ == '__main__':
    unittest.main()
