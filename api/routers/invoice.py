from fastapi import APIRouter, HTTPException
from uuid import uuid4
from typing import Annotated, Any, Dict, Literal, ClassVar, List
from pydantic import BaseModel, Field, UUID4, field_validator
from datetime import date, datetime
from logging import DEBUG

from starlette import status

from ..auth import get_current_active_user, Depends, User
from ..dependencies import logger, cache_db, push_job, ResponseState, JobStateRequest, Product

logger.setLevel(DEBUG)
logger.name = __name__

router = APIRouter(
    prefix="/invoice",
    tags=["invoice"],
    dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Invalid request endpoint"},
        403: {"description": "Not authorized"},
        500: {"description": "Internal Server Error"},
    },
)

INVOICE_STATE_KEY_PREFIX = 'invoice'
INVOICES_ACTUAL_KEY_PREFIX = 'actual_invoices'


class Requisites(BaseModel):
    signer_name: str
    signer_position: str = None
    company_name: str
    vat: str = None
    zip: str = None
    country: str = None
    region: str = None
    city: str = None
    street: str = None
    email: str = None
    phone: str = None
    notes: str = None


class InvoiceLine(Product):
    name: str
    price: float
    amount: float
    tax: float


class Invoice(BaseModel):
    uuid: UUID4
    reference: str
    issue_date: str
    deadline_date: str
    requisites: Requisites
    invoice_lines: List[InvoiceLine]
    amount_total: float
    amount_tax: float


class InvoiceList(BaseModel):
    actual_invoices: List[Invoice]


class InvoiceIssueRequest(BaseModel):
    date_start: str
    date_end: str
    include_invoice_file: bool = False

    @field_validator("date_start", "date_end", mode='before', check_fields=False)
    @classmethod
    def string_to_date(cls, v: Any) -> Any:
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date().strftime("%Y-%m-%d")
        raise ValueError('Incorrect date format, use pattern %Y-%m-%d')


@router.post("/issue")
async def issue_invoice(
        invoice_request: InvoiceIssueRequest,
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> ResponseState:

    response = ResponseState(state='enqueued')

    payload = {
        "uuid": str(response.uuid),
        "partner_id": current_user.partner_id,
        **invoice_request.dict()
    }
    logger.info(f"ISSUE INVOICE PAYLOAD: {payload}")
    # create and push job to queue
    try:
        push_job(payload=payload, actor_name='issue_invoice', queue_name='invoice')
        return response
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot process request: {str(e)}")


@router.post("/actual")
async def actual_invoices(
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> InvoiceList | ResponseState:
    invoices_key = f"{INVOICES_ACTUAL_KEY_PREFIX}:{current_user.partner_id}"
    logger.info(f"Invoices list redis key: {invoices_key}")
    invoices_data = cache_db.get(invoices_key)
    logger.info(f"Got invoices data: {invoices_data}")
    if invoices_data is not None:
        invoices_response = InvoiceList(**invoices_data)
        logger.info(f"Prepared response: {invoices_response}")
        # drop record from db
        cache_db.delete(invoices_key)
        # return data
        return invoices_response
    payload = {
        "uuid": str(uuid4()),
        "partner_id": current_user.partner_id,
    }
    logger.info(f"TRANSFER PAYLOAD: {payload}")
    # create and push job to queue
    try:
        push_job(payload=payload, actor_name='actual_invoices', queue_name='invoice')
        return ResponseState(uuid=payload.get('uuid'), state='enqueued')
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot process request: {str(e)}")


@router.post("/state")
async def invoice_state(
        job: JobStateRequest,
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> ResponseState:
    pass
