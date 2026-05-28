from fastapi import APIRouter, Depends

from app.dependencies import require_admin
from app.models.fund import FundBalance, FundEntry, FundEntryCreate
import app.services.fund_service as fund_service

router = APIRouter(prefix="/fund")


@router.get("/balance", response_model=FundBalance)
async def get_fund_balance(_=Depends(require_admin)):
    return fund_service.get_balance()


@router.post("/entries", response_model=FundEntry, status_code=201)
async def create_fund_entry(data: FundEntryCreate, _=Depends(require_admin)):
    return fund_service.add_entry(data)
