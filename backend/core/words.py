"""Number-to-words conversion in international (Western) format.
Handles up to 999 trillion. Used for PI 'Amount in Words'.
"""

_ONES = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
_SCALE = [(10**12, "Trillion"), (10**9, "Billion"), (10**6, "Million"), (10**3, "Thousand")]

CURRENCY_MAJOR = {
    "USD": "Dollars",
    "EUR": "Euros",
    "GBP": "Pounds",
    "AED": "Dirhams",
    "INR": "Rupees",
}
CURRENCY_MINOR = {
    "USD": "Cents",
    "EUR": "Cents",
    "GBP": "Pence",
    "AED": "Fils",
    "INR": "Paise",
}


def _under_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else f" {_ONES[n % 10]}")
    return _ONES[n // 100] + " Hundred" + ("" if n % 100 == 0 else f" {_under_thousand(n % 100)}")


def number_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    if n < 0:
        return f"Minus {number_to_words(-n)}"
    parts = []
    for value, name in _SCALE:
        if n >= value:
            chunk = n // value
            n = n % value
            parts.append(f"{_under_thousand(chunk)} {name}")
    if n > 0:
        parts.append(_under_thousand(n))
    return " ".join(parts).strip()


def amount_in_words(amount: float, currency: str = "USD") -> str:
    major = CURRENCY_MAJOR.get(currency, currency)
    minor = CURRENCY_MINOR.get(currency, "Cents")
    whole = int(amount)
    cents = round((amount - whole) * 100)
    txt = f"{number_to_words(whole)} {major}"
    if cents > 0:
        txt += f" and {number_to_words(cents)} {minor}"
    return txt + " Only"
