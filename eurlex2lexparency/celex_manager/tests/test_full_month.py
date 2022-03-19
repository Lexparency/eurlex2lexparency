import unittest
from datetime import date

from eurlex2lexparency.utils.generics import FullMonth

successors = [
    (FullMonth(2010, 1), FullMonth(2010, 2)),
    (FullMonth(2010, 5), FullMonth(2010, 6)),
    (FullMonth(2010, 12), FullMonth(2011, 1)),
    (FullMonth(2010, 11), FullMonth(2010, 12)),
]

ultimos = [
    (FullMonth(2010, 1), date(2010, 1, 31)),
    (FullMonth(2010, 2), date(2010, 2, 28)),
    (FullMonth(2012, 2), date(2012, 2, 29)),
    (FullMonth(2012, 7), date(2012, 7, 31)),
    (FullMonth(2012, 9), date(2012, 9, 30)),
]


class TestFullMonth(unittest.TestCase):

    def test_next(self):
        for predecessor, follower in successors:
            self.assertEqual(predecessor.next(), follower)

    def test_previous(self):
        for predecessor, follower in successors:
            self.assertEqual(predecessor, follower.previous())

    def test_ultimo(self):
        for month, ultimo in ultimos:
            self.assertEqual(ultimo, month.ultimo)

    def test_instantiation(self):
        for month, ultimo in ultimos:
            self.assertEqual(month, FullMonth.instantiate(ultimo))
        for month, _ in ultimos:
            self.assertEqual(
                month,
                FullMonth.instantiate(
                    str(month.year) + str(month.month).zfill(2))
            )


if __name__ == '__main__':
    unittest.main()
