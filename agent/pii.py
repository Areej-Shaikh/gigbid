"""PII masking (R9, E4): one function used by the audit log AND the trace exporter, so emails, phone numbers
and payment details never reach logs or traces. Order matters: card / IBAN before the generic phone rule."""
import re

IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?<![\w-])\+?\d[\d\s().-]{7,}\d(?![\w-])")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACCOUNT = re.compile(r"(?i)\b(account|acct|routing|sort code|swift|bic)(\s*(?:no\.?|number|#|code))?\s*[:#]?\s*[A-Z0-9-]{4,}")


def _phone(m: re.Match) -> str:
    s = m.group(0)
    if DATE.match(s.strip()) or len(re.sub(r"\D", "", s)) < 9:     # dates and short numbers are not phones
        return s
    return "[phone]"


def mask(text: str) -> str:
    text = IBAN.sub("[iban]", text)
    text = CARD.sub("[card]", text)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub(_phone, text)
    return ACCOUNT.sub(lambda m: f"{m.group(1)} [masked]", text)
