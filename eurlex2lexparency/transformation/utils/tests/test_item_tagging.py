import json
import os
import unittest

from eurlex2lexparency.transformation.utils.liap import ListItemsAndPatterns

TagProposal = ListItemsAndPatterns.TagProposal


class TestItemTagging(unittest.TestCase):

    data_file_path = os.path.join(os.path.dirname(__file__),
                                  'item_label_sequences.json')

    def setUp(self):
        with open(self.data_file_path) as f:
            data = json.load(f)['challenges']
        self.data = [[TagProposal({d['axis']}, d['value']) for d in i['items']]
                     for i in data]

    def test(self):
        liap = ListItemsAndPatterns('EN', 'eu')
        for expected in self.data:
            raw = [f"({i.inner})" for i in expected]
            actual = liap.get_list_item_tag(raw)
            self.assertEqual(expected, actual)


if __name__ == '__main__':
    unittest.main()
