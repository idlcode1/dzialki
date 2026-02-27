# 🏡 Działki PL — Scraper + Aplikacja webowa

Automatyczny scraper ogłoszeń działek z portali Otodom, OLX, Gratka i Nieruchomosci-online dla okolic **Rzeszowa (30 km)** i **Zakopanego (20 km)**.  
Dane aktualizowane co 12 godzin przez **GitHub Actions**, wyświetlane przez **GitHub Pages**.

---

## 🚀 Instalacja krok po kroku

### 1. Utwórz repozytorium na GitHub

1. Zaloguj się na [github.com](https://github.com)
2. Kliknij **"New repository"**
3. Nazwa: `dzialki-scraper` (lub dowolna)
4. Ustaw jako **Public** (wymagane dla darmowego GitHub Pages)
5. Kliknij **"Create repository"**

### 2. Wgraj pliki

Możesz to zrobić przez interfejs GitHub (przeciągnij i upuść pliki) lub przez terminal:

```bash
git clone https://github.com/TWÓJ_LOGIN/dzialki-scraper.git
cd dzialki-scraper

# Skopiuj wszystkie pliki z tego archiwum do katalogu
# Następnie:
git add .
git commit -m "Pierwszy commit"
git push
```

### 3. Włącz GitHub Pages

1. W repozytorium przejdź do **Settings** → **Pages**
2. W sekcji **"Source"** wybierz **"Deploy from a branch"**
3. Branch: `main`, Folder: `/docs`
4. Kliknij **Save**
5. Po chwili Twoja aplikacja będzie dostępna pod adresem:
   `https://TWÓJ_LOGIN.github.io/dzialki-scraper/`

### 4. Uruchom pierwsze scrapowanie ręcznie

1. Przejdź do **Actions** w repozytorium
2. Kliknij **"Scrape Działki"** po lewej
3. Kliknij **"Run workflow"** → **"Run workflow"**
4. Poczekaj ~5 minut
5. Odśwież stronę aplikacji — pojawią się pierwsze oferty! 🎉

---

## ⏰ Harmonogram automatyczny

Scraper uruchamia się automatycznie:
- **08:00** czasu polskiego (6:00 UTC)
- **20:00** czasu polskiego (18:00 UTC)

Możesz zmienić godziny w pliku `.github/workflows/scrape.yml` (format cron UTC).

---

## 📁 Struktura projektu

```
dzialki-scraper/
├── .github/
│   └── workflows/
│       └── scrape.yml        # Harmonogram GitHub Actions
├── scraper/
│   ├── scraper.py            # Główny skrypt scrapujący
│   └── requirements.txt      # Zależności Pythona
└── docs/                     # GitHub Pages
    ├── index.html            # Aplikacja webowa
    └── data.json             # Dane ofert (generowane automatycznie)
```

---

## 🔧 Dostosowanie lokalizacji

W pliku `scraper/scraper.py` znajdź sekcję `LOCATIONS` i zmodyfikuj według potrzeb.
Możesz zmienić promień wyszukiwania lub dodać nowe miasta.

---

## ⚠️ Uwagi

- Portale mogą zmieniać strukturę HTML — scraper może wymagać aktualizacji
- Zbyt częste scraping może skutkować tymczasowym blokowaniem IP
- Upewnij się, że scraping jest zgodny z regulaminami portali
