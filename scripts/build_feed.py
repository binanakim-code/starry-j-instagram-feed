#!/usr/bin/env python3
"""Build a one-item-per-product Meta catalog feed from the BASE variant feed."""

from __future__ import annotations

import copy
import os
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

SOURCE_URL = os.environ.get(
    "SOURCE_FEED_URL",
    "https://baseec2.s3.ap-northeast-1.amazonaws.com/facebook-app/feed/"
    "d8503f4ffbc66dcbbc6413e547ffb5392f725fbf.xml",
)
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "docs/feed.xml"))
GOOGLE_NS = "http://base.google.com/ns/1.0"

ET.register_namespace("g", GOOGLE_NS)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def field_text(item: ET.Element, name: str) -> str:
    for child in item:
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def is_product_record(element: ET.Element) -> bool:
    fields = {local_name(child.tag) for child in element}
    has_identity = "id" in fields and "title" in fields
    has_catalog_data = bool(
        fields.intersection({"price", "availability", "image_link", "link"})
    )
    return has_identity and has_catalog_data


def is_available(item: ET.Element) -> bool:
    value = field_text(item, "availability").lower().replace("_", " ")
    return value in {"in stock", "available for order", "preorder", "pre order"}


def choose_representative(items: list[ET.Element]) -> ET.Element:
    # Preserve BASE's first variant whenever possible, but prefer an available
    # variant so the product remains purchasable when another size is sold out.
    return next((item for item in items if is_available(item)), items[0])


def to_google_field(source: ET.Element) -> ET.Element:
    converted = ET.Element(f"{{{GOOGLE_NS}}}{local_name(source.tag)}", source.attrib)
    converted.text = source.text
    converted.tail = source.tail
    for child in source:
        converted.append(to_google_field(child))
    return converted


def main() -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "StarryJ-Catalog-Feed/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        source_xml = response.read()

    source_tree = ET.parse(BytesIO(source_xml))
    source_root = source_tree.getroot()
    source_items = [
        element for element in source_root.iter() if is_product_record(element)
    ]
    if not source_items:
        root_tag = local_name(source_root.tag)
        child_tags = sorted({local_name(child.tag) for child in source_root.iter()})
        raise RuntimeError(
            f"No product records found. root={root_tag}; tags={child_tags[:30]}"
        )

    groups: OrderedDict[str, list[ET.Element]] = OrderedDict()
    for item in source_items:
        item_id = field_text(item, "id")
        group_id = field_text(item, "item_group_id")
        key = group_id or item_id
        groups.setdefault(key, []).append(item)

    output_root = ET.Element("rss", {"version": "2.0"})
    output_channel = ET.SubElement(output_root, "channel")
    ET.SubElement(output_channel, "title").text = "Starry J BASE Products"
    ET.SubElement(output_channel, "link").text = "https://shop.starry-j.online"
    ET.SubElement(output_channel, "description").text = (
        "Deduplicated product feed for Meta and Instagram"
    )

    for variants in groups.values():
        representative = choose_representative(variants)
        output_item = ET.SubElement(output_channel, "item")
        for child in representative:
            if local_name(child.tag) == "item_group_id":
                continue
            output_item.append(to_google_field(copy.deepcopy(child)))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(output_root).write(
        OUTPUT_PATH,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"Built {OUTPUT_PATH}: {len(source_items)} variants -> "
        f"{len(groups)} products"
    )


if __name__ == "__main__":
    main()
