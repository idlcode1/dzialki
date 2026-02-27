#!/usr/bin/env python3
"""
Scraper działek - Rzeszów 30km + Zakopane 20km
Portale: Otodom, OLX, Gratka, Nieruchomosci-online, Domiporta, Adresowo, Morizon

NAPRAWKI v3:
- Otodom: nowy URL /pl/wyniki/ (stary /pl/oferty/ zwracał 404)
- Gratka: poprawione selektory kart i ceny
- Nieruchomosci-online: poprawione selektory
- Domiporta: poprawione selektory
- Adresowo: poprawiony URL + selektory
- Morizon: poprawiony URL + selektory
- Dodane nagłówki Accept-Encoding + Connection dla lepszej kompatybilności
"""

import json
import time
import random
import re
import hashlib
import logging
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
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
        # Otodom — nowy format URL /pl/wyniki/
        "otodom_url":        "https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/podkarpackie/rzeszowski/rzeszow?distanceRadius=30&viewType=listing",
        "olx_url":           "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/rzeszow/?search[dist]=30",
        "gratka_url":        "https://gratka.pl/nieruchomosci/dzialki/podkarpackie?promien=30&lokalizacja_miejscowosc=Rzesz%C3%B3w&transakcja=sprzedaz",
        "nieruchomosci_url": "https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Rzesz%C3%B3w,,,30",
        "domiporta_url":     "https://www.domiporta.pl/dzialka/sprzedam/podkarpackie/rzeszowski",
        "adresowo_url":      "https://adresowo.pl/dzialki/rzeszow/",
        "morizon_url":       "https://www.morizon.pl/dzialki/rzeszow/",
    },
    "zakopane": {
        "label": "Zakopane i okolice (20 km)",
        "otodom_url":        "https://www.otodom.pl/pl/wyniki/sprzedaz/dzialka/malopolskie/tatrzanski/zakopane?distanceRadius=20&viewType=listing",
        "olx_url":           "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz/zakopane/?search[dist]=20",
        "gratka_url":        "https://gratka.pl/nieruchomosci/dzialki/malopolskie?promien=20&lokalizacja_miejscowosc=Zakopane&transakcja=sprzedaz",
        "nieruchomosci_url": "https://www.nieruchomosci-online.pl/szukaj.html?3,dzialka,sprzedaz,,Zakopane,,,20",
        "domiporta_url":     "https://www.domiporta.pl/dzialka/sprzedam/malopolskie/tatrzanski",
        "adresowo_url":      "https://adresowo.pl/dzialki/zakopane/",
        "morizon_url":       "https://www.morizon.pl/dzialki/zakopane/",
    },
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def uid(s):
    return hashlib.md5(s.encode()).hexdigest()[:12]

def sleep():
    time.sleep(random.uniform(3.0, 6.0))

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


# ─── 1. OTODOM ────────────────────────────────────────────────────────────────

def scrape_otodom(location_key, location):
    log.info(f"[Otodom] {location_key}")
    results = []
    base_url = location["otodom_url"]

    for page in range(1, 6):
        url = base_url if page == 1 else base_url + f"&page={page}"
        r = get(url, referer="https://www.otodom.pl/")
        if not r:
            break

        soup = BeautifulSoup(r.text, "html.parser")

        # Otodom renderuje przez Next.js — dane w __NEXT_DATA__
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            log.warning(f"[Otodom] brak __NEXT_DATA__ na stronie {page}")
            break

        try:
            data = json.loads(script.string)
            # Nowa struktura: props.pageProps.data.searchAds.items
            # lub props.pageProps.listing.results
            items = (
                data.get("props", {}).get("pageProps", {})
                    .get("data", {}).get("searchAds", {}).get("items", [])
                or
                data.get("props", {}).get("pageProps", {})
                    .get("listing", {}).get("results", [])
            )
        except Exception as e:
            log.warning(f"[Otodom] JSON parse: {e}")
            break

        if not items:
            log.info(f"[Otodom] brak wyników na stronie {page}, koniec")
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
                    src = (img.get("large") or img.get("medium") or
                           img.get("small") or img.get("src") or
                           (img if isinstance(img, str) else None))
                    if src:
                        images.append(src)

                slug = item.get("slug") or item.get("id", "")
                link = f"https://www.otodom.pl/pl/oferta/{slug}" if slug else ""

                loc = item.get("locationLabel") or item.get("location") or {}
                city = (loc.get("value") or loc.get("name") or
                        item.get("city", "")) if isinstance(loc, dict) else str(loc)

                check_text = f"{city} {item.get('title', '')} {link}"
                if not is_in_location(check_text, location_key):
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


# ─── 2. OLX ──────────────────────────────────────────────────────────────────

def scrape_olx(location_key, location):
    log.info(f"[OLX] {location_key}")
    results = []

    for page in range(1, 6):
        url = location["olx_url"] + f"&page={page}"
        r = get(url, referer="https://www.olx.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("[data-cy='l-card']")
        if not cards:
            break

        for card in cards:
            try:
                a = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://www.olx.pl" + link

                title_el = card.select_one("[data-cy='ad-card-title']") or card.find("h6")
                title = title_el.get_text(strip=True) if title_el else "Działka"

                price_el = card.select_one("[data-testid='ad-price']") or card.find(class_=re.compile("price"))
                price = parse_price(price_el.get_text() if price_el else "")

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("src")
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = card.select_one("[data-testid='location-date']") or card.find(class_=re.compile("location"))
                city = loc_el.get_text(strip=True).split("-")[0].strip() if loc_el else ""

                check_text = f"{city} {title}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("OLX", location, location_key, title, price, None, city, "", images, link))
            except Exception as e:
                log.debug(f"[OLX] item: {e}")
        sleep()

    log.info(f"[OLX] {location_key}: {len(results)}")
    return results


# ─── 3. GRATKA ───────────────────────────────────────────────────────────────

def scrape_gratka(location_key, location):
    log.info(f"[Gratka] {location_key}")
    results = []

    for page in range(1, 6):
        url = location["gratka_url"] + f"&strona={page}" if page > 1 else location["gratka_url"]
        r = get(url, referer="https://gratka.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")

        # Gratka używa article z klasą "listing__item" lub "offer"
        cards = (soup.select("article.listing__item") or
                 soup.select("article.offer") or
                 soup.select("[data-url]") or
                 soup.select(".listing-item"))
        if not cards:
            log.warning(f"[Gratka] brak kart na stronie {page}")
            break

        for card in cards:
            try:
                link = card.get("data-url") or ""
                if not link:
                    a = card.find("a", href=True)
                    link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://gratka.pl" + link

                title_el = card.find("h2") or card.find("h3") or card.select_one("[class*='title']")
                title = title_el.get_text(strip=True) if title_el else "Działka"

                # Gratka: cena w .price__value lub .listing__price lub span z ceną
                price = None
                for sel in [".price__value", ".listing__price", "[class*='price']", "[class*='cena']"]:
                    el = card.select_one(sel)
                    if el:
                        price = parse_price(el.get_text())
                        if price:
                            break

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("data-lazy") or img_el.get("src")
                    if src and ("http" in src):
                        images = [src]

                loc_el = (card.select_one(".listing__location") or
                          card.select_one("[class*='location']") or
                          card.select_one("[class*='locat']"))
                city = loc_el.get_text(strip=True) if loc_el else ""
                area = parse_area(title)

                check_text = f"{city} {title} {link}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("Gratka", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[Gratka] item: {e}")
        sleep()

    log.info(f"[Gratka] {location_key}: {len(results)}")
    return results


# ─── 4. NIERUCHOMOSCI-ONLINE ─────────────────────────────────────────────────

def scrape_nieruchomosci_online(location_key, location):
    log.info(f"[Nieruchomosci-online] {location_key}")
    results = []

    for page in range(1, 6):
        url = location["nieruchomosci_url"] + f"&p={page}" if page > 1 else location["nieruchomosci_url"]
        r = get(url, referer="https://www.nieruchomosci-online.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")

        cards = (soup.select(".property-list-item") or
                 soup.select("article.property") or
                 soup.select(".offer-item") or
                 soup.select("[class*='offer']"))
        if not cards:
            log.warning(f"[N-online] brak kart na stronie {page}")
            break

        for card in cards:
            try:
                a = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://www.nieruchomosci-online.pl" + link

                title_el = card.find("h2") or card.find("h3") or card.select_one("[class*='title']")
                title = title_el.get_text(strip=True) if title_el else "Działka"

                price = None
                for sel in ["[class*='price']", "[class*='cena']", "strong", "b"]:
                    el = card.select_one(sel)
                    if el:
                        price = parse_price(el.get_text())
                        if price:
                            break

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("src")
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = card.select_one("[class*='location']") or card.select_one("[class*='address']")
                city = loc_el.get_text(strip=True) if loc_el else ""
                area = parse_area(title)

                check_text = f"{city} {title} {link}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("Nieruchomosci-online", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[N-online] item: {e}")
        sleep()

    log.info(f"[Nieruchomosci-online] {location_key}: {len(results)}")
    return results


# ─── 5. DOMIPORTA ─────────────────────────────────────────────────────────────

def scrape_domiporta(location_key, location):
    log.info(f"[Domiporta] {location_key}")
    results = []

    for page in range(1, 6):
        base = location["domiporta_url"]
        url = base if page == 1 else base + f"?PageNumber={page}"
        r = get(url, referer="https://www.domiporta.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")

        cards = (soup.select(".sneakpeak") or
                 soup.select("li.listing__item") or
                 soup.select(".listing-item") or
                 soup.select("article"))
        if not cards:
            log.warning(f"[Domiporta] brak kart na stronie {page}")
            break

        for card in cards:
            try:
                a = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://www.domiporta.pl" + link

                title_el = (card.select_one(".sneakpeak__title") or
                            card.select_one("[class*='title']") or
                            card.find("h2") or card.find("h3"))
                title = title_el.get_text(strip=True) if title_el else "Działka"

                price_el = (card.select_one(".sneakpeak__price") or
                            card.select_one("[class*='price']") or
                            card.select_one("[class*='cena']"))
                price = parse_price(price_el.get_text() if price_el else "")

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("data-lazy") or img_el.get("src")
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = (card.select_one(".sneakpeak__location") or
                          card.select_one("[class*='location']"))
                city = loc_el.get_text(strip=True) if loc_el else ""
                area = parse_area(card.select_one("[class*='area']").get_text() if card.select_one("[class*='area']") else "") or parse_area(title)

                check_text = f"{city} {title} {link}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("Domiporta", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[Domiporta] item: {e}")
        sleep()

    log.info(f"[Domiporta] {location_key}: {len(results)}")
    return results


# ─── 6. ADRESOWO ─────────────────────────────────────────────────────────────

def scrape_adresowo(location_key, location):
    log.info(f"[Adresowo] {location_key}")
    results = []

    for page in range(1, 6):
        base = location["adresowo_url"]
        url = base if page == 1 else base + f"?strona={page}"
        r = get(url, referer="https://adresowo.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")

        # Adresowo może mieć różne selektory — próbujemy kilka
        cards = (soup.select(".property-box") or
                 soup.select(".offer-item") or
                 soup.select("[data-property-id]") or
                 soup.select("article.offer") or
                 soup.select(".listing-item") or
                 soup.select("li.search-result"))
        if not cards:
            log.warning(f"[Adresowo] brak kart na stronie {page}")
            # Wypisz fragment HTML żeby zrozumieć strukturę
            log.debug(f"[Adresowo] HTML snippet: {str(soup.body)[:500] if soup.body else 'brak body'}")
            break

        for card in cards:
            try:
                a = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://adresowo.pl" + link

                title_el = (card.select_one("[class*='title']") or
                            card.select_one("[class*='name']") or
                            card.find("h2") or card.find("h3"))
                title = title_el.get_text(strip=True) if title_el else "Działka"

                # Adresowo — próbuj data-price, potem CSS klasy, potem regex
                price = None
                for el in [card] + list(card.find_all(True))[:20]:
                    for attr in ["data-price", "data-value", "data-cost"]:
                        val = el.get(attr)
                        if val:
                            price = parse_price(val)
                            if price:
                                break
                    if price:
                        break

                if not price:
                    for sel in ["[class*='price']", "[class*='cena']", "[class*='cost']", "strong"]:
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
                    src = (img_el.get("data-src") or img_el.get("data-lazy") or
                           img_el.get("data-original") or img_el.get("src"))
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = (card.select_one("[class*='location']") or
                          card.select_one("[class*='address']") or
                          card.select_one("[class*='city']"))
                city = loc_el.get_text(strip=True) if loc_el else ""

                area = None
                for sel in ["[class*='area']", "[class*='powierzch']", "[class*='size']"]:
                    el = card.select_one(sel)
                    if el:
                        area = parse_area(el.get_text())
                        if area:
                            break
                if not area:
                    area = parse_area(title)

                check_text = f"{city} {title} {link}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("Adresowo", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[Adresowo] item: {e}")
        sleep()

    log.info(f"[Adresowo] {location_key}: {len(results)}")
    return results


# ─── 7. MORIZON ──────────────────────────────────────────────────────────────

def scrape_morizon(location_key, location):
    log.info(f"[Morizon] {location_key}")
    results = []

    for page in range(1, 6):
        base = location["morizon_url"]
        url = base if page == 1 else base + f"?page={page}"
        r = get(url, referer="https://www.morizon.pl/")
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")

        cards = (soup.select(".property-list-item") or
                 soup.select("[class*='PropertyCard']") or
                 soup.select("[class*='offerCard']") or
                 soup.select(".listing-item") or
                 soup.select("[data-item-id]") or
                 soup.select("article"))
        if not cards:
            log.warning(f"[Morizon] brak kart na stronie {page}")
            break

        for card in cards:
            try:
                a = card.find("a", href=True)
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://www.morizon.pl" + link

                title_el = (card.select_one("[class*='title']") or
                            card.select_one("[class*='Title']") or
                            card.find("h2") or card.find("h3"))
                title = title_el.get_text(strip=True) if title_el else "Działka"

                price_el = (card.select_one("[class*='price']") or
                            card.select_one("[class*='Price']") or
                            card.select_one("[class*='cena']"))
                price = parse_price(price_el.get_text() if price_el else "")

                img_el = card.find("img")
                images = []
                if img_el:
                    src = img_el.get("data-src") or img_el.get("src")
                    if src and src.startswith("http"):
                        images = [src]

                loc_el = (card.select_one("[class*='location']") or
                          card.select_one("[class*='Location']") or
                          card.select_one("[class*='address']"))
                city = loc_el.get_text(strip=True) if loc_el else ""

                area_el = (card.select_one("[class*='area']") or
                           card.select_one("[class*='Area']") or
                           card.select_one("[class*='powierzch']"))
                area = parse_area(area_el.get_text() if area_el else "") or parse_area(title)

                check_text = f"{city} {title} {link}"
                if not is_in_location(check_text, location_key):
                    continue

                results.append(make_item("Morizon", location, location_key, title, price, area, city, "", images, link))
            except Exception as e:
                log.debug(f"[Morizon] item: {e}")
        sleep()

    log.info(f"[Morizon] {location_key}: {len(results)}")
    return results


# ─── MAIN ─────────────────────────────────────────────────────────────────────

ALL_SCRAPERS = [
    scrape_otodom,
    scrape_olx,
    scrape_gratka,
    scrape_nieruchomosci_online,
    scrape_domiporta,
    scrape_adresowo,
    scrape_morizon,
]

def main():
    all_results = []

    for loc_key, loc_data in LOCATIONS.items():
        log.info(f"\n{'='*50}")
        log.info(f"LOKALIZACJA: {loc_data['label']}")
        log.info(f"{'='*50}")
        for fn in ALL_SCRAPERS:
            try:
                items = fn(loc_key, loc_data)
                all_results.extend(items)
            except Exception as e:
                log.error(f"{fn.__name__} failed for {loc_key}: {e}")

    # Deduplikacja
    seen, unique = set(), []
    for item in all_results:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    # Statystyki
    by_source = {}
    by_location = {}
    for item in unique:
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
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
