import re
from lxml import etree as et
from anytree import NodeMixin, RenderTree
from operator import attrgetter


class FormulaConversionError(Exception):
    pass


brace_map = {
    "<EXPR {'TYPE': 'BRACKET'}>": ('(', ')'),
    "<EXPR {'TYPE': 'BRACE'}>": (r'\{', r'\}'),
    "<EXPR {'TYPE': 'SQBRACKET'}>": (r'[', r']'),
    "<EXPR {'TYPE': 'BAR'}>": ('|', '|'),
}


latex_operators = {
    "<HT {'TYPE': 'BOLD'}>": r"\mathbf",
    "<HT {'TYPE': 'ITALIC'}>": r"\mathrm",
    "<OVERLINE>": r"\overline",
    "<IND {'LOC': 'SUP'}>": "^",
    "<IND {'LOC': 'OVER'}>": "^",
    "<IND {'LOC': 'UNDER'}>": "_",
    "<EXPONENT>": "^",
    "<OVER>": "^",
    "<IND {'LOC': 'SUB'}>": "_",
    "<IND>": "_",
    "<UNDER>": "_",
    "<FT {'TYPE': 'NUMBER'}>": "",
    "<FMT.VALUE": "",
    '<ROOT>': r'\sqrt',
}


simple_mapping = {
    'ln': r'\ln',
    'min': r'\min',
    'max': r'\max',
    'sin': r'\sin',
    'cos': r'\cos',
    'exp': r'\exp',
    "<OP.MATH {'TYPE': 'CARTPROD'}>": '\\times',
    "<OP.MATH {'TYPE': 'DIV'}>": '/',
    "<OP.MATH {'TYPE': 'MINUS'}>": '-',
    "<OP.MATH {'TYPE': 'MULT'}>": '\\cdot',
    "<OP.MATH {'TYPE': 'PLUS'}>": '+',
    "<OP.MATH {'TYPE': 'PLUSMINUS'}>": '\\pm',
    "<OP.CMP {'TYPE': 'EQ'}>": '=',
    "<OP.CMP {'TYPE': 'LT'}>": '<',
    "<OP.CMP {'TYPE': 'GT'}>": '>',
    "<OP.CMP {'TYPE': 'NE'}>": '\\ne',
    "<OP.CMP {'TYPE': 'LE'}>": '\\le',
    "<OP.CMP {'TYPE': 'GE'}>": '\\ge',
    "<OP.CMP {'TYPE': 'AP'}>": '\\approx',
    "<OP.CMP {'TYPE': 'EQV'}>": '\\equiv',
    "<SUM>": r'\sum',
}

special_characters = {
    # greeks
    chr(913): r"\Alpha",
    chr(914): r"\Beta",
    chr(915): r"\Gamma",
    chr(916): r"\Delta",
    chr(917): r"\Epsilon",
    chr(918): r"\Zeta",
    chr(919): r"\Eta",
    chr(920): r"\Theta",
    chr(921): r"\Iota",
    chr(922): r"\Kappa",
    chr(923): r"\Lambda",
    chr(924): r"\Mu",
    chr(925): r"\Nu",
    chr(926): r"\Xi",
    chr(927): r"\Omicron",
    chr(928): r"\Pi",
    chr(929): r"\Rho",
    chr(931): r"\Sigma",
    chr(932): r"\Tau",
    chr(933): r"\Upsilon",
    chr(934): r"\Phi",
    chr(935): r"\Chi",
    chr(936): r"\Psi",
    chr(937): r"\Omega",
    chr(945): r"\alpha",
    chr(946): r"\beta",
    chr(947): r"\gamma",
    chr(948): r"\delta",
    chr(949): r"\epsilon",
    chr(950): r"\zeta",
    chr(951): r"\eta",
    chr(952): r"\theta",
    chr(953): r"\iota",
    chr(954): r"\kappa",
    chr(955): r"\lambda",
    chr(956): r"\mu",
    chr(957): r"\nu",
    chr(958): r"\xi",
    chr(959): r"\omicron",
    chr(960): r"\pi",
    chr(961): r"\rho",
    # chr(962): r"ς",
    chr(963): r"\sigma",
    chr(964): r"\tau",
    chr(965): r"\upsilon",
    chr(966): r"\varphi",
    chr(967): r"\chi",
    chr(968): r"\psi",
    chr(969): r"\omega",
    # other special characters
    chr(903): r"\cdot",
    chr(8211): "-",
    chr(8212): "-",
    chr(8706): r'\partial',
    '%': r'\%',
    chr(215): r"\times",
    chr(8721): r"\sum",
    chr(8804): r"\le",
    chr(8805): r"\ge",
}


def urep(s):
    n = ord(s)
    return r'\u' + hex(n)[2:].upper().zfill(4)


simple_mapping.update(special_characters)


word_sequence_pattern = re.compile('^[a-z ]+$', flags=re.IGNORECASE)
abbreviation_pattern = re.compile('^[A-Z]{2,}$')


def tokenize_string(string: str):
    string = string.strip()
    if word_sequence_pattern.match(string):
        return [string]
    else:
        # Regex don't seem to work here.
        for clear_token in list(';:*/+-') + list(special_characters.keys()):
            string = string.replace(clear_token, '###{}###'.format(clear_token))
        return [
            token.strip() for token in string.split('###')
            if token.strip() not in (None, '')
        ]


class FormulaNodeParser(NodeMixin):

    def __init__(self, source, parent=None):
        self.parent = parent
        self.source = source
        if et.iselement(self.source):
            self._set_children_from_element(self.source)
        self.representation = repr(self)
        self.correct_nesting()

    def get_next(self):
        if self.parent is None:
            return None
        it = iter(self.parent.children)
        for node in it:
            if node is self:
                break
        try:
            return next(it)
        except StopIteration:
            return None

    @property
    def could_be_sum(self):
        """ Some summations are implemented using the greek letter "\Sigma" (literally).
        This property evaluates whether the present token should be converted to \sum in latex.
        This is a complex logic and would require testing
        :return: bool, indicating whether it makes sense to interpret the present token as summation symbol
        """
        if simple_mapping.get(self.representation) != r'\Sigma':
            return False
        next_sibling = self.get_next()
        if next_sibling is None:
            return False
        next_operator = latex_operators.get(next_sibling.representation)
        if next_operator == '_':
            return True
        if next_operator == '^':
            next_next_sibling = next_sibling.get_next()
            if next_next_sibling is None:
                return False
            next_next_operator = latex_operators.get(next_next_sibling.representation)
            if next_next_operator == '_':
                return True
        return False

    @property
    def latex(self):
        if self.representation in simple_mapping:
            if self.could_be_sum:
                return r'\sum'
            return simple_mapping[self.representation]
        if not self.complex_type:
            if ((word_sequence_pattern.match(self.representation) and len(self.representation) >= 3)
                or abbreviation_pattern.match(self.representation))\
                    and self.representation not in latex_operators:  # those are handled further down the road
                operator = r'\text' if ' ' in self.representation else r'\mathrm'
                return operator + '{{{}}}'.format(self.representation)
            return self.representation
        if self.representation == '<FRACTION>':
            return r'\frac{}{}'.format(*map(attrgetter('latex'), self.children))
        inner = ' '.join(child.latex for child in self.children)
        if self.representation in ('<EXPR>', '<DIVIDEND>', '<DIVISOR>'):
            return '{{{}}}'.format(inner)
        if self.representation in brace_map:
            if re.search(r'\\(frac|sum)\b', inner):
                # Adapt braces sizes if inner contains fractions
                braces = map(lambda a, b: ' '.join([a, b]), (r'\left', r'\right'), brace_map[self.representation])
            else:
                braces = brace_map[self.representation]
            return '{}{inner}{}'.format(*braces, inner=inner)
        if self.representation in latex_operators:
            operator = latex_operators[self.representation]
            if operator != '':
                if operator == r'\mathrm' and (inner.startswith(operator) or inner.startswith(r'\text')):
                    return inner
                return operator + '{{{}}}'.format(inner)
            else:
                return inner
        return inner

    def _set_children_from_element(self, source: et.ElementBase):
        """ Actually a tokenisation step. """
        if (source.tail or '').strip() != '':
            for token_string in tokenize_string(source.tail):
                FormulaNodeParser(token_string, parent=self.parent)
        if (source.text or '').strip() != '':
            for token_string in tokenize_string(source.text):
                FormulaNodeParser(token_string, parent=self)
        for child in source.iterchildren():
            FormulaNodeParser(child, parent=self)

    @property
    def complex_type(self):
        return et.iselement(self.source)

    def __repr__(self):
        if self.complex_type:
            return '<{} {}>'.format(self.source.tag, self.source.attrib).replace(' {}', '')
        return self.source.replace('\n', '').strip()

    def __str__(self):
        return str(RenderTree(self))

    def correct_nesting(self):
        """ In some versions of formex, the fractions within the formulas are expressed as
            <EXPR/><OVER/><EXPR/>
        """
        fractions = []
        roots = []
        for k, child in enumerate(self.children):
            if child.representation == '<OVER>' and k > 0 and len(child.children) == 0:
                child.representation = '<FRACTION>'
                fractions.append((self.children[k-1], child, self.children[k+1]))
            if child.representation == '<ROOT>' and len(child.children) == 0:
                roots.append((child, self.children[k+1]))
        for enumerator, dash, nominator in fractions:
            enumerator.parent = dash
            nominator.parent = dash
        for root, rootant in roots:
            rootant.parent = root


def formex_to_latex(formula: et.ElementBase):
    latex = FormulaNodeParser(formula).latex
    if formula.tag == 'FORMULA.S' or (formula.tag == 'FORMULA' and formula.attrib.pop('TYPE', None) == "OUTLINE"):
        tag = 'div'
        wrapper = ('$$', '$$')
    else:
        tag = 'span'
        wrapper = (r'\(', r'\)')
    for child in formula.iterchildren():
        formula.remove(child)
    formula.tag = tag
    formula.attrib['class'] = 'lxp-math'
    formula.text = '{}{text}{}'.format(*wrapper, text=latex)
    return formula
