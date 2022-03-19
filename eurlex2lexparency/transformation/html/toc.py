from lxml import etree as et
from typing import Callable, Iterator
from anytree import NodeMixin, LevelOrderIter, RenderTree, PreOrderIter

from eurlex2lexparency.transformation.utils.generics import HeadingAnalyzer


class CorruptContentsTable(Exception):
    pass


class SkeletonNode(NodeMixin):

    def __init__(
            self,
            axis: str,
            value: str or None,
            element: et.ElementBase = None,
            parent=None
    ):
        self.std_axis = axis
        self.value = value
        self.element = element
        self.parent = parent

    @property
    def id(self):
        return self.element.attrib.get('id')

    @id.setter
    def id(self, value: str):
        self.element.attrib['id'] = value

    @property
    def standardized_ordinate(self):
        if self.value is None:
            return self.std_axis
        return '{}_{}'.format(self.std_axis, self.value)

    @property
    def type(self) -> str:
        if self.std_axis == 'toc':
            return 'container'
        return self.element.attrib['class'].replace('lxp-', '')

    @type.setter
    def type(self, value: str):
        self.element.attrib['class'] = 'lxp-' + value

    def __repr__(self):
        return "{}[{}]".format(
            self.type,
            self.id or self.standardized_ordinate
        )

    def __str__(self):
        return str(RenderTree(self))

    @classmethod
    def create(cls, std_axis, value, type_):
        return cls(
            std_axis,
            value,
            et.SubElement(
                et.Element(
                    'div',
                    attrib={
                        'class': f'lxp-{type_}'
                    }
                ),
                'div',
                attrib={
                    'class': 'lxp-heading',
                }
            ).getparent()
        )

    @classmethod
    def annex(cls):
        anx = cls.create('ANX', None, 'container')
        et.SubElement(anx.element[0], 'h1', attrib={'class': 'lxp-ordinate'})\
            .text = 'ANNEX'
        return anx


class TableOfContents:

    def __init__(self, body: et.ElementBase):
        self.root = SkeletonNode('toc', None, body)
        self.root.id = 'toc'
        self._flat_node_list = []
        self._nested = False

    def detach_container(self):
        for node in self.iter_nodes():
            if node == self.root:
                continue
            if node.type == 'container':
                try:
                    node.element.getparent().remove(node.element)
                except AttributeError:
                    # Annex container may be introduced by the nesting
                    if node.standardized_ordinate != 'ANX':
                        raise

    def iter_nodes(self) -> Iterator[SkeletonNode]:
        return LevelOrderIter(self.root)

    def iter_leaves(self) -> Iterator[SkeletonNode]:
        for node in PreOrderIter(self.root):
            if node.type == 'article':
                yield node

    def iter_container(self) -> Iterator[SkeletonNode]:
        for node in PreOrderIter(self.root):
            if node.type == 'container':
                yield node

    def _get_latest_parent(self, sought_axis, starting_point=None):
        current_element = starting_point or self.root
        parent = None
        while current_element.std_axis != sought_axis:
            # this step could use reversed iteration and the path
            try:
                current_element = current_element.children[-1]
            except IndexError:
                parent = current_element
                break
            if current_element.std_axis == sought_axis:
                parent = current_element.parent
        if parent.type == 'article' and starting_point is None:
            # TODO: In the future, whether or nor a ToC item is a sub-item
            #     of another one should be recognized, using the information
            #     whether or not there is a 'body' between the headings.
            return parent.parent
        return parent

    def nest(self):
        if self._nested:
            return
        annex = SkeletonNode.annex()
        for node in self._flat_node_list:
            if node.std_axis.split('_')[0] == 'ANX':
                if annex.parent is None:
                    annex.parent = self.root
                node.parent = annex
            elif annex.parent is not None and node.type.endswith('container'):
                node.parent = self._get_latest_parent(
                    node.std_axis,
                    starting_point=annex.children[-1]
                )
            else:
                node.parent = self._get_latest_parent(node.std_axis)
        if len(annex.children) == 1:
            # rolling back container creation for the case of a single annex
            annex.children[0].parent = self.root
            annex.parent = None
        elif len(annex.children) > 1:  # attach annex to underlying html document.
            annex.children[0].element.addprevious(annex.element)
        self.leaves_and_container(self.root)
        self.aggregate_ids()
        self._nested = True

    def leaves_and_container(self, node: SkeletonNode, left=False):
        """ Assign final tag to each inner node
        :param node:
            Node whose sub-nodes shall be assigned with the final tag.
        :param left: bool
            Indicates whether current node is (sub-) element of a Leave node.
        """
        for child in node.children:
            if child.std_axis == 'CNT_ANX':
                self.leaves_and_container(child)
            elif child.type == 'container':
                if left:
                    child.type = 'sub-container'
                self.leaves_and_container(child, left)
            elif child.type == 'article':
                self.leaves_and_container(child, left=True)
            elif child.type == 'sub-container':
                self.leaves_and_container(child, left)

    def aggregate_ids(self):
        self.root.id = self.root.std_axis
        for node in self.iter_nodes():
            if node == self.root:
                continue
            if node.type in ('container', 'sub-container'):
                node.id = node.parent.id + '-' + node.standardized_ordinate
            else:
                node.id = node.standardized_ordinate

    def attach(self, element: et.ElementBase):
        """
        Note: kwargs itself could contain a tag keyword.
        Therefore, in order to make this class mor stable, the "tag"
        parameter is protected with an underscore.
        """
        if self._nested:
            raise RuntimeError("Trying to attach after finalization")
        ordinate = element.attrib.pop('standardized-ordinate')
        try:
            axis, value = ordinate.split('_')
        except ValueError:
            axis, value = ordinate, None
        self._flat_node_list.append(SkeletonNode(axis, value, element))

    def transpose_nesting(self):
        """ At this stage the nesting of the elements is only done
            virtually on the anytree nodes level. Not for the xml-elments.
        """
        for node in self.iter_nodes():
            if node == self.root or node.parent == self.root:
                continue
            node.parent.element.append(node.element)

    @classmethod
    def collect_from(cls, body: et.ElementBase):
        """
        Constructs contents table from header elements, found in 'body'.
        Removes header of container elements.
        Assumes, that header elements have been marked by an instance
        of NodeMarker.

        :param body: Body of the document to be parsed.
        """
        toc = cls(body)
        classes = ['lxp-container', 'lxp-article', 'lxp-sub-container']
        for element in body.xpath('|'.join(map('./*[@class="{}"]'.format, classes))):
            toc.attach(element)
            if element.attrib.get('class') in ('lxp-article', 'lxp-sub-container'):
                for sibling in list(element.itersiblings()):
                    if sibling.attrib.get('class') in classes:
                        break
                    element.append(sibling)
        toc.nest()
        toc.transpose_nesting()

    def __str__(self):
        if self._nested:
            return str(self.root)
        else:  # to avoid strange interactions when debugging.
            return str(self._flat_node_list)


class NodeMarker:

    def __init__(
            self,
            heading_title_eligibility: Callable[[et.ElementBase, str], float],
            heading_ordinate_eligibility: Callable[[et.ElementBase], bool],
            textify: Callable[[et.ElementBase], str],
            language='EN',
            domain='eu'
    ):
        """
        Function to detect and label (with further attributes) section
        and article header.

        :param heading_title_eligibility:
            Function(et.ElementBase, str) -> float
            Returns score that element could be heading title
        :param heading_ordinate_eligibility: Function(et.ElementBase) -> bool
        :param textify: Function(et.ElementBase) -> str
            should strip annotations
        :param language: str
            E.g. 'EN', 'DE', 'ES'
        :param domain: str
            E.g. 'eu'
        """
        self.language = language
        self.domain = domain
        self.heading_analyzer = HeadingAnalyzer(self.language)
        self.heading_ordinate_eligibility = heading_ordinate_eligibility
        self.heading_title_eligibility = heading_title_eligibility
        self.textify = textify

    def __call__(
            self,
            before: et.ElementBase,
            center: et.ElementBase,
            after: et.ElementBase
    ):
        if not self.heading_ordinate_eligibility(center) or after is None:
            return
        center_text = self.textify(center)
        try:
            co, ordinate, title = self.heading_analyzer(center_text)
        except ValueError:
            return
        if co.axis in ('PAR', 'LTR', 'NUM', 'DIGIT',
                       'SUBPAR', 'REC', 'PT', 'PG'):
            return
        # End: recognition of headings
        if not (before.tag == 'div'
                and before.attrib.get('class') == 'lxp-container'):
            pre_score = self.heading_title_eligibility(before, co.role.name)
        else:  # before is title of a previous heading element.
            pre_score = 0
        post_score = self.heading_title_eligibility(after, co.role.name)
        if title is None:
            if max(pre_score, post_score) != 0:
                title_element = before if pre_score > post_score else after
                title_element.attrib['class'] = 'lxp-title'
                title_element.tag = 'h2'
            else:
                title_element = None
        else:
            # case: title is contained in same element with ordinate
            #   (axis and value)
            center.addnext(et.Element('h2'))
            title_element = center.getnext()
            title_element.text = title
        center.tag = 'h1'
        center.attrib['class'] = 'lxp-ordinate'
        center.addnext(et.Element('div', attrib={'class': 'lxp-heading'}))
        heading = center.getnext()
        heading.append(center)
        if title_element is not None:
            heading.append(title_element)
        role = 'leaf' if co.axis == 'ANX' else co.role.name
        heading.addnext(et.Element(
            'article' if role == 'leaf' else 'div',
            attrib={
                'class':
                    'lxp-{}'.format('article' if role == 'leaf' else co.role.name),
                'standardized-ordinate': co.collated}))
        node_element = heading.getnext()
        node_element.append(heading)
