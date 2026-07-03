import os
from datetime import datetime


def format_date_for_aviasales(date_string):
    """
    Convert date from YYYY-MM-DD to DDMM format for Aviasales URL.

    Example:
    2026-09-01 -> 0109
    """
    date_obj = datetime.strptime(date_string, "%Y-%m-%d")
    return date_obj.strftime("%d%m")


def generate_aviasales_search_url(
    origin,
    destination,
    departure_date,
    return_date=None,
    adults=1
):
    """
    Generate Aviasales affiliate search URL.

    Example one-way:
    https://www.aviasales.com/search/BUD0109TPE1?marker=xxxx

    Example round-trip:
    https://www.aviasales.com/search/BUD0109TPE20091?marker=xxxx
    """

    marker = os.getenv("TRAVELPAYOUTS_MARKER", "")

    origin = origin.upper().strip()
    destination = destination.upper().strip()

    departure_part = format_date_for_aviasales(departure_date)

    if return_date:
        return_part = format_date_for_aviasales(return_date)
        search_path = f"{origin}{departure_part}{destination}{return_part}{adults}"
    else:
        search_path = f"{origin}{departure_part}{destination}{adults}"

    base_url = "https://www.aviasales.com/search"
    url = f"{base_url}/{search_path}"

    if marker:
        url += f"?marker={marker}"

    return url
