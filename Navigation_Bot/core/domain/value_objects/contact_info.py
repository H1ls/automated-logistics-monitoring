from dataclasses import dataclass


@dataclass(slots=True)
class ContactInfo:
    full_name: str = ""
    phone: str = ""