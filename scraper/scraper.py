#!/usr/bin/env python3
"""
Scraper działek - Rzeszów 30km + Zakopane 20km
v4 - Playwright dla portali z JS renderingiem

Portale requests (szybkie):  Otodom, OLX API, Domiporta
Portale Playwright (Chrome): Gratka, Nieruchomosci-online, Adresowo, Morizon
"""

import json
import time
import random
import re
import hashlib
import logging
import asyncio
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

LOCATION_KEYWORDS = {
    "rzeszow": [
        "rzeszów", "rzeszow", "boguchwała", "boguchwa", "głogów małopolski",
        "tyczyn", "świlcza", "swilcza", "krasne", "lubenia", "dynów", "dynow",
        "sokołów małopolski", "strzyżów", "strzyzow", "czudec", "nisko",
        "leżajsk", "łańcut", "lancut", "przeworsk", "jarosław", "jaroslaw",
        "podkarpacie", "podkarpackie", "rzeszowski",
    ],
    "zakopane": [
        "zakopane", "poronin", "biały dunajec", "bialy dunajec", "szaflary",
        "nowy targ", "bukowina tatrzańska", "bukowina tatrzanska",
        "białka tatrzańska", "bialka tatrzanska", "murzasichle",
        "kościelisko", "koscielisko", "chochołów", "chocholow",
        "czarny dunajec", "rabka", "tatry", "tatrzański", "tatrzanski",
        "małopolskie", "malopolskie", "podhale",
    ],
}

LOCATIONS = {
    "rzeszow": {
        "label": "Rzeszów i okolice (30 km)",
        # Otodom — poprawny URL (zakopane działa, rzeszów ma inną ścieżkę)
        "otodom_url":        "https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/podkarpackie?distanceRadius=30&locations=%5Bcities_6-935%5D&viewType=listing",
        "olx_url":           "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/rzeszow/?search[dist]=30",
        "domiporta_url":     "https://www.domiporta.pl/dzialka/sprzedam/podkarpackie/rzeszowski",
        # Portale JS — Playwright
        "gratka_url":        "https://gratka.pl/nieruchomosci/dzialki/podkarpackie?promien=30&lokalizacja_miejscowosc=Rzesz%C3%B3w&transakcja=sprzedaz",
        "nieruchomosci_url": "https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Rzesz%C3%B3w,,,30",
        "adresowo_url":      "https://adresowo.pl/dzialki/rzeszow/",
        "morizon_url":       "https://www.morizon.pl/dzialki/rzeszow/",
    },
    "zakopane": {
        "label": "Zakopane i okolice (20 km)",
        "otodom_url":        "https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/malopolskie/tatrzanski/zakopane?distanceRadius=20&viewType=listing",
        "olx_url":           "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/zakopane/?search[dist]=20",
        "domiporta_url":     "https://www.domiporta.pl/dzialka/sprzedam/malopolskie/tatrzanski",
        "gratka_url":        "https://gratka.pl/nieruchomosci/dzialki/malopolskie?promien=20&lokalizacja_miejscowosc=Zakopane&transakcja=sprzedaz",
        "nieruchomosci_url": "https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Zakopane,,,20",
        "adresowo_url":      "https://adresowo.pl/dzialki/zakopane/",
        "morizon_url":       "https://www.morizon.pl/dzialki/zakopane/",
    },
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def uid(s):
    return hashlib.md5(s.encode()).hexdigest()[:12]

def sleep(a=2.0, b=4.5):
    time.sleep(random.uniform(a, b))

def get(url, referer=None):
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    try:
        r = requests.get(url, headers=h, timeout=25)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"GET failed {url}: {e}")
        return None

def parse_price(text):
    if not text:
        return None
    text = re.sub(r"[\xa0\u202f\u00a0\s]", "", str(text))
    text = text.replace("PLN", "").replace("zł", "").replace(",", "")
    m = re.search(r"\d{4,}", text)
    if m:
        try:
            val = int(re.sub(r"\D", "", m.group(0)))
            return val if 5_000 <= val <= 50_000_000 else None
        except Exception:
            pass
    return None

def parse_area(text):
    if not text:
        return None
    text = str(text).replace(",", ".")
    m = re.search(r"(\d[\d\s\.]*)\s*m", text)
    if m:
        try:
            val = int(float(re.sub(r"[\s]", "", m.group(1))))
            return val if 10 <= val <= 1_000_000 else None
        except Exception:
            pass
    return None

def is_in_location(text, location_key):
    t = text.lower()
    return any(kw in t for kw in LOCATION_KEYWORDS[location_key])

def make_item(source, location, location_key, title, price, area, city, desc, images, url):
    return {
        "id":             uid(url or source + title + city),
        "source":         source,
        "location_area":  location["label"],
        "location_key":   location_key,
        "title":          (title or "Działka").strip()[:200],
        "price":          price,
        "price_currency": "PLN",
        "area_m2":        area,
        "city":           (city or "").strip()[:100],
        "description":    (desc or "").strip()[:500],
        "images":         images or [],
        "url":            url or "",
        "scraped_at":     datetime.utcnow().isoformat(),
    }


# ─── PLAYWRIGHT HELPER ────────────────────────────────────────────────────────

def pw_get_html(page, url, wait_selector=None, wait_ms=3000):
    """Ładuje stronę Playwrightem i zwraca HTML po wyrenderowaniu JS."""
    try:
        page.goto(url, wait_until="networkidle", timeout=35000)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=10000)
            except PWTimeout:
                page.wait_for_timeout(wait_ms)
        else:
            page.wait_for_timeout(wait_ms)
        return page.content()
    except Exception as e:
        log.warning(f"[Playwright] GET failed {url}: {e}")
        return ""

def dismiss_cookie_banners(page):
    """Zamyka banery cookie żeby nie blokowały kliknięć."""
    for sel in [
        "button#onetrust-accept-btn-handler",
        "button[id*='accept']",
        "button[class*='accept']",
        "button[class*='cookie']",
        "[data-testid='cookie-accept']",
        ".cookie-accept",
        "#cookieAccept",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
                break
        except Exception:
            pass


# ─── 1. OTODOM ────────────────────────────────────────────────────────────────

def scrape_otodom(location_key, location):
    log.info(f"[Otodom] {location_key}")
    results = []
    base_url = location["otodom_url"]

    for page_num in range(1, 6):
        url = base_url if page_num == 1 else base_url + f"&page={page_num}"
        r = get(url, referer="https://www.otodom.pl/")
        if not r:
            break

        soup   = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            log.warning(f"[Otodom] brak __NEXT_DATA__ str.{page_num}")
            break

        try:
            data  = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})
            items = (props.get("data", {}).get("searchAds", {}).get("items", [])
                     or props.get("listing", {}).get("results", [])
                     or props.get("searchAdsResponse", {}).get("items", []))
        except Exception as e:
            log.warning(f"[Otodom] JSON: {e}")
            break

        if not items:
            break

        for item in items:
            try:
                price_raw = item.get("totalPrice") or item.get("price") or {}
                price = price_raw.get("value") if isinstance(price_raw, dict) else price_raw

                area = item.get("areaInSquareMeters") or item.get("area")
                if isinstance(area, list):
                    area = area[0] if area else None

                images = []
                for img in (item.get("images") or item.get("photos") or [])[:6]:
                    src = (img.get("large") or img.get("medium") or img.get("small")
                           or img.get("src") or (img if isinstance(img, str) else None))
                    if src:
                        images.append(src)

                slug = item.get("slug") or item.get("id", "")
                link = f"https://www.otodom.pl/pl/oferta/{slug}" if slug else ""

                loc  = item.get("locationLabel") or item.get("location") or {}
                city = (loc.get("value") or loc.get("name") or item.get("city", "")) if isinstance(loc, dict) else str(loc)

                check = f"{city} {item.get('title','')} {link}"
                if not is_in_location(check, location_key):
                    continue

                results.append(make_item(
                    "Otodom", location, location_key,
                    item.get("title"), price, area, city,
                    item.get("shortDescription", ""), images, link,
                ))
            except Exception as e:
                log.debug(f"[Otodom] item: {e}")
        sleep()

    log.info(f"[Otodom] {location_key}: {len(results)}")
    return results


# ─── 2. OLX (API) ────────────────────────────────────────────────────────────

OLX_API_IDS = {
    "rzeszow":  {"category_id": 1389, "region_id": 14,  "city_id": 116063, "dist": 30},
    "zakopane": {"category_id": 1389, "region_id": 15,  "city_id": 145283, "dist": 20},
}

def scrape_olx(location_key, location):
    log.info(f"[OLX] {location_key}")
    results = []
    p = OLX_API_IDS[location_key]

    for offset in range(0, 200, 40):
        url = (f"https://www.olx.pl/api/v1/offers/"
               f"?category_id={p['category_id']}&region_id={p['region_id']}"
               f"&city_id={p['city_id']}&dist={p['dist']}"
               f"&sort_by=created_at%3Adesc&offset={offset}&limit=40")
        try:
            r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=25)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning(f"[OLX API] offset={offset}: {e}")
            break

        offers = data.get("data", [])
        if not offers:
            break

        for offer in offers:
            try:
                title = offer.get("title", "Działka")
                link  = offer.get("url", "")
                if link and not link.startswith("http"):
                    link = "https://www.olx.pl" + link

                price = None
                pi = offer.get("price") or {}
                if isinstance(pi, dict):
                    price = parse_price(str(pi.get("value", "") or ""))

                loc  = offer.get("location") or {}
                city = ((loc.get("city") or {}).get("name", "") if isinstance(loc.get("city"), dict)
                        else loc.get("city", "") or loc.get("name", ""))

                images = []
                for ph in (offer.get("photos") or offer.get("images") or [])[:6]:
                    src = ph.get("link") or ph.get("url") or (ph if isinstance(ph, str) else "")
                    if src and src.startswith("http"):
                        images.append(src)

                area = None
                for param in offer.get("params", []):
                    if param.get("key") in ("surface", "area", "m2"):
                        area = parse_area(str(param.get("value", {}).get("key", "") if isinstance(param.get("value"), dict) else param.get("value", "")))
                        if area:
                            break

                desc = (offer.get("description") or "")[:300]

                check = f"{city} {title} {link}"
                if not is_in_location(check, location_key):
                    continue

                results.append(make_item("OLX", location, location_key, title, price, area, city, desc, images, link))
            except Exception as e:
                log.debug(f"[OLX] item: {e}")

        if not data.get("links", {}).get("next"):
            break
        sleep(1, 2)

    log.info(f"[OLX] {location_key}: {len(results)}")
    return results


# ─── 3. DOMIPORTA (requests) ─────────────────────────────────────────────────

def scrape_domiporta(location_key, location):
    log.info(f"[Domiporta] {location_key}")
    results = []

    for page_num in range(1, 8):
        base = location["domiporta_url"]
        url  = base if page_num == 1 else base + f"?PageNumber={page_num}"
        r    = get(url, referer="https://www.domiporta.pl/")
        if not r:
            break
        soup  = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".sneakpeak") or soup.select("li.listing__item") or soup.select(".listing-item")
        if not cards:
            break

        for card in cards:
            try:
                a    = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://www.domiporta.pl" + link

                title_el = card.select_one(".sneakpeak__title") or card.select_one("[class*='title']") or card.find("h2") or card.find("h3")
                title    = title_el.get_text(strip=True) if title_el else "Działka"

                price_el = card.select_one(".sneakpeak__price") or card.select_one("[class*='price']")
                price    = parse_price(price_el.get_text() if price_el else "")

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("data-lazy") or img_el.get("src")
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = card.select_one(".sneakpeak__location") or card.select_one("[class*='location']")
                city   = loc_el.get_text(strip=True) if loc_el else ""

                area_el = card.select_one("[class*='area']") or card.select_one("[class*='powierzch']")
                area    = parse_area(area_el.get_text() if area_el else "") or parse_area(title)

                check = f"{city} {title} {link}"
                if not is_in_location(check, location_key):
                    continue

                results.append(make_item("Domiporta", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[Domiporta] item: {e}")
        sleep()

    log.info(f"[Domiporta] {location_key}: {len(results)}")
    return results


# ─── PLAYWRIGHT SCRAPERS ──────────────────────────────────────────────────────

def _pw_parse_cards(html, source, location, location_key, card_selectors, base_domain):
    """Wspólny parser HTML po Playwright dla różnych portali."""
    results = []
    soup    = BeautifulSoup(html, "html.parser")

    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if cards:
            break

    if not cards:
        # Wypisz dostępne klasy żeby znaleźć właściwy selektor
        log.warning(f"[{source}] brak kart w HTML ({len(html)} znaków)")
        all_classes = []
        for tag in soup.find_all(["article", "li", "div", "section"], class_=True)[:80]:
            for c in tag.get("class", []):
                if len(c) > 3 and c not in all_classes:
                    all_classes.append(c)
        log.warning(f"[{source}] klasy elementów: {sorted(all_classes)[:50]}")
        return results

    for card in cards:
        try:
            a    = card.find("a", href=True)
            link = a["href"] if a else ""
            if link and link.startswith("/"):
                link = base_domain + link

            title_el = (card.select_one("[class*='title']") or card.select_one("[class*='Title']")
                        or card.find("h2") or card.find("h3") or card.find("h4"))
            title    = title_el.get_text(strip=True) if title_el else "Działka"

            price = None
            for sel in ["[class*='price']", "[class*='Price']", "[class*='cena']", "strong", "b"]:
                el = card.select_one(sel)
                if el:
                    price = parse_price(el.get_text())
                    if price:
                        break
            if not price:
                m = re.search(r"(\d[\d\s]{3,9})\s*(zł|PLN)", card.get_text())
                if m:
                    price = parse_price(m.group(1))

            img_el = card.find("img")
            images = []
            if img_el:
                src = img_el.get("data-src") or img_el.get("data-lazy") or img_el.get("src")
                if src and src.startswith("http"):
                    images = [src]

            loc_el = (card.select_one("[class*='location']") or card.select_one("[class*='locat']")
                      or card.select_one("[class*='address']") or card.select_one("[class*='city']"))
            city   = loc_el.get_text(strip=True) if loc_el else ""

            area_el = card.select_one("[class*='area']") or card.select_one("[class*='powierzch']")
            area    = parse_area(area_el.get_text() if area_el else "") or parse_area(title)

            check = f"{city} {title} {link}"
            if not is_in_location(check, location_key):
                continue

            results.append(make_item(source, location, location_key, title, price, area, city, "", images, link))
        except Exception as e:
            log.debug(f"[{source}] item: {e}")

    return results


def scrape_with_playwright(location_key, location, pw_browser):
    """Scrape portale JS: Gratka, N-online, Adresowo, Morizon."""
    results = []
    context = pw_browser.new_context(
        user_agent=HEADERS["User-Agent"],
        locale="pl-PL",
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    # Blokuj zbędne zasoby (reklamy, fonty) — szybsze ładowanie
    page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}", lambda r: r.abort())
    page.route("**/{ads,analytics,tracking,gtm,facebook,hotjar}**", lambda r: r.abort())

    portals = [
        {
            "source":   "Gratka",
            "url_key":  "gratka_url",
            "domain":   "https://gratka.pl",
            "wait_sel": "article.listing__item, [data-url], .listing-item",
            "cards":    ["article.listing__item", "[data-url]", ".listing-item", "article.offer"],
            "pages":    4,
            "page_param": "&strona=",
        },
        {
            "source":   "Nieruchomosci-online",
            "url_key":  "nieruchomosci_url",
            "domain":   "https://www.nieruchomosci-online.pl",
            "wait_sel": ".property-list-item, .offer-item, article",
            "cards":    [".property-list-item", ".offer-item", "article.property", "article"],
            "pages":    4,
            "page_param": "&p=",
        },
        {
            "source":   "Adresowo",
            "url_key":  "adresowo_url",
            "domain":   "https://adresowo.pl",
            "wait_sel": ".property-box, .offer-item, article, .listing-item",
            "cards":    [".property-box", ".offer-item", ".listing-item", "article.offer", "li.search-result"],
            "pages":    4,
            "page_param": "?strona=",
        },
        {
            "source":   "Morizon",
            "url_key":  "morizon_url",
            "domain":   "https://www.morizon.pl",
            "wait_sel": ".property-list-item, [class*='PropertyCard'], article",
            "cards":    [".property-list-item", "[class*='PropertyCard']", "[class*='offerCard']", "article"],
            "pages":    4,
            "page_param": "?page=",
        },
    ]

    for portal in portals:
        source  = portal["source"]
        base_url = location[portal["url_key"]]
        log.info(f"[{source}] {location_key} (Playwright)")

        portal_results = []

        for pg in range(1, portal["pages"] + 1):
            if pg == 1:
                url = base_url
            else:
                sep = portal["page_param"]
                url = base_url + sep + str(pg)

            html = pw_get_html(page, url, wait_selector=portal["wait_sel"], wait_ms=6000)

            if pg == 1:
                dismiss_cookie_banners(page)
                page.wait_for_timeout(500)
                html = page.content()  # odśwież po zamknięciu bannera

            items = _pw_parse_cards(html, source, location, location_key, portal["cards"], portal["domain"])
            if not items:
                log.info(f"[{source}] brak wyników str.{pg}, koniec")
                break

            portal_results.extend(items)
            log.info(f"[{source}] str.{pg}: +{len(items)}")
            sleep(2, 5)

        log.info(f"[{source}] {location_key}: {len(portal_results)}")
        results.extend(portal_results)

    page.close()
    context.close()
    return results


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    all_results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        for loc_key, loc_data in LOCATIONS.items():
            log.info(f"\n{'='*50}")
            log.info(f"LOKALIZACJA: {loc_data['label']}")
            log.info(f"{'='*50}")

            # Szybkie scrapery (requests)
            for fn in [scrape_otodom, scrape_olx, scrape_domiporta]:
                try:
                    items = fn(loc_key, loc_data)
                    all_results.extend(items)
                except Exception as e:
                    log.error(f"{fn.__name__} failed: {e}")

            # Portale JS (Playwright)
            try:
                items = scrape_with_playwright(loc_key, loc_data, browser)
                all_results.extend(items)
            except Exception as e:
                log.error(f"Playwright failed for {loc_key}: {e}")

        browser.close()

    # Deduplikacja
    seen, unique = set(), []
    for item in all_results:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    # Statystyki
    by_source   = {}
    by_location = {}
    for item in unique:
        by_source[item["source"]]         = by_source.get(item["source"], 0) + 1
        by_location[item["location_area"]] = by_location.get(item["location_area"], 0) + 1

    log.info("\n─── PODSUMOWANIE ─────────────────────")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        log.info(f"  {src}: {cnt}")
    log.info("")
    for loc, cnt in sorted(by_location.items()):
        log.info(f"  {loc}: {cnt}")
    log.info(f"  ŁĄCZNIE (unikalne): {len(unique)}")

    output = {
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "total":       len(unique),
        "by_source":   by_source,
        "by_location": by_location,
        "listings":    unique,
    }

    out_path = Path(__file__).parent.parent / "docs" / "data.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"\n✅ Zapisano {len(unique)} ofert → {out_path}")


if __name__ == "__main__":
    main()
