from __future__ import annotations

from services.lib.data_models.metadata import DocumentKind
from services.lib.normalization.private_segmenter import segment_private


FIR_TEXT = """\
FIR No. 123/2024
Police Station: Connaught Place

Sections: 378, 379 IPC

Complainant: John Doe
Accused: Jane Roe

Brief facts: On 01/05/2024, the complainant alleges that the accused
dishonestly took his wallet from his pocket while travelling in a metro...
"""


CONTRACT_TEXT = """\
MASTER SERVICES AGREEMENT

"Service" means the software-as-a-service platform made available by the Company.

1. Definitions
1.1 The terms in quotation marks shall have the meanings assigned below.

2. Services
2.1 The Company shall provide the Services as described in Schedule A.
2.2 Availability targets are set out in Schedule B.

SCHEDULE A — Service Catalogue
Service 1: Core Platform
Service 2: API Access
"""


CHARGESHEET_TEXT = """\
CHARGE-SHEET under Section 173 CrPC

Sections 378, 379 IPC

Accused No. 1: Rahul Sharma, aged 28
Accused No. 2: Priya Verma, aged 25

PW-1: Inspector A.K. Singh (Investigating Officer)
PW-2: Dr. Meera Das (medical expert)
DW-1: Suresh Kumar (defence witness)

Facts disclosed by the investigation...
"""


def test_fir_segmenter_captures_header_and_narrative():
    segs = segment_private(FIR_TEXT, [(0, len(FIR_TEXT))], doc_kind=DocumentKind.FIR)
    assert len(segs) >= 1
    header = segs[0]
    assert header.extra.get("fir_number") == "123/2024"
    assert "378" in str(header.extra.get("offence_sections", ""))


def test_contract_segmenter_captures_clauses_and_schedule():
    segs = segment_private(
        CONTRACT_TEXT, [(0, len(CONTRACT_TEXT))], doc_kind=DocumentKind.CONTRACT
    )
    clauses = [s for s in segs if s.node_type == "ContractClause"]
    definitions = [s for s in clauses if s.extra.get("role") == "definition"]
    assert len(definitions) >= 1
    assert any(s.label.startswith("Clause 1") for s in clauses)
    schedules = [s for s in segs if s.extra.get("role") == "schedule"]
    assert len(schedules) >= 1


def test_chargesheet_segmenter_captures_accused_and_witnesses():
    segs = segment_private(
        CHARGESHEET_TEXT,
        [(0, len(CHARGESHEET_TEXT))],
        doc_kind=DocumentKind.CHARGESHEET,
    )
    accused = [s for s in segs if s.node_type == "Party"]
    witnesses = [s for s in segs if s.node_type == "Witness"]
    assert len(accused) >= 2
    assert len(witnesses) >= 3
    # at least one PW and one DW
    witness_types = {s.extra.get("witness_type") for s in witnesses}
    assert "PW" in witness_types
    assert "DW" in witness_types
