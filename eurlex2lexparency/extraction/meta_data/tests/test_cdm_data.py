import json
import unittest
import datetime
import os
from lxml import etree as et
from eurlex2lexparency.extraction.meta_data.cdm_data import (
    TitlesRetriever,
    ActMetaData,
    Anchor,
)
from eurlex2lexparency.extraction.meta_data.handler import default

amd = ActMetaData(
    language="EN",
    amends={
        Anchor(
            href="/eu/32012R0648",
            text="Regulation (EU) No 648/2012",
            title="On OTC derivatives, central counterparties and trade "
            "repositories  Text with EEA relevance",
        )
    },
    based_on=Anchor(
        "/eu/TFEU", "TFEU", "Treaty on the Functioning of the European Union"
    ),
    cites={
        Anchor(
            href="/eu/32009R1060",
            text="Regulation (EC) No 1060/2009",
            title="On credit rating agencies (Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32009L0138",
            text="Directive 2009/138/EC",
            title="On the taking-up and pursuit of the business of Insurance "
            "and Reinsurance (Solvency II) (Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32004L0039",
            text="Directive 2004/39/EC",
            title="On markets in financial instruments",
        ),
        Anchor(
            href="/eu/32013L0036",
            text="Directive 2013/36/EU",
            title="On access to the activity of credit institutions and the "
            "prudential supervision of credit institutions and investment firms",
        ),
        Anchor(
            href="/eu/32006L0049",
            text="Directive 2006/49/EC",
            title="On the capital adequacy of investment firms and credit "
            "institutions (recast)",
        ),
        Anchor(
            href="/eu/31995L0046",
            text="Directive 95/46/EC",
            title="On the protection of individuals with regard to the "
            "processing of personal data and on the free movement of such data",
        ),
        Anchor(
            href="/eu/32009L0111",
            text="Directive 2009/111/EC",
            title="Directive 2009/111/EC of the European Parliament and of the "
            "Council of 16 September 2009 amending Directives 2006/48/EC, "
            "2006/49/EC and 2007/64/EC as regards banks affiliated to "
            "central institutions, certain own funds items, large "
            "exposures, supervisory arrangements, and crisis management "
            "(Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32003H0361",
            text="32003H0361",
            title="Concerning the definition of micro, small and medium-sized "
            "enterprises (Text with EEA relevance) "
            "(notified under document number C(2003) 1422)",
        ),
        Anchor(
            href="/eu/32011R0182",
            text="Regulation (EU) No 182/2011",
            title="Laying down the rules and general principles concerning "
            "mechanisms for control by Member States of the Commission’s "
            "exercise of implementing powers",
        ),
        Anchor(
            href="/eu/32002R1606",
            text="Regulation (EC) No 1606/2002",
            title="On the application of international accounting standards",
        ),
        Anchor(
            href="/eu/32011R1205",
            text="Regulation (EU) No 1205/2011",
            title="Commission Regulation (EU) No\xa01205/2011 of 22\xa0November "
            "2011 amending Regulation (EC) No\xa01126/2008 adopting "
            "certain international accounting standards in accordance "
            "with Regulation (EC) No\xa01606/2002 of the European "
            "Parliament and of the Council as regards International "
            "Financial Reporting Standard (IFRS) 7 Text with EEA relevance",
        ),
        Anchor(
            href="/eu/52012XX0619(01)",
            text="52012XX0619(01)",
            title="Opinion of the European Data Protection Supervisor on the "
            "Commission proposals for a Directive on the access to the "
            "activity of credit institutions and the prudential "
            "supervision of credit institutions and investment firms, and "
            "for a Regulation on prudential requirements for credit "
            "institutions and investment firms",
        ),
        Anchor(
            href="/eu/32013Y0425(01)",
            text="32013Y0425(01)",
            title="On funding of credit institutions (ESRB/2012/2)",
        ),
        Anchor(
            href="/eu/32007L0064",
            text="Directive 2007/64/EC",
            title="On payment services in the internal market",
        ),
        Anchor(
            href="/eu/32000L0012",
            text="Directive 2000/12/EC",
            title="Relating to the taking up and pursuit of the business of "
            "credit institutions",
        ),
        Anchor(
            href="/eu/31983L0349",
            text="Directive 83/349/EEC",
            title="Based on the Article 54 (3) (g) of the Treaty on "
            "consolidated accounts",
        ),
        Anchor(
            href="/eu/31993L0006",
            text="Directive 93/6/EEC",
            title="On the capital adequacy of investments firms and credit "
            "institutions",
        ),
        Anchor(
            href="/eu/32008R1126",
            text="Regulation (EC) No 1126/2008",
            title="Adopting certain international accounting standards in "
            "accordance with Regulation (EC) No 1606/2002 of the European "
            "Parliament and of the Council (Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32006L0048",
            text="Directive 2006/48/EC",
            title="Relating to the taking up and pursuit of the business of "
            "credit institutions (recast)   (Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32002L0087",
            text="Directive 2002/87/EC",
            title="On the supplementary supervision of credit institutions, "
            "insurance undertakings and investment firms in a financial "
            "conglomerate",
        ),
        Anchor(
            href="/eu/32004D0010",
            text="32004D0010",
            title="Establishing the European Banking Committee (Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/31986L0635",
            text="Directive 86/635/EEC",
            title="On the annual accounts and consolidated accounts of banks "
            "and other financial institutions",
        ),
        Anchor(
            href="/eu/32009L0065",
            text="Directive 2009/65/EC",
            title="On the coordination of laws, regulations and administrative "
            "provisions relating to undertakings for collective "
            "investment in transferable securities (UCITS) "
            "(Text with EEA relevance)",
        ),
        Anchor(
            href="/eu/32010R1093",
            text="Regulation (EU) No 1093/2010",
            title="Establishing a European Supervisory Authority "
            "(European Banking Authority)",
        ),
        Anchor(
            href="/eu/32010R1094",
            text="Regulation (EU) No 1094/2010",
            title="Establishing a European Supervisory Authority "
            "(European Insurance and Occupational Pensions Authority)",
        ),
        Anchor(
            href="/eu/32011L0061",
            text="Directive 2011/61/EU",
            title="On Alternative Investment Fund Managers",
        ),
        Anchor(
            href="/eu/31978L0660",
            text="Directive 78/660/EEC",
            title="Based on Article 54 (3) (g) of the Treaty on the annual "
            "accounts of certain types of companies",
        ),
        Anchor(
            href="/eu/32010R1092",
            text="Regulation (EU) No 1092/2010",
            title="On European Union macro-prudential oversight of the "
            "financial system and establishing a European Systemic Risk Board",
        ),
        Anchor(
            href="/eu/32009D0937",
            text="32009D0937",
            title="Adopting the Council's Rules of Procedure",
        ),
        Anchor(
            href="/eu/32001R0045",
            text="Regulation (EC) No 45/2001",
            title="On the protection of individuals with regard to the "
            "processing of personal data by the Community institutions "
            "and bodies and on the free movement of such data",
        ),
        Anchor(
            href="/eu/31994L0019",
            text="Directive 94/19/EC",
            title="On deposit-guarantee schemes",
        ),
    },
    date_document=datetime.date(2013, 6, 26),
    date_publication=datetime.date(2013, 6, 27),
    first_date_entry_in_force=datetime.date(2013, 6, 28),
    id_human="Regulation (EU) No 575/2013",
    id_local="32013R0575",
    in_force=True,
    passed_by={"Council of the European Union", "European Parliament"},
    serial_number=575,
    source_iri="http://publications.europa.eu/resource/eli/reg/2013/575/oj",
    title="Regulation (EU) No 575/2013 of the European Parliament and of the "
    "Council of 26 June 2013 on prudential requirements for credit "
    "institutions and investment firms and amending "
    "Regulation (EU) No 648/2012  Text with EEA relevance",
    title_essence="On prudential requirements for credit institutions and investment firms",
    type_document="REG",
)


def check_title_retriever():
    cellar_trunk = "http://publications.europa.eu/resource/cellar/"

    print(
        TitlesRetriever(
            "EN",
            (
                cellar_trunk + "ccd31733-df06-11e2-9165-01aa75ed71a1",
                cellar_trunk + "775a4724-2086-4a06-9213-1a4e6489053b",
                cellar_trunk + "0177e751-7cb7-404b-98d8-79a564ddc629",
            ),
        ).get_anchors()
    )


class TestSerialization(unittest.TestCase):
    DATA_PATH = os.path.join(os.path.dirname(__file__), "data")

    def setUp(self):
        self.maxDiff = None
        self.sauce = et.ElementTree(
            file=os.path.join(self.DATA_PATH, "metas_1.html"), parser=et.HTMLParser()
        )
        self.expected = sorted(
            [
                et.tostring(meta, encoding="unicode", method="html").strip()
                for meta in self.sauce.xpath("/html/head/meta[@property]")
            ]
        )

    def test_dumps(self):
        actual = sorted(
            [
                et.tostring(meta, encoding="unicode", method="html")
                for meta in amd.to_rdfa()
            ]
        )
        for k, (expected, act) in enumerate(zip(self.expected, actual)):
            self.assertEqual(expected, act, f"Problem at {k}")
        self.assertEqual("\n".join(self.expected), "\n".join(actual))

    def test_parse(self):
        md = ActMetaData.parse(self.sauce.getroot())
        re_serialized = sorted(
            [
                et.tostring(meta, encoding="unicode", method="html")
                for meta in md.to_rdfa()
            ]
        )
        self.assertEqual(
            self.expected,
            re_serialized,
            "Missed = {missed}, overhead = {overhead}".format(
                missed=str(set(self.expected) - set(re_serialized)),
                overhead=str(set(re_serialized) - set(self.expected)),
            ),
        )


class TestDictSerialization(unittest.TestCase):
    def test_1(self):
        re_parsed = ActMetaData.from_dict(amd.to_dict())
        for (l_name, l_value), (r_name, r_value) in zip(amd.items(), re_parsed.items()):
            self.assertEqual(l_name, r_name)
            self.assertEqual(l_value, r_value)

    def test_2(self):
        re_parsed = ActMetaData.from_dict(
            json.loads(json.dumps(amd.to_dict(), default=default))
        )
        for (l_name, l_value), (r_name, r_value) in zip(amd.items(), re_parsed.items()):
            self.assertEqual(l_name, r_name)
            self.assertEqual(l_value, r_value)


if __name__ == "__main__":
    unittest.main()
