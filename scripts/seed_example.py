"""Seed a tiny example corpus so the system is runnable end-to-end on a laptop.

Drops a few statute excerpts + one fake judgment + one fake private matter into
data/raw so the adapters can pick them up.
"""

from __future__ import annotations

from pathlib import Path

from services.lib.core import settings


STATUTE_THEFT = """378. Theft.\u2014Whoever, intending to take dishonestly any movable
property out of the possession of any person without that person's consent,
moves that property in order to such taking, is said to commit theft.

Explanation 1.\u2014A thing so long as it is attached to the earth, not being
movable property, is not the subject of theft; but it becomes capable of being
the subject of theft as soon as it is severed from the earth.

Illustration.\u2014A cuts down a tree on Z's ground, with the intention of
dishonestly taking the tree out of Z's possession without Z's consent. Here,
as soon as A has severed the tree in order to such taking, he has committed
theft.
"""

STATUTE_MURDER = """300. Murder.\u2014Except in the cases hereinafter excepted, culpable
homicide is murder, if the act by which the death is caused is done with the
intention of causing death.

Provided that the act must be done with the intention of causing such bodily
injury as is sufficient in the ordinary course of nature to cause death.

Explanation.\u2014The mental element (mens rea) is essential.
"""

JUDGMENT_EXCERPT = """1. This appeal arises out of an FIR registered under Section 378 IPC
and Section 302 IPC.

12. The ingredients of theft under Section 378 IPC are (i) dishonest
intention, (ii) movable property, (iii) taking out of possession, (iv) without
consent, (v) moving the property in order to such taking. See State of
Maharashtra v. X, (2019) 8 SCC 100.
"""

PRIVATE_STATEMENT = """Statement of Ramesh Kumar
Ex. P-1

I saw the accused take my bicycle from my shop at 9:30 PM on 12 March 2024
without my consent. I later saw him riding it near the market at 10:00 PM.
"""


def main() -> None:
    raw = Path(settings.data_dir) / "raw"
    (raw / "india_code").mkdir(parents=True, exist_ok=True)
    (raw / "sci").mkdir(parents=True, exist_ok=True)
    (Path(settings.data_dir) / "private" / "matter_demo").mkdir(parents=True, exist_ok=True)

    (raw / "india_code" / "Indian_Penal_Code_1860_s378.txt").write_text(STATUTE_THEFT)
    (raw / "india_code" / "Indian_Penal_Code_1860_s300.txt").write_text(STATUTE_MURDER)
    (raw / "sci" / "2019_STATE_V_X.txt").write_text(JUDGMENT_EXCERPT)
    (Path(settings.data_dir) / "private" / "matter_demo" / "Ex-P-1-Statement.txt").write_text(
        PRIVATE_STATEMENT
    )

    print("Seeded example corpus under", settings.data_dir)


if __name__ == "__main__":
    main()
