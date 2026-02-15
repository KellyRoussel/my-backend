"""Client for OpenFigi API — ISIN to ticker conversion."""
import requests

from config import settings

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


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

        instrument = data[0]
        return instrument.get("ticker", "")
