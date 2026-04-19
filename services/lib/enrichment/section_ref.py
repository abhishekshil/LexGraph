"""Extract references to statutory sections like 'Section 302 IPC' or 'S.173(2) CrPC'."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Known short names + aliases. Keep central so crosswalk can hop across them.
ACT_ALIASES: dict[str, str] = {
    "IPC": "Indian Penal Code, 1860",
    "INDIAN PENAL CODE": "Indian Penal Code, 1860",
    "BNS": "Bharatiya Nyaya Sanhita, 2023",
    "CRPC": "Code of Criminal Procedure, 1973",
    "CR.P.C.": "Code of Criminal Procedure, 1973",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "IEA": "Indian Evidence Act, 1872",
    "EVIDENCE ACT": "Indian Evidence Act, 1872",
    "BSA": "Bharatiya Sakshya Adhiniyam, 2023",
    "CONSTITUTION": "Constitution of India",
    "ARTICLE": "Constitution of India",
    "ART": "Constitution of India",
}


SECTION_RE = re.compile(
    r"""
    (?:
        (?:Section|Sec\.?|S\.)\s*
        (?P<num>\d+[A-Za-z]?)
        (?:\s*\(\s*(?P<sub>\d+[A-Za-z]?)\s*\))?
        (?:\s+of)?\s+
        (?P<act>
            (?:IPC|CrPC|Cr\.P\.C\.?|BNS|BNSS|IEA|BSA)
          | [A-Z][A-Za-z\.\&\-\s]*?(?:Code|Act|Sanhita|Adhiniyam)
        )
    )
    |
    (?:
        (?:Article|Art\.)\s*
        (?P<art>\d+[A-Za-z]?)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass
class SectionRef:
    raw: str
    act: str
    act_alias: str | None
    section: str | None
    subsection: str | None
    start: int
    end: int
    is_article: bool = False


def extract_section_refs(text: str) -> list[SectionRef]:
    out: list[SectionRef] = []
    for m in SECTION_RE.finditer(text):
        if m.group("art"):
            out.append(
                SectionRef(
                    raw=m.group(0),
                    act="Constitution of India",
                    act_alias="Article",
                    section=m.group("art"),
                    subsection=None,
                    start=m.start(),
                    end=m.end(),
                    is_article=True,
                )
            )
            continue
        act_raw = (m.group("act") or "").strip()
        alias_key = re.sub(r"[^A-Z]", "", act_raw.upper())
        act_norm = ACT_ALIASES.get(act_raw.upper(), ACT_ALIASES.get(alias_key, act_raw))
        out.append(
            SectionRef(
                raw=m.group(0),
                act=act_norm,
                act_alias=act_raw,
                section=m.group("num"),
                subsection=m.group("sub"),
                start=m.start(),
                end=m.end(),
            )
        )
    return out
