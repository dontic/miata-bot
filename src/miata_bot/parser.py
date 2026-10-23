"""Parse a theparking.eu results page into Listing objects."""

import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

BASE_URL = "https://www.theparking.eu"

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_ID_RE = re.compile(r"holder-(\d+)")


@dataclass
class Listing:
    id: str
    title: str
    description: str
    price: str
    year: str
    mileage: str
    fuel: str
    gearbox: str
    postcode: str
    country_code: str
    country: str
    published: str
    seller: str
    source: str
    url: str
    image_url: str

    def to_dict(self) -> dict:
        return asdict(self)


def _text(node: LexborNode, selector: str) -> str:
    found = node.css_first(selector)
    # separator=" " keeps sibling spans ("Mazda", "Mx5", "1.6") from running together
    return " ".join(found.text(separator=" ").split()) if found else ""


def _is_sponsored(li: LexborNode) -> bool:
    classes = (li.attributes.get("class") or "").split()
    return "premium" in classes or "premium-bloc" in classes or li.css_first(".sponsor") is not None


def _parse_item(li: LexborNode) -> Listing | None:
    match = _ID_RE.search(li.attributes.get("class") or "")
    if not match:
        return None

    title = _text(li, ".block-title-list h2")
    link = li.css_first(".block-title-list a")
    url = urljoin(BASE_URL, link.attributes.get("href", "")) if link else ""

    img = li.css_first(".figure picture img")
    image_url = img.attributes.get("src", "") if img else ""
    # Thumbnails are served at any WxH prefix; ask for a larger rendition.
    image_url = re.sub(r"(img\.leparking\.fr/)\d+x\d+/", r"\g<1>800x600/", image_url)

    flag = li.css_first(".location .sprite")
    flag_classes = (flag.attributes.get("class") or "").split() if flag else []
    country_code = next((c for c in flag_classes if c != "sprite"), "")

    # The info list is: fuel, mileage, year, gearbox, postcode (each may be "-").
    infos = [" ".join(x.text().split()) for x in li.css(".bc-info.bigScreen ul.info li")]
    infos = [("" if v == "-" else v) for v in infos] + [""] * 5
    fuel, mileage, year, gearbox, postcode = infos[:5]
    if not _YEAR_RE.match(year):
        year = next((v for v in infos if _YEAR_RE.match(v)), "")

    return Listing(
        id=match.group(1),
        title=title,
        description=_text(li, ".desc"),
        price=_text(li, ".title-n-price .price-block p.prix"),
        year=year,
        mileage=mileage,
        fuel=fuel,
        gearbox=gearbox,
        postcode=postcode,
        country_code=country_code,
        country=_text(li, ".location .upper").title(),
        published=_text(li, ".btn-publication"),
        seller=_text(li, ".seller"),
        source=_text(li, ".site-bottom a"),
        url=url,
        image_url=image_url,
    )


def parse_listings(html: str) -> list[Listing]:
    """Return the organic (non-sponsored) listings on a results page, in page order."""
    tree = LexborHTMLParser(html)
    listings = []
    for li in tree.css("li.li-result"):
        if _is_sponsored(li):
            continue
        item = _parse_item(li)
        if item:
            listings.append(item)
    return listings


def is_challenge_page(html: str) -> bool:
    return "<title>Just a moment...</title>" in html
