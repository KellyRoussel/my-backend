"""Client for OpenFigi API — ISIN to ticker conversion."""
import requests

from config import settings

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

# OpenFigi exchCode → Yahoo Finance suffix
# US exchanges have no suffix (empty string = no suffix needed)
_EXCH_CODE_TO_YAHOO_SUFFIX: dict[str, str] = {
    # US
    "US": "", "UN": "", "UQ": "", "UA": "", "UV": "",
    # Europe
    "FP": ".PA",   # Euronext Paris
    "LN": ".L",    # London
    "GY": ".DE",   # XETRA
    "NA": ".AS",   # Euronext Amsterdam
    "BB": ".BR",   # Euronext Brussels
    "IM": ".MI",   # Borsa Italiana (Milan)
    "SM": ".MC",   # Madrid
    "SW": ".SW",   # SIX Swiss Exchange
    "SS": ".ST",   # Stockholm
    "DC": ".CO",   # Copenhagen
    "FH": ".HE",   # Helsinki
    "NO": ".OL",   # Oslo
    "VX": ".SW",   # Zurich (virt-x)
    "AU": ".AX",   # Australia
    "HK": ".HK",   # Hong Kong
    "JP": ".T",    # Tokyo
}


class OpenFigiClient:
    @staticmethod
    def isin_to_ticker(isin: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "X-OPENFIGI-APIKEY": settings.openfigi_api_key,
        }

        payload = [{
            "idType": "ID_ISIN",
            "idValue": isin,
        }]

        response = requests.post(OPENFIGI_URL, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()[0].get("data", [])
        if not data:
            raise ValueError(f"No instrument found for ISIN {isin}")

        # Prefer US listings (no suffix, most reliable on Yahoo Finance).
        # Otherwise pick the first instrument with a known exchange mapping.
        us_codes = {"US", "UN", "UQ", "UA", "UV"}
        us_instrument = next((i for i in data if i.get("exchCode") in us_codes), None)
        instrument = us_instrument or data[0]

        ticker = instrument.get("ticker", "")
        exch_code = instrument.get("exchCode", "")
        suffix = _EXCH_CODE_TO_YAHOO_SUFFIX.get(exch_code, "")

        return f"{ticker}{suffix}" if ticker else ""
