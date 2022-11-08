import os

from settings import LEXPATH
from eurlex2lexparency.extraction.meta_data.graph_data import prefixes, new_graph


# with urllib.request.urlopen(prefixes['op-rt']) as connection:
g = new_graph()
g.load(source=prefixes["res-type"][:-1], format="xml")

res = g.query(
    """
SELECT ?s WHERE { 
    ?s skos:inScheme <http://publications.europa.eu/resource/authority/resource-type> .
}
"""
)

secondary_uris = set(row[0] for row in res)

for uri in secondary_uris:
    print("loading from  " + uri)
    g.load(source=uri, format="xml")


# Now the same game with passing bodies:
print("\n--Loading passing bodies--")
g.load(source=prefixes["corp"][:-1], format="xml")

res = g.query(
    """
SELECT ?s WHERE { 
    ?s skos:inScheme <http://publications.europa.eu/resource/authority/corporate-body> .
}
"""
)

secondary_uris = set(row[0] for row in res)

for uri in secondary_uris:
    print("loading from  " + uri)
    g.load(source=uri, format="xml")


RDF_PATH = os.path.join(LEXPATH, "RDF")

g.serialize(
    destination=os.path.join(RDF_PATH, "op_resource_authority.ttl"), format="turtle"
)
