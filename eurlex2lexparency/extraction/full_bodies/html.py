import os
from urllib.parse import urljoin, urlparse
import requests
from lxml import etree as et
import logging

from eurlex2lexparency.extraction.generic import Retriever, img_2_base64
from eurlex2lexparency.utils.generics import retry


# TODO: Find raw documents that have java-script elements directly embedded.
#         Those elements should be extracted from the document and should
#         be stored in a separate js-file.
#         Actually, the same holds for embedded style-elements.
class HTMLoader(Retriever):
    def __init__(self, local_path, url, logger=None):
        self.logger = logger or logging.getLogger()
        super().__init__(local_path, url)

    def open(self):
        document = et.ElementTree(
            file=os.path.join(self.local_path, "raw.html"),
            parser=et.HTMLParser(encoding="utf-8", remove_blank_text=True),
        )
        return document.getroot()

    def retrieve(self):
        sauce = requests.get(self.url).content.replace(b" xmlns=", b" xmlnamespace=")
        document = et.fromstring(
            sauce, parser=et.HTMLParser(encoding="utf-8", remove_blank_text=True)
        )
        for element in document.xpath("//*[@xmlnamespace]"):
            element.attrib.pop("xmlnamespace")

        @retry(exceptions=requests.exceptions.ConnectionError, tries=3)
        def patiently_get(url_):
            return requests.get(url_).content

        for attrib in ("src", "href"):  # Making all url-paths absolute
            for element in document.xpath(f"//*[@{attrib}]"):
                if element.attrib[attrib].startswith("#"):
                    continue
                element.attrib[attrib] = urljoin(self.url, element.attrib[attrib])

            for k, resource in enumerate(document.xpath(f"//img[@{attrib}]")):
                if resource.attrib[attrib].startswith("data:image/jpg;base64"):
                    continue
                resource_url = urlparse(resource.attrib[attrib])
                suffix = resource_url.geturl().split(".")[-1]
                resource.attrib[attrib] = img_2_base64(
                    suffix, patiently_get(resource_url.geturl())
                )
        # Store to self.local_path
        os.makedirs(self.local_path, mode=0o770, exist_ok=True)
        et.ElementTree(document).write(
            os.path.join(self.local_path, "raw.html"),
            method="html",
            pretty_print=True,
            encoding="utf-8",
        )
        return document
