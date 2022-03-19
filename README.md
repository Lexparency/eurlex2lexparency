# eurlex2lexparency
Transforming documents from Eur-Lex to Lexparency

## Installation

`pip install eurlex2lexparency`

## Usage

Using this package requires a settings-module on first level,
featuring the definition of the following variables.

| Name                 | Description                                               |
|----------------------|-----------------------------------------------------------|
| LEXPATH              | Filesystem path to store the transformed documents.       |
| CELEX_CONNECT_STRING | To be used by `sqlalchemy.create_engine`                  |
| LANG_2_ADDRESS       | Dictionary, language code to corresponding Lexparency URL |
