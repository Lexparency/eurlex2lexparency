import argparse

from eurlex2lexparency.celex_manager.eurlex import PreLegalContentXmlDataBase


parser = argparse.ArgumentParser(
    description="Queries the Eurlex database for document IDs and stores metadata to a preliminary database"
)
parser.add_argument(
    "--consyear", help="Focus on consolidated versions published at given year."
)
parser.add_argument(
    "--consleg", help="Include Celexes for consolidated Versions.", action="store_true"
)
parser.add_argument("--pre", help="First digit of the celex ID.")
parser.add_argument("--year", help="Specify year of the documents to be queried.")
parser.add_argument(
    "--inter", help="Interfix of the celex ID, specifying the document type."
)
parser.add_argument("--number", help="Number of the document.")
parser.add_argument(
    "--resume", help="Resume from previous queries", action="store_true"
)
args = parser.parse_args()
plcxdb = PreLegalContentXmlDataBase()
if args.consyear is not None:
    plcxdb.get_conslegs_from(args.consyear, resume=args.resume)
else:
    kwargs = {key: value for key, value in args.__dict__.items() if value is not None}
    plcxdb.get_celexes_where(**kwargs)
