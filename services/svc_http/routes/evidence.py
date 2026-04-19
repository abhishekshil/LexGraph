from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...lib.data_models.evidence import EvidencePack
from ...lib.retrieval import RetrievalOrchestrator


router = APIRouter(prefix="/evidence", tags=["evidence"])


class EvidenceRequest(BaseModel):
    question: str
    matter_scope: str | None = None
    mode: str | None = None


@router.post("", response_model=EvidencePack)
async def build_pack(body: EvidenceRequest) -> EvidencePack:
    orch = RetrievalOrchestrator()
    return await orch.answer(
        question=body.question,
        matter_scope=body.matter_scope,
        mode=body.mode,
    )
