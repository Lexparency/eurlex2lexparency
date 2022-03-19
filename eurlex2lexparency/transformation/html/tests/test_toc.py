import unittest
from lxml import etree as et
import os
import re
from anytree import PreOrderIter
from typing import List
from copy import deepcopy

from eurlex2lexparency.transformation.html.toc import TableOfContents, SkeletonNode

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')


def id2ordinate(id_):
    ordinate = id_.split('-')[-1]
    try:
        axis, value = ordinate.split('_')
    except ValueError:
        axis, value = ordinate, None
    return axis, value


def nested2flat(nested: SkeletonNode) -> List[SkeletonNode]:
    result = [
        SkeletonNode.create(node.std_axis, node.value, node.type)
        for node in PreOrderIter(nested)
        if node.id != 'toc-ANX'
    ][1:]
    body = et.Element('body')
    for node in result:
        body.append(node.element)
    return result


def raw2skeleton(element: et.ElementBase) -> SkeletonNode:
    def append_children(parent: SkeletonNode):
        for child in parent.element.iterchildren():
            axis, value = id2ordinate(child.attrib['id'])
            append_children(SkeletonNode(axis, value, child, parent=parent))
    root = SkeletonNode('toc', None, element)
    append_children(root)
    return root


class TestTableOfContents(unittest.TestCase):

    file_pattern = re.compile(r'toc_(?P<key>[^.]+)\.xml')

    def setUp(self):
        self.tocs = dict()
        for file_name in os.listdir(DATA_PATH):
            m = self.file_pattern.match(file_name)
            if m is None:
                continue
            nested = raw2skeleton(
                et.ElementTree(file=os.path.join(DATA_PATH, file_name))
                .getroot()
            )
            flat = nested2flat(nested)
            self.tocs[m.group('key')] = (nested, flat)
        # For testing if the type-assignment (leaves_and_container) works
        self.tocs['32016R0679a2'] = deepcopy(self.tocs['32016R0679a1'])
        body = et.Element('body')
        for node in self.tocs['32016R0679a2'][1]:
            body.append(node.element)  # body element not captured by deepcopy
            if node.element.attrib.get('class') == 'lxp-sub-container':
                node.element.attrib['class'] = 'container'

    def test_toc_nesting(self):
        for key, (nested, flat) in self.tocs.items():
            toc = TableOfContents(et.Element('div', attrib={'id': 'toc'}))
            toc._flat_node_list = flat
            toc.nest()
            for expected, actual in zip(
                    str(nested).split('\n'),
                    str(toc.root).split('\n')
            ):
                self.assertEqual(expected, actual)


if __name__ == '__main__':
    unittest.main()
