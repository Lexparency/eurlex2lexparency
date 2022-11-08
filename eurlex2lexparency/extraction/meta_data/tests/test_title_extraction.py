import unittest

from lexref import Reflector

from eurlex2lexparency.extraction.meta_data.title_parsing import TitleParser
from datetime import date

in_2_out_en = [
    (
        "REGULATION (EU) No 575/2013 OF THE EUROPEAN PARLIAMENT "
        "AND OF THE COUNCIL of 26 June 2013 "
        "on prudential requirements for credit institutions and "
        "investment firms and amending Regulation (EU) No 648/2012",
        {
            "id_human": "Regulation (EU) No 575/2013",
            "title_essence": "On prudential requirements "
            "for credit institutions and investment firms",
            "date_document": date(2013, 6, 26),
            "amends": ["32012R0648"],
            "repeals": [],
        },
    ),
    (
        "Directive 2009/111/EC of the European Parliament and "
        "of the Council of 16 September 2009 "
        "amending Directives 2006/48/EC, 2006/49/EC and 2007/64/EC "
        "as regards banks affiliated to central institutions, "
        "certain own funds items, large exposures, supervisory "
        "arrangements, and crisis management (Text with EEA relevance)",
        {
            "id_human": "Directive 2009/111/EC",
            "date_document": date(2009, 9, 16),
            "amends": ["32006L0048", "32006L0049", "32007L0064"],
            "repeals": [],
        },
    ),
    (
        "Seventh Commission Directive 76/372/EEC of 1 March 1976 establishing "
        "Community methods of analysis for the official control of feedingstuffs",
        {
            "id_human": "Directive 76/372/EEC",
            "title_essence": "Establishing Community methods of analysis for the "
            "official control of feedingstuffs",
            "date_document": date(1976, 3, 1),
            "amends": [],
            "repeals": [],
        },
    ),
    (
        "REGULATION (EU) No 575/2013 of 26 June 2013 on prudential requirements for credit "
        "institutions and investment firms and amending Regulations (EU) No 648/2012 "
        "and (EC) No 33/2001 and repealing Directive 1922/22/EU",
        {
            "id_human": "Regulation (EU) No 575/2013",
            "title_essence": "On prudential requirements for "
            "credit institutions and investment firms",
            "date_document": date(2013, 6, 26),
            "amends": ["32012R0648", "32001R0033"],
            "repeals": ["31922L0022"],
        },
    ),
    (
        "Directive (EU) 2015/2366 of the European Parliament and of the Council "
        "of 25 November 2015 on payment services in the internal market, "
        "amending Directives 2002/65/EC, 2009/110/EC and 2013/36/EU and "
        "Regulation (EU) No 1093/2010, and repealing Directive 2007/64/EC "
        "(Text with EEA relevance)",
        {
            "id_human": "Directive (EU) 2015/2366",
            "title_essence": "On payment services in the internal market",
            "date_document": date(2015, 11, 25),
            "amends": ["32002L0065", "32009L0110", "32013L0036", "32010R1093"],
            "repeals": [
                "32007L0064",
            ],
        },
    ),
    (
        "Commission Directive (EU) 2015/1787 of 6 October 2015 "
        "on the quality of water intended for human consumption"
        ", amending Annex II to Council Directive 98/83/EC ",
        {
            "id_human": "Directive (EU) 2015/1787",
            "title_essence": "On the quality of water intended for human consumption",
            "date_document": date(2015, 10, 6),
            "amends": ["31998L0083"],
            "repeals": [],
        },
    ),
    (
        "Commission Directive (EU) 2015/1787 of 6 October 2015 "
        "on the quality of water intended for human consumption"
        ", amending Annexes II and III to Council Directive 98/83/EC ",
        {
            "id_human": "Directive (EU) 2015/1787",
            "title_essence": "On the quality of water intended for human consumption",
            "date_document": date(2015, 10, 6),
            "amends": ["31998L0083"],
            "repeals": [],
        },
    ),
    (
        "Commission Directive (EU) 2015/1787 of 6 October 2015 "
        "amending Annexes II and III to Council Directive 98/83/EC "
        "on the quality of water intended for human consumption",
        {
            "id_human": "Directive (EU) 2015/1787",
            # 'title_essence':
            #     'On the quality of water intended for human consumption',
            # TODO: Improve title parser to recognize essence in this case
            "date_document": date(2015, 10, 6),
            "amends": ["31998L0083"],
            "repeals": [],
        },
    ),
    (
        "Directive (EU) 2016/680 of the European Parliament and of the "
        "Council of 27 April 2016 on the protection of natural persons with "
        "regard to the processing of personal data by competent authorities "
        "for the purposes of the prevention, investigation, detection or "
        "prosecution of criminal offences or the execution of criminal "
        "penalties, and on the free movement of such data, and repealing "
        "Council Framework Decision 2008/977/JHA",
        {
            "id_human": "Directive (EU) 2016/680",
            "title_essence": "On the protection of natural persons with regard "
            "to the processing of personal data by competent "
            "authorities for the purposes of the prevention, "
            "investigation, detection or prosecution of "
            "criminal offences or the execution of criminal "
            "penalties, and on the free movement of such data",
            "date_document": date(2016, 4, 27),
            "amends": [],
            "repeals": ["32008F0977"],
        },
    ),
    # (
    #     'Directive (EU) 2015/1535 of the European Parliament and of the '
    #     'Council of 9 September 2015 laying down a procedure for the provision '
    #     'of information in the field of technical regulations and of rules on '
    #     'Information Society services (Text with EEA relevance)',
    #     {
    #         'id_human': 'Directive (EU) 2015/1535',
    #         'title_essence': "Laying down a procedure for the provision of "
    #                          "information in the field of technical "
    #                          "regulations and of rules on Information Society "
    #                          "services",
    #         'date_document': date(2015, 9, 9),
    #         'amends': [],
    #         'repeals': [],
    #     }
    # )
]

in_2_out_es = [
    (
        "Propuesta de REGLAMENTO DEL PARLAMENTO EUROPEO Y DEL CONSEJO POR EL "
        "QUE SE ESTABLECEN NORMAS ARMONIZADAS EN MATERIA DE INTELIGENCIA "
        "ARTIFICIAL (LEY DE INTELIGENCIA ARTIFICIAL) Y SE MODIFICAN "
        "DETERMINADOS ACTOS LEGISLATIVOS DE LA UNIÓN",
        {
            "title_essence": "Propuesta de REGLAMENTO DEL PARLAMENTO EUROPEO Y "
            "DEL CONSEJO POR EL QUE SE ESTABLECEN NORMAS "
            "ARMONIZADAS EN MATERIA DE INTELIGENCIA ARTIFICIAL "
            "(LEY DE INTELIGENCIA ARTIFICIAL)",
            "amends": [],
            "repeals": [],
        },
    ),
]


class TestTitleParser(unittest.TestCase):
    def test_parser_en(self):
        Reflector.reset()
        parser = TitleParser("EN")
        for title, data in in_2_out_en:
            self.assertEqual(data, parser(title))

    def test_parser_es(self):
        Reflector.reset()
        parser = TitleParser("ES")
        for title, data in in_2_out_es:
            self.assertEqual(data, parser(title))


if __name__ == "__main__":
    unittest.main()
