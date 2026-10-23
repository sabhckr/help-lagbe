"""National helplines shown on the site. These are public numbers, not organisations verified by staff.

Each entry names its source and the date it was checked. A number is added only after a source
confirms it. 1098 (child helpline) is deliberately absent until an official source confirms it.
"""

from __future__ import annotations

CHECKED_ON = {"en": "23 Oct 2026", "bn": "২৩ অক্টোবর ২০২৬"}

NATIONAL = (
    {
        "number": "999",
        "name_en": "National emergency service",
        "name_bn": "জাতীয় জরুরি সেবা",
        "for_en": "Police, fire and ambulance. For immediate danger.",
        "for_bn": "এখনই বিপদ হলে পুলিশ, ফায়ার সার্ভিস বা অ্যাম্বুলেন্সের জন্য।",
        "source": "https://www.thedailystar.net/toggle/news/helpline-numbers-location-sharing-apps-and-services-you-may-need-emergency-1978905",
    },
    {
        "number": "109",
        "name_en": "Violence against women and children helpline",
        "name_bn": "নারী ও শিশু নির্যাতন প্রতিরোধ হেল্পলাইন",
        "for_en": "Harassment or abuse on the street or at home.",
        "for_bn": "ঘরে বা বাইরে নারী বা শিশুর ওপর হয়রানি বা নির্যাতন হলে।",
        "source": "https://findahelpline.com/organizations/national-helpline-109",
    },
)


def national_for_display() -> tuple[dict, ...]:
    return NATIONAL
