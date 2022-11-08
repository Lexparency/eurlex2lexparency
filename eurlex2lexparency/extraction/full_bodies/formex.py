import os
import shutil
from zipfile import ZipFile
import requests
from lxml import etree as et
from PIL import Image
import logging

from eurlex2lexparency.celex_manager.eurlex import country_mapping
from eurlex2lexparency.extraction.generic import (
    Retriever,
    FormatNotAvailable,
    img_2_base64,
)
from eurlex2lexparency.utils.eurlex_request_lock import eurlex_request_queue


class FileCheater:
    """
    For cheating on Image.save:
        https://pillow.readthedocs.io/en/3.1.x/reference/Image.html
    """

    def __init__(self):
        self.content = b""

    def write(self, inp: bytes):
        self.content += inp

    def tell(self, value):
        raise NotImplemented("Why do you even need this method?")

    def seek(self):
        raise NotImplemented("Why do you even need this method?")


class BasicFormexLoader(Retriever):
    def __init__(self, local_path, url, language, logger=None):
        """
        :param local_path: path up until the fmx subdir
        :param language: two character language code
        :param url: celex-ID, optionally including version indicator (YYYYmmdd)
        :param logger: logger
        """
        assert language.isupper() and len(language) == 2
        self.language = country_mapping.get(two=language).lower()
        self.logger = logger or logging.getLogger()
        super().__init__(local_path, url)

    def retrieve(self):
        """
        Corresponding curl command:
        curl -XGET https://publications.europa.eu/resource/celex/02002F0584-20090328 \
            -H 'Accept: application/zip;mtype=fmx4' \
            -H 'Accept-Language: deu' -L --output 02002F0584-20090328.zip
        """
        eurlex_request_queue.wait()
        r = requests.get(
            "https://publications.europa.eu/resource/celex/{}".format(self.url),
            headers={
                "Accept": "application/zip;mtype=fmx4",
                "Accept-Language": self.language,
            },
        )
        if r.status_code != 200:
            raise FormatNotAvailable('Reason "{}" ({})'.format(r.reason, r.status_code))
        self.store_local(r.content)
        return r.content

    def store_local(self, content):
        with open(os.path.join(self.local_path, "fmx.zip"), mode="wb") as f:
            f.write(content)

    def open(self):
        with open(os.path.join(self.local_path, "fmx.zip"), mode="rb") as f:
            content = f.read()
        return content


class FormexLoader(Retriever):
    def __init__(self, local_path, url, language, logger=None):
        self.zipped_formex = BasicFormexLoader(
            local_path, url, language, logger
        ).document
        super().__init__(local_path, url)
        self.logger = logger or logging.getLogger()

    def extract(self):
        tmpath = os.path.join(self.local_path, "tmp")
        os.makedirs(tmpath, exist_ok=True)
        result = {}
        with ZipFile(os.path.join(self.local_path, "fmx.zip")) as f:
            self.logger.info(
                'Inflating zip file for "CELEX:{}"\n'.format(self.url)
                + "File list: {}".format(", ".join(f.namelist()))
            )
            for name in f.namelist():
                f.extract(name, tmpath)
                if name.endswith(".tif"):
                    im = Image.open(os.path.join(tmpath, name))
                    self.logger.info(f"Converting {name}")
                    fc = FileCheater()
                    if im.mode in ("CMYK", "RGBX"):
                        im = im.convert("RGB")
                    im.save(fc, format="PNG")
                    result[name] = img_2_base64("PNG", fc.content)
                elif name.endswith(".xml"):
                    result[name] = et.ElementTree(
                        file=os.path.join(tmpath, name),
                        parser=et.XMLParser(encoding="utf-8"),
                    ).getroot()
                else:
                    raise NotImplementedError(
                        f"No idea how to handle this file: {name}."
                    )
        shutil.rmtree(tmpath)
        return result

    def retrieve(self):
        zf = self.extract()
        overview = [value for name, value in zf.items() if name.endswith(".doc.xml")][0]
        main = zf[overview.xpath("//DOC.MAIN.PUB/REF.PHYS/@FILE")[0]]
        annexes = [
            zf[name]
            for name in overview.xpath('//DOC.SUB.PUB[@TYPE="ANNEX"]/REF.PHYS/@FILE')
        ]
        combined = et.Element("LEXP.COMBINED")
        combined.append(main)
        if len(annexes) > 1:
            annexes_e = et.SubElement(combined, "ANNEXES")
            for element in annexes:
                annexes_e.append(element)
        elif len(annexes) == 1:
            combined.append(annexes[0])
        while combined.xpath('//INCL.ELEMENT[@TYPE="FORMEX.DOC"]'):
            # Case of ugly nesting, e.g. 32015R0079
            # or multiple nesting, as in 32019R0428
            for element in combined.xpath('//INCL.ELEMENT[@TYPE="FORMEX.DOC"]'):
                if list(element.iterancestors("BIB.INSTANCE")):
                    element.getparent().remove(element)
                    continue
                content = zf[element.attrib["FILEREF"]]
                for bibi in content.xpath("//BIB.INSTANCE"):
                    bibi.getparent().remove(bibi)
                element.addnext(content)
                element.getparent().remove(element)
        delivered_tifs = set(tif for tif in zf if tif.endswith(".tif"))
        required_tifs = set(combined.xpath('//INCL.ELEMENT[@TYPE="TIFF"]/@FILEREF'))
        if delivered_tifs < required_tifs:
            raise FormatNotAvailable(
                "Actually, it is not complete! "
                "TODO: adapt data-model to set formex status"
            )
        if delivered_tifs:
            for tif in combined.xpath('//INCL.ELEMENT[@TYPE="TIFF"]'):
                tif.attrib["FILEREF"] = zf[tif.attrib["FILEREF"]]
        et.ElementTree(element=combined).write(
            os.path.join(self.local_path, "formex.xml"), encoding="utf-8"
        )
        return combined

    def open(self):
        return et.ElementTree(
            file=os.path.join(self.local_path, "formex.xml")
        ).getroot()
