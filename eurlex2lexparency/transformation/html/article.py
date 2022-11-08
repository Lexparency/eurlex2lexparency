"""
Proposal for further splitting of the current structure:
  - the liap module should take bigger part in the nesting.
  - the TableElement class shall assist more in the unfolding of the pseudotables.
"""
from lxml import etree as et
from functools import reduce

from eurlex2lexparency.extraction import textify
from eurlex2lexparency.transformation.utils.liap import ListItemsAndPatterns
from eurlex2lexparency.utils import xtml
from ..generic.article import Article as AbstractArticle
from .htmltable import HtmlTable


class Article(AbstractArticle):
    """ " This class is responsible for the transformations on article level"""

    TEST = False

    def __init__(
        self,
        element: et.ElementBase,
        itemization_type,
        language,
        logger=None,
        transform=True,
    ):
        """
        :param element: lxml.etree.Element
        :param itemization_type: string ('tabled' or 'flat')
        :param language: str
        """
        if logger is None:
            super().__init__(element, language)
        else:
            super().__init__(element, language, logger)
        self.itemization_type = itemization_type
        self.liap = ListItemsAndPatterns(
            self.language, "eu", known_firsts=(itemization_type == "tabled")
        )
        if transform:
            # Cumbersome way of transforming self.source,
            # in order to make use of the rollback decorator.
            if not self.TEST:
                xtml.rollback_on(Exception, logger)(lambda _: self.transform())(
                    self.source
                )
            else:
                self.transform()
            self._finalize()  # Needs to be performed. No excuse.

    def transform(self):
        if self.itemization_type == "tabled":
            self._nest_nump()
            self._unfold_pseudo_tables()
            self._wrap_list_items()
            self._cleanse_document()
        elif self.itemization_type == "flat":
            self._convert_point_k_items()
            self._unfold_pseudo_tables()
            self._aggregate_items()
            self._item_nesting()
        else:
            raise NotImplementedError(
                "It seems like a new type of raw itemization was found."
            )

    @staticmethod
    def _nest_all_siblings(leader: et.ElementBase):
        """To be used for Proposals"""
        cls = leader.attrib["class"]
        siblings = [leader]
        for s in leader.itersiblings():
            if s.tag != leader.tag or s.attrib["class"] != cls:
                break
            siblings.append(s)
        ol = et.Element("ol")
        leader.addprevious(ol)
        for s in siblings:
            data_title = s.find('./span[@class="num"]')
            s.attrib["data-title"] = data_title.text.strip()
            s.attrib.pop("class")
            s.tag = "li"
            xtml.remove(data_title)
            ol.append(s)
        return ol

    def _convert_point_k_items(self):
        for depth in "543210":
            for k in range(20):
                first = self.source.find(f'.//p[@class="li Point{depth}"]')
                if first is None:
                    break
                if first.find('./span[@class="num"]') is None:
                    continue
                ol = self._nest_all_siblings(first)
                if depth != 0:
                    pre = ol.getprevious()
                    if pre.tag == "p" and pre.attrib["class"].startswith("li Point"):
                        xtml.cut_append(pre, ol)
            else:  # if no break occurs
                raise RuntimeError("Had to iterate too often.")

    def _nest_nump(self):
        # nump-elements are put within <p> tags.
        # 1: group all elements and together that belong to the same
        aux_article = et.SubElement(
            self.source, "aux_article", id=self.source.attrib.get("id")
        )
        current_item = None
        for element in self.source.xpath("./*[not(self::aux_article)]"):
            if element.tag == "p":
                m = self.liap["nump"].item_pattern.search(element.text)
                if m is not None:
                    current_item = et.SubElement(
                        aux_article,
                        "li",
                        {"data-title": m.group(0).strip(), "class": "nump"},
                    )
                    element.text = self.liap["nump"].item_pattern.sub("", element.text)
            if current_item is not None:
                current_item.append(element)
            else:
                aux_article.append(element)
        xtml.unfold(aux_article)

    def _unfold_pseudo_tables(self):
        """Converts pseudo-tables in <body> into list items."""
        # remove dead columns from pseudo tables
        for table in self.source.xpath('.//table[not(@class="table")]'):
            tmp_table = HtmlTable(table)
            if tmp_table.is_column_empty(0):
                tmp_table.remove_column(0)
        relevant_tables = []
        for table in self.source.xpath('.//table[not(@class="table")]'):
            table_handler = HtmlTable(table)
            if table_handler.count_columns() == 2:
                if table_handler.count_rows() == 1:
                    if self.liap.list_label_generic.match(
                        textify(table_handler.body[0][0])
                    ):
                        relevant_tables.append(table_handler)
                else:
                    self._conditionally_convert_to_ordered_list(table_handler)
            elif table_handler.is_equation_array():
                table_handler.convert_to_unnumbered_list()
                table_handler.table.attrib["class"] = "equation_array"
        xtml.concatenate_siblings(self.source, "ul", **{"class": "equation_array"})
        xtml.concatenate_siblings(self.source, "ol", **{"class": "numbr"})
        for table_handler in relevant_tables:
            table_handler.convert_pseudo_table_to_list_item()

    def _conditionally_convert_to_ordered_list(self, table):
        """Converts "table" to ordered list.

        :param table: utils.htmltable.HtmlTable (html table)
             table is checked if it is eligible for list conversion. If so ... convert it.
        """
        label_sequence = []
        for cell in table.body.xpath("./tr/td[1]"):  # selects first column (tested)
            label_sequence.append(textify(cell))
        label_types = set(
            reduce(
                lambda x, y: x | y,
                [tags for tags, inner in self.liap.get_list_item_tag(label_sequence)],
            )
        )
        if len(label_types) != 1:
            return  # 'condition' not fulfilled
        for row in table.body.xpath("./tr"):
            row.remove(row[0])
        table.convert_to_unnumbered_list(wise="row")
        table.table.tag = "ol"
        table.table.attrib["class"] = label_types.pop()
        for title, li in zip(label_sequence, table.table.xpath("./li")):
            li.attrib["data-title"] = title

    def _wrap_list_items(self):
        """Decorates subsequent list-items with <ol> tags
        and attributes the corresponding class name to them.
        """
        # First Step: Aggregate top-level itemization
        current_item = None
        for child in self.source.xpath("./*"):
            if child.tag == "li" and child.attrib.get("data-title") is not None:
                if (
                    self.liap.get_list_item_tag(child.attrib.get("data-title")).tags
                    != set()
                ):
                    current_item = child
            elif current_item is not None:
                current_item.append(child)
        first_items = []
        for item in self.source.xpath(".//li[not(parent::ol) and not(parent::ul)]"):
            predecessors = [el.tag for el in item.itersiblings(preceding=True)]
            if not predecessors:
                first_items.append(item)
            elif predecessors[0] != "li":
                first_items.append(item)
        for item in first_items:
            # insertion of <ol>/<ul> element at the place of the first <li> element
            parent = item.getparent()
            css_class = self.liap.get_list_item_tag(
                item.attrib["data-title"]
            ).tags.pop()
            html_tag = "ol" if css_class != "dash" else "ul"
            inserted_list = et.Element(html_tag, attrib={"class": css_class})
            parent.insert(parent.index(item), inserted_list)
            inserted_list.append(item)
            # iteration over siblings of <list>, since item has no siblings any more:
            for sibling in inserted_list.itersiblings():
                if sibling.tag != "li":
                    break
                # this insertion actually replaces the element "sibling"
                inserted_list.append(sibling)

    def _recital(self):
        super()._recital()
        for recital in self.source.xpath('//li[@class="lxp-recital"]'):
            try:
                il = recital[0]
            except IndexError:
                continue
            if (
                il.tag == "span"
                and il.attrib.get("class") == "num"
                and il.text == recital.attrib.get("data-title")
            ):
                xtml.remove(il)

    def _cleanse_document(self, remove_ids=False):
        for paragraph in self.source.xpath(
            './/p[@class="ti-tbl"]'
        ):  # customize table captions
            if len(paragraph) == 1:
                if paragraph[0].tag == "span":
                    xtml.unfold(paragraph[0])
                    paragraph.attrib["class"] = "table-caption"
        for table in self.source.xpath(".//table"):
            table_handler = HtmlTable(table)
            table_handler.convert_hidden_list_to_list()
            if table_handler.single_celled:
                table_handler.unfold()
        for descendant in self.source.xpath(
            ".//li | .//td"
        ):  # Unfold first paragraph of table and list-item
            if len(descendant) and xtml.is_negligible(descendant.text):
                if descendant[0].tag == "p":
                    xtml.unfold(descendant[0])
        for descendant in self.source.xpath(".//table | .//col | .//tr | .//td"):
            for key, value in descendant.attrib.items():
                if (
                    key == "width"
                    or (key == "class" and descendant.tag == "table")
                    or (key.endswith("span") and value != "1")
                ):
                    continue
                descendant.attrib.pop(key)
        for anchor in self.source.xpath(".//a[@class]"):
            anchor.attrib.pop("class")
            if remove_ids and anchor.attrib.get("id") is not None:
                anchor.attrib.pop("id")
        for class_, tag in (("bold", "b"), ("italic", "i")):
            for bold_element in self.source.xpath(
                './/span[@class="{}"]'.format(class_)
            ):
                bold_element.tag = tag
                bold_element.attrib.pop("class")
        for footnote_anchor in self.source.xpath(".//a"):
            if footnote_anchor.attrib.get("shape") == "rect":
                footnote_anchor.attrib.pop("shape")
            footnote_label = footnote_anchor.xpath('./span[@class="super"]')
            if not len(footnote_label):
                continue
            footnote_label = footnote_label[0]
            xtml.unfold(footnote_label)
            footnote_anchor.insert(0, et.Element("sup"))
            footnote_anchor[0].text = footnote_anchor.text
            footnote_anchor.text = None

    def _aggregate_items(self):
        if self.id.startswith("ANX_"):
            return
        active_item = None
        for paragraph in self.source.xpath("*"):
            if paragraph.tag == "p":
                line_content = textify(paragraph, with_tail=False)
                m = self.liap.list_label_generic.search(line_content)
                if m is not None:
                    paragraph.tag = "li"
                    paragraph.attrib["data-title"] = m.group(0)
                    paragraph.attrib["class"] = self.liap.get_list_item_tag(
                        m.group(0)
                    ).tags.pop()
                    active_item = paragraph
                    continue
            if active_item is not None:
                active_item.append(paragraph)
        for paragraph in self.source.xpath("li"):
            # Handling of None-classes (a pain in the neck)
            if paragraph.attrib["class"] != "None":
                continue
            if paragraph.attrib.get("data-title") in ("(i)", "i)"):
                if paragraph.getnext() is not None:
                    if paragraph.getnext().attrib.get("data-title") in ("(ii)", "ii)"):
                        paragraph.attrib["class"] = "roman"
                    else:  # assumes that nobody would start an item-list with a single item.
                        paragraph.attrib["class"] = "alpha"
                else:
                    paragraph.attrib["class"] = "alpha"
            elif paragraph.attrib.get("data-title") in ["(v)", "(x)", "v)", "x)"]:
                paragraph.attrib["class"] = paragraph.getprevious().attrib["class"]

    def _item_nesting(self):
        """
        for each Article:
         - get first item
         - insert <ol> element in front of first item
         - append subsequent elements to active element
        """
        first_item = self.source.find("li")
        if first_item is None:
            return
        current_element = et.Element("ol", {"class": first_item.attrib.get("class")})
        self.source.insert(self.source.index(first_item), current_element)
        list_stack = [current_element]
        class_stack = [current_element.attrib.get("class")]
        for list_item in self.source.xpath("li"):
            current_class = list_item.attrib["class"]
            if current_class in class_stack:
                index = class_stack.index(current_class)
                class_stack = class_stack[: index + 1]
                list_stack = list_stack[: index + 1]
                list_stack[-1].append(list_item)
            else:
                class_stack.append(current_class)
                list_type = "ul" if current_class == "dash" else "ol"
                new_list = et.SubElement(
                    list_stack[-1][-1], list_type, {"class": current_class}
                )
                list_stack.append(new_list)
                list_stack[-1].append(list_item)
        for list_item in self.source.xpath("descendant::li[@data-title]"):
            list_item.text = list_item.text.replace(
                list_item.attrib["data-title"], "", 1
            )
            try:
                list_item.attrib.pop("class")
            except KeyError:
                pass
