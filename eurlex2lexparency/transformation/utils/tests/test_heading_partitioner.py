import unittest

from eurlex2lexparency.transformation.utils.generics import HeadingAnalyzer


class TestHeadingAnalyzer(unittest.TestCase):

    def test_en(self):
        _ha = HeadingAnalyzer('EN')

        def ha(in_text):
            co, text, title = _ha(in_text)
            return co.collated, text, title

        self.assertEqual(('CHP_5', 'Chapter 5', None), ha('Chapter 5'))
        self.assertEqual(('ANX', 'ANNEX', None), ha('ANNEX'))
        self.assertEqual(('ANX_II_B', 'ANNEX II B', None), ha('ANNEX II B'))
        self.assertEqual(('ANX', 'ANNEX', 'Correlation Tables'), ha('ANNEX Correlation Tables'))
        self.assertEqual(('SUB_IIa', 'Subsection IIa', None), ha('Subsection IIa'))
        self.assertRaises(ValueError, lambda: ha('Article 10.'))
        self.assertRaises(ValueError, lambda: ha(''))
        self.assertRaises(ValueError, lambda: ha('Yeah, Whatever'))
        self.assertRaises(ValueError, lambda: ha('(Article 7)'))

    def test_de(self):
        _ha = HeadingAnalyzer('DE')
        def ha(in_text):
            co, text, title = _ha(in_text)
            return co.collated, text, title
        self.assertRaises(ValueError, lambda: ha('EG-Fusionskontrollverordnung'))



if __name__ == '__main__':
    unittest.main()
