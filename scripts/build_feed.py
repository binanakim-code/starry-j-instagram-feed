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


def is_available(item: ET.Element) -> bool:
    value = field_text(item, "availability").lower().replace("_", " ")
    return value in {"in stock", "available for order", "preorder", "pre order"}


def choose_representative(items: list[ET.Element]) -> ET.Element:
    # Preserve BASE's first variant whenever possible, but prefer an available
    # variant so the product remains purchasable when another size is sold out.
    return next((item for item in items if is_available(item)), items[0])


def main() -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "StarryJ-Catalog-Feed/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        source_xml = response.read()

    tree = ET.parse(BytesIO(source_xml))
    root = tree.getroot()
    channel = next(
        (element for element in root.iter() if local_name(element.tag) == "channel"),
        None,
    )
    if channel is None:
        raise RuntimeError("The BASE feed does not contain an RSS channel.")

    source_items = [
        child for child in list(channel) if local_name(child.tag) == "item"
    ]
    if not source_items:
        raise RuntimeError("The BASE feed contains no product items.")

    groups: OrderedDict[str, list[ET.Element]] = OrderedDict()
    for item in source_items:
        item_id = field_text(item, "id")
        group_id = field_text(item, "item_group_id")
        key = group_id or item_id
        if not key:
            raise RuntimeError("A product item has neither id nor item_group_id.")
        groups.setdefault(key, []).append(item)

    representatives: list[ET.Element] = []
    for variants in groups.values():
        representative = copy.deepcopy(choose_representative(variants))
        for child in list(representative):
            if local_name(child.tag) == "item_group_id":
                representative.remove(child)
        representatives.append(representative)

    for item in source_items:
        channel.remove(item)
    channel.extend(representatives)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tree.write(OUTPUT_PATH, encoding="utf-8", xml_declaration=True)

    print(
        f"Built {OUTPUT_PATH}: {len(source_items)} variants -> "
        f"{len(representatives)} products"
    )


if __name__ == "__main__":
    main()
