from fastapi import APIRouter, HTTPException
from uuid import uuid4
from typing import Annotated, Any, Dict, Literal, ClassVar, List
from pydantic import BaseModel, Field, UUID4, field_validator
from datetime import date, datetime
from logging import DEBUG
from ..auth import get_current_active_user, Depends, User
from ..dependencies import logger, cache_db, push_job

logger.setLevel(DEBUG)
logger.name = __name__

router = APIRouter(
    prefix="/transfer",
    tags=["transfer", "inbound"],
    dependencies=[Depends(get_current_active_user)],
    responses={
        404: {"description": "Invalid request endpoint"},
        403: {"description": "Not authorized"},
        500: {"description": "Internal Server Error"},
    },
)


fake_items_db = {"plumbus": {"name": "Plumbus"}, "gun": {"name": "Portal Gun"}}


class ResponseMessage(BaseModel):
    uuid: UUID4 = None
    message: str = None


class ResponseTransferStateMessage(ResponseMessage):
    state: str = None


class Job(BaseModel):
    uuid: UUID4 = Field(default_factory=uuid4)
    client: str = None
    # channel: Literal['inbound', 'outbound']
    payload: Dict[str, Any] = None


class Transfer(BaseModel):
    # channel: Literal['inbound', 'outbound']
    reference: str
    representative_name: str = None
    representative_tel: str = None
    products: List[Any]

    @field_validator("inbound_date", "outbound_date", mode='before', check_fields=False)
    @classmethod
    def string_to_date(cls, v: Any) -> Any:
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date().strftime("%Y-%m-%d")
        raise ValueError('Incorrect date format')


class InboundProduct(BaseModel):
    default_code: str
    barcode: str = None
    name: str
    description: str = None
    quantity: int
    price: float


class InboundTransfer(Transfer):
    # channel: str = 'inbound'
    inbound_date: str
    products: List[InboundProduct]


@router.get("/test")
async def read_items():
    return fake_items_db


@router.post("/inbound")
async def create_inbound(
        transfer: InboundTransfer,
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> ResponseTransferStateMessage:

    payload = {
        "uuid": str(uuid4()),
        "partner_id": current_user.partner_id,
        **transfer.dict()
    }
    logger.info(f"TRANSFER PAYLOAD: {payload}")
    # create and push job to queue
    try:
        push_job(payload=payload, actor_name='create_inbound_order', queue_name='inbound')
        return ResponseTransferStateMessage(uuid=payload.get('uuid'), state='accepted', message="Inbound order enqueued")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot process request: {str(e)}")


# @router.post("/outbound")
# async def create_outbound(outbound: Transfer) -> Job:
#
#     print(outbound)
#     return Job(uuid="UUID", message="Outbound Transfer added to processing queue")
#
