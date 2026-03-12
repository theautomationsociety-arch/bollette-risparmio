"""
scraper.py — Scraping automatico rimosso.

Il caricamento delle offerte avviene tramite:
  - Pannello admin → "Da PDF"  (POST /api/admin/offerte/da-pdf)
  - Pannello admin → "Da URL"  (POST /api/admin/offerte/da-url)
  - Pannello admin → "+ Aggiungi" (POST /api/admin/offerte/{tipo})

Le funzioni esportate sono stub no-op per compatibilità con main.py.
"""


def stato_scraper() -> dict:
    return {
        "in_corso": False,
        "ultimo_run": None,
        "offerte_trovate": 0,
        "offerte_inserite": 0,
        "offerte_aggiornate": 0,
        "errori": [],
        "log": [],
        "auto_ogni_ore": 0,
        "fonti_consecutive_fallite": 0,
    }


async def esegui_scraping(get_db, gemini_api_key: str) -> dict:
    """No-op: scraping automatico disabilitato."""
    return {"inserite": 0, "aggiornate": 0, "errori": [], "log": []}


def avvia_scheduler(get_db, gemini_api_key: str, ore: int) -> None:
    """No-op: scheduler disabilitato."""
    pass
