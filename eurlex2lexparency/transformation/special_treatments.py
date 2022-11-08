import sys
import re
from lxml import etree as et
from collections import defaultdict


def _treat_32003R0001(document: et.ElementBase):
    misref = re.compile("32003R0001/(?P<art>ART_8[12])")
    for anchor in document.xpath(".//a[@href]"):
        if misref.search(anchor.attrib["href"]) is not None:
            anchor.attrib["href"] = misref.sub("TFEU/\g<art>", anchor.attrib["href"])


# this has to go at the end!!
treat = defaultdict(lambda: identity)
treat.update(
    {
        name.replace("_treat_", ""): eval(name)
        for name in dir(sys.modules[__name__])
        if name.startswith("_treat_")
    }
)


def identity(x):
    return x
