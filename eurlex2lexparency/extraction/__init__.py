from lxml import etree as et
import re


blanks = re.compile(r'[\s\n\r\t]+')


def textify(element: et.ElementBase, with_tail=True, simplify_blanks=False):
    """ copied from the interface part (doq)
        ATTENTION: The pretty-printing is necessary. Otherwise, the text-content
        of neighbouring h1 and h2 elements
        (as example) would be glued together.
    """
    if simplify_blanks:
        return blanks.sub(
            ' ',
            et.tostring(
                et.fromstring(
                    et.tostring(element, pretty_print=True, with_tail=with_tail)
                ),
                method='text', with_tail=with_tail, encoding='unicode'
            )
        ).strip()
    else:
        return et.tostring(element, method='text', encoding='unicode',
                           with_tail=with_tail).strip()
