import os


LEXPATH = os.path.join(os.path.dirname(__file__), 'inte_data')

ETL_BATCH_FILE = os.path.join(LEXPATH, 'batch.json')

CELEX_CONNECT_STRING = 'sqlite:///{}'.format(os.path.join(LEXPATH, 'celex.db'))

LANG_2_ADDRESS = {'DE': 'http://localhost:5000'}

