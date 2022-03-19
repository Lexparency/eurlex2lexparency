import unittest
from lxml import etree as et
import os

from eurlex2lexparency.transformation.formex.formula import FormulaNodeParser


class TestFormulaParser(unittest.TestCase):

    def setUp(self):
        self.formulas = et.ElementTree(file=os.path.join(os.path.dirname(__file__), 'data', 'formulas.xml'))

    def test_latex(self):
        for comparer in self.formulas.xpath('/MATH/COMPARER'):
            formula = FormulaNodeParser(comparer[0])
            latext = comparer[1].text
            self.assertEqual(formula.latex, latext)

    def test_latex_unchanged(self):
        """ Checks that parsing and getting latex doesn't modify the underlying XML. """
        for comparer in self.formulas.xpath('/MATH/COMPARER'):
            formex_string = et.tostring(comparer[0])
            formula = FormulaNodeParser(comparer[0])
            latext = formula.latex
            self.assertEqual(formex_string, et.tostring(formula.source))


if __name__ == '__main__':
    unittest.main()
