import logging
from functools import wraps

from lxml import etree as et
import collections
from typing import List, Iterator


def is_negligible(in_text):
    """ " Checks if text or tail of XML element is either empty string or None
    Copied from the interface (doq).
    """
    if in_text is None:
        return True
    elif type(in_text) is str:
        if in_text.strip(chr(160) + " \t\n\r") == "":
            return True
        else:
            return False
    else:
        raise TypeError


def leader(in_element: et.ElementBase) -> et.ElementBase:
    candidate = in_element.getprevious()
    if candidate is not None:
        return candidate
    return in_element.getparent()


def get_lead(in_element: et.ElementBase) -> str:
    """Return value can also be None."""
    leader_ = in_element.getprevious()
    if leader_ is not None:
        return leader_.tail
    return in_element.getparent().text


def set_lead(self: et.ElementBase, text_tail):
    leader_ = self.getprevious()
    if leader_ is not None:
        leader_.tail = text_tail
    else:
        self.getparent().text = text_tail


def strip_subelements(element: et.ElementBase, sub_x_path: str) -> List[et.ElementBase]:
    """
    Strips off child elements of element and
    :param element: XML-Element to be modified
    :param sub_x_path: xpath fragment to indicate which child elements should be removed
    :return: list of removed elements
    """
    stripped = []
    for sub_element in element.xpath(sub_x_path):
        stripped.append(sub_element)
        sub_element.getparent().remove(sub_element)
    return stripped


def unfold(in_element, processing_instruction=False):
    """moves content of element to parent element,
        appends its tail to the tail of the final sub-element,
        finally removes element
    :param in_element:
    :param processing_instruction:
    """

    def member_to_text(member):
        return "" if member is None else member

    in_parent = in_element.getparent()
    first = in_parent.index(in_element) == 0
    if in_element.text is not None and not processing_instruction:
        if first:
            in_parent.text = member_to_text(in_parent.text) + in_element.text
        else:
            in_element.getprevious().tail = (
                member_to_text(in_element.getprevious().tail) + in_element.text
            )
        in_element.text = None
    if len(in_element) > 0:
        for sub_element in in_element.iterchildren(reversed=True):
            in_element.addnext(sub_element)
    else:
        if in_element.tail is not None:
            if first:
                in_parent.text = member_to_text(in_parent.text) + in_element.tail
            else:
                in_element.getprevious().tail = (
                    member_to_text(in_element.getprevious().tail) + in_element.tail
                )
    in_parent.remove(in_element)


def unfold_all(ultimate_parent: et, tags):
    for desc in ultimate_parent.xpath(".//*"):
        if desc.tag in tags:
            unfold(desc)


def remove(element: et.ElementBase, keep_tail=True):
    if keep_tail and element.tail not in (None, ""):
        if element.tail not in (None, ""):
            set_lead(element, (get_lead(element) or "") + element.tail)
    element.getparent().remove(element)


def flatten_by_paths(element: et.ElementBase, *paths):
    for sub_element in element.xpath(" | ".join(paths)):
        unfold(sub_element)


def analyze_attrib_frequency(in_element, attribute):
    """Counts frequencies of values of given attribute fields"""
    return collections.Counter(in_element.xpath("//@{}".format(attribute)))


def reunite(body, element_tag="p", class_list="doc-ti"):
    """Merges all adjacent elements that are of the same css-class"""
    if type(class_list) is str:
        class_list = [class_list]
    for _class in class_list:
        candidate_list = body.xpath(f'.//{element_tag}[@class="{_class}]"')
        group_list = []
        k = 0
        while k <= len(candidate_list) - 1:
            if candidate_list[k].getnext() == candidate_list[k + 1]:
                current_list = [k]
                for sibling in candidate_list[k].itersiblings(element_tag):
                    if sibling.attrib.get("class") != _class:
                        break
                    k += 1
                    current_list.append(k)
                group_list.append(current_list)
            k += 1
        for group in group_list:
            leader_ = group[0]
            for paragraph in group[1:]:
                # noinspection PyUnresolvedReferences
                leader_.append(paragraph)
                # noinspection PyTypeChecker
                unfold(paragraph)


def concatenate_siblings(element, tag, **attrib):
    predicates = [f'@{key}="{value}"' for key, value in attrib.items()]
    selector = "{}[{}]".format(tag, " and ".join(predicates)).replace("[]", "")
    # Find all elements that match the selector where its direct next neighbour
    # matches the same selector
    for candidate in element.xpath(".//{}".format(selector)):
        if candidate.tail is not None:
            if candidate.tail.strip() != "":
                continue
        next_ = candidate.getnext()
        if et.iselement(next_):
            if next_.xpath("self::{}".format(selector)):
                break
    else:
        return
    for sibling in candidate.xpath("following-sibling::*"):
        if sibling.xpath("self::{}".format(selector)):
            candidate.append(sibling)
            unfold(sibling)
        else:
            break
    concatenate_siblings(element, tag, **attrib)


def migrate_attributes(element, name, mapping):
    value = element.attrib.get(name, None)
    if value in mapping:
        element.attrib[name] = mapping[value]


def unfold_redundant_paragraphs(item, *tags):
    while (item.text or "").strip() == "" and len(item) > 0:
        if item[0].tag not in tags:
            break
        unfold(item[0])


def push(host: et.ElementBase, adoptee: et.ElementBase):
    """Makes a true insert to the very front of the host element."""
    text = host.text
    host.text = None
    if text is not None:
        adoptee.tail = (adoptee.tail or "") + " " + text
    host.insert(0, adoptee)


def cut_append(host: et.ElementBase, adoptee: et.ElementBase):
    """Appends the adoptee to the end of the host but leaves the adoptee's
    tail outside."""
    tail = adoptee.tail
    if tail is not None:
        if host.tail is not None:
            host.tail = tail + " " + host.tail
        else:
            host.tail = tail
    host.append(adoptee)


def subskeleton(element: et.Element) -> et.ElementBase:
    """For debugging"""
    proxy = et.Element(element.tag, dict(**element.attrib))
    for child in element.iterchildren():
        if isinstance(child.tag, str):
            proxy.append(subskeleton(child))
    return proxy


def iter_column(table: et.ElementBase, col: int) -> Iterator[et.ElementBase]:
    for row in table.xpath("./tr | ./*/tr"):
        yield row[col]


def iter_table_columns(table: et.ElementBase) -> Iterator[List[et.ElementBase]]:
    for col in range(1000):  # 1000 should be sufficient
        try:
            yield list(iter_column(table, col))
        except IndexError:
            break


def rollback_on(errors, logger: logging.Logger):
    def rollback_on_error(f):
        """Decorator for functions transforming an XML-Element (e).
        Performs a rollback on the element if anything fails.
        """

        @wraps(f)
        def wrapped(e: et.ElementBase, *args, **kwargs):
            ec = et.fromstring(et.tostring(e, with_tail=False))
            try:
                f(e, *args, **kwargs)
            except errors:  # rollback
                logger.error(f"Could not transform {ec.tag}, {ec.attrib}")
                for child in e.xpath("./*"):
                    e.remove(child)
                e.text = ec.text
                for child in ec.xpath("./*"):
                    e.append(child)
                for key in list(e.attrib):
                    e.attrib.pop(key)
                for key, value in ec.attrib.items():
                    e.attrib[key] = value

        return wrapped

    return rollback_on_error
