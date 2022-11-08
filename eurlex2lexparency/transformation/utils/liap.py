"""
"""
import re
from collections import namedtuple
from functools import lru_cache

from lexref.model import Value

__all__ = ["ListItemsAndPatterns"]


romans_pattern = Value.tag_2_pattern("EN")["ROM_L"].pattern.strip("b\\()")


_eur_lex_item_patterns_en = {  # key: (itemization-character-pattern, ordered [bool], first two items, decorations)
    # TODO: Amendments could cause Itemizations of the type "5a.  ". Keep that in mind and see if / how the code
    # TODO:   can cope with that.
    "nump": (
        re.compile(r"^[1-9][0-9]{,3}\." + chr(160) + "{,3}", flags=re.UNICODE),
        True,
        ("1", "2"),
        "(). " + chr(160),
    ),
    "numpt": (
        re.compile(r"^[0-9]{1,3}\.?(?!([0-9/();]| of))"),
        True,  # TODO: This pattern does not belong here!
        ("1", "2"),
        ".",
    ),  # TODO:    => get rid of it!
    "numbr": (re.compile(r"^\([0-9]{1,3}\)"), True, ("1", "2"), "()"),  # 2
    "alpha": (re.compile(r"^\([a-z]\)"), True, ("a", "b"), "()"),  # 3
    "roman": (re.compile(r"^\((" + romans_pattern + r")\)"), True, ("i", "ii"), "()"),
    "dash": (
        re.compile("^(&mdash;|" + chr(8212) + ")", flags=re.UNICODE),
        False,
        None,
        None,
    ),
}

_eur_lex_item_patterns_es = {  # key: (itemization-character-pattern, ordered [bool], first two items, decorations)
    "nump": (
        re.compile(r"^[1-9][0-9]{,3}\." + chr(160) + "{,3}", flags=re.UNICODE),
        True,
        ("1", "2"),
        "(). " + chr(160),
    ),
    "numpt": (
        re.compile(r"^[0-9]{1,3}\.?(?!([0-9/();]| de))"),
        True,
        # TODO: This pattern does not belong here!
        ("1", "2"),
        ".",
    ),  # TODO:    => get rid of it!
    "numbr": (re.compile(r"^\([0-9]{1,3}\)"), True, ("1", "2"), "()"),  # 2
    "alpha": (re.compile(r"^\([a-z]\)"), True, ("a", "b"), "()"),  # 3
    "roman": (re.compile(r"^\((" + romans_pattern + r")\)"), True, ("i", "ii"), "()"),
    "dash": (
        re.compile("^(&mdash;|" + chr(8212) + ")", flags=re.UNICODE),
        False,
        None,
        None,
    ),
}

_eur_lex_item_patterns_de = {  # key: (itemization-character-pattern, ordered [bool], first two items, decorations)
    "nump": (re.compile(r"^\([0-9]{1,3}\)"), True, ("1", "2"), "()"),  # 2
    "alpha": (re.compile(r"^\([a-z]\)"), True, ("a", "b"), "()"),  # 3
    "roman": (re.compile(r"^\((" + romans_pattern + r")\)"), True, ("i", "ii"), "()"),
    "dash": (
        re.compile("^(&mdash;|" + chr(8212) + ")", flags=re.UNICODE),
        False,
        None,
        None,
    ),
}

_eur_lex_item_patterns_hierarchy = ["nump", "numpt", "numbr", "alpha", "roman", "dash"]


class ListItemPattern:

    FirstSecond = namedtuple("FirstSecond", ["first", "second"])

    def __init__(
        self,
        tag,  # Tag is used as CSS class on the surface
        item_pattern,
        ordered,
        first_two_items,
        decoration,
    ):
        self.item_pattern = item_pattern
        self.tag = tag
        self.ordered = ordered
        self.first_two_items = (
            None if first_two_items is None else self.FirstSecond(*first_two_items)
        )
        self.decoration = decoration

    @classmethod
    @lru_cache()
    def create(
        cls,
        tag,  # Tag is used as CSS class on the surface
        item_pattern,
        ordered,
        first_two_items,
        decoration,
    ):
        return cls(tag, item_pattern, ordered, first_two_items, decoration)


@lru_cache()
class ListItemsAndPatterns:

    TagProposal = namedtuple("TagProposal", ["tags", "inner"])

    def __init__(self, language, document_domain, known_firsts=False):
        if document_domain.lower() == "eu":
            try:
                _eur_lex_item_patterns = eval(
                    f"_eur_lex_item_patterns_{language.lower()}"
                )
            except NameError:
                raise NotImplementedError(
                    f"It seems that the time has come to implement "
                    f"language {language} for domain eu."
                )
            else:
                self.list_item_patterns = {
                    key: ListItemPattern.create(key, *value)
                    for key, value in _eur_lex_item_patterns.items()
                }
            self.known_firsts = known_firsts
            self.list_label_generic = re.compile(
                "^("
                + "|".join(
                    [
                        "(" + x.item_pattern.pattern.strip("^") + ")"
                        for x in self.list_item_patterns.values()
                    ]
                )
                + ")"
            )
            self.tag_hierarchy = _eur_lex_item_patterns_hierarchy
        else:
            raise NotImplementedError(
                f"It seems that the time has come to "
                f"implement domain {document_domain}"
            )

    def get_list_item_tag(self, arg, force_ambivalence_resolution=True):
        if type(arg) is str:
            if force_ambivalence_resolution:
                return self.get_list_item_tag([arg])[0]
            else:
                tag_candidates = set()
                inner = None
                for list_item_pattern in self.list_item_patterns.values():
                    m = list_item_pattern.item_pattern.match(arg)
                    if m is not None:
                        if inner is None:
                            inner = m.group(0).strip(list_item_pattern.decoration)
                        elif inner != m.group(0).strip(list_item_pattern.decoration):
                            raise RuntimeError(
                                "Unexpected ambivalence (type 0) "
                                "within ListItemsHandler"
                            )
                        tag_candidates |= {list_item_pattern.tag}
                return self.TagProposal(tag_candidates, inner)
        elif type(arg) is list:
            tags_list = [
                self.get_list_item_tag(it, force_ambivalence_resolution=False)
                for it in arg
            ]
            self._resolve_ambivalences(tags_list)
            return tags_list

    def __getitem__(self, item):
        return self.list_item_patterns[item]

    def _resolve_ambivalences(self, tag_candidates_list):
        """
        1. Identify
        :param tag_candidates_list:
        :return:
        TODO: This routine works more or les fine. However, it does not
            really take into account all the context sensitivity that may arise.
            Furthermore, at least two of the test cases have no unique solution,
            but this routine simply chooses one possible solution. That is more
            than questionable. Furthermore, this routine, does not take into
            account the full nested structure of itemization, which would
            clearly help to make the outcome this task more more correct for
            all possible input cases.
        """

        def ambivalence_resolvable(tag_list):
            for tag_l in tag_list:
                for tag_r in tag_list:
                    if tag_r > tag_l:
                        if self[tag_l] != self[tag_r]:
                            return True
            return False

        # TODO: distinction between two types of ambivalence:
        ambivalent_cases = [
            k
            for k, (tags, inner) in enumerate(tag_candidates_list)
            if ambivalence_resolvable(tags)
        ]
        # TODO: Not resolvable cases must be handled via the hierarchy
        for k in ambivalent_cases:
            case = tag_candidates_list[k]
            if k < len(tag_candidates_list) - 1:
                subsequent = tag_candidates_list[k + 1]
                if k + 1 not in ambivalent_cases:
                    # If the adjacent item is not ambivalent. The tag of the subsequent is it
                    if (
                        subsequent.tags.issubset(case.tags)
                        and self[subsequent.tags.copy().pop()].first_two_items.first
                        != subsequent.inner
                    ):
                        tag_candidates_list[k] = self.TagProposal(
                            subsequent.tags, case.inner
                        )
                        continue
            if k > 0:  # No successor of case but a precedent (of course)
                preceding = tag_candidates_list[k - 1]
                if k - 1 not in ambivalent_cases:
                    if preceding.tags.issubset(
                        case.tags
                    ):  # and case is not first with respect to preceding tag
                        if (
                            self[preceding.tags.copy().pop()].first_two_items.first
                            != case.inner
                        ):
                            tag_candidates_list[k] = self.TagProposal(
                                preceding.tags, case.inner
                            )
                            continue
                        else:
                            case.tags.remove(preceding.tags.copy().pop())
                            continue
            for tag in self.tag_hierarchy:  # map to hierarchy and take the first one.
                if tag in case.tags:
                    tag_candidates_list[k] = self.TagProposal({tag}, case.inner)
                    continue
        if len([_ for _ in tag_candidates_list if len(_.tags) > 1]) > 0:
            self._resolve_ambivalences(tag_candidates_list)
