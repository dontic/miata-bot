from pathlib import Path

from miata_bot.config import normalize_search_url
from miata_bot.parser import is_challenge_page, parse_listings
from miata_bot.telegram import format_caption

FIXTURE = Path(__file__).parent / "fixtures" / "results_page.html"


def test_skips_sponsored_and_parses_fields():
    listings = parse_listings(FIXTURE.read_text())

    # The fixture holds 2 sponsored blocks and 3 organic listings.
    assert [l.id for l in listings] == ["9698873936", "9698144767", "9697365164"]

    first = listings[0]
    assert first.title == "Mazda Mx5 1.6 2WD"
    assert first.price == "7,141 €"
    assert first.year == "1993"
    assert first.mileage == "177,100 Km"
    assert first.gearbox == "Manual"
    assert first.postcode == ""  # "-" on the site
    assert first.country_code == "se"
    assert first.country == "Sweden"
    assert first.source == "bilweb.se"
    assert first.url.startswith("https://www.theparking.eu/used-cars-detail/")
    assert first.image_url.startswith("https://img.leparking.fr/800x600/")


def test_discounted_price_keeps_current_price_only():
    discounted = parse_listings(FIXTURE.read_text())[2]
    assert discounted.price == "16,942 €"


def test_normalize_hash_url():
    url = "https://www.theparking.eu/#!/used-cars/mx5.html%3Fid_volant%3D1%26slider_millesime%3D1910%7C1997%26tri%3Ddate"
    assert normalize_search_url(url) == (
        "https://www.theparking.eu/used-cars/mx5.html?id_volant=1&slider_millesime=1910|1997&tri=date"
    )


def test_challenge_detection():
    assert is_challenge_page("<html><head><title>Just a moment...</title></head></html>")
    assert not is_challenge_page(FIXTURE.read_text())


def test_caption_is_html_safe():
    listing = parse_listings(FIXTURE.read_text())[0]
    listing.description = "<script> & stuff"
    caption = format_caption(listing)
    assert "&lt;script&gt; &amp; stuff" in caption
    assert "🇸🇪" in caption
    assert len(caption) <= 1024
