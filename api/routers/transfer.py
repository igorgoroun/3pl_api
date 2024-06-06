from fastapi import APIRouter, HTTPException
from uuid import uuid4
from typing import Annotated, Any, Dict, Literal, ClassVar, List
from pydantic import BaseModel, Field, UUID4, field_validator
from datetime import date, datetime
from logging import DEBUG
from ..auth import get_current_active_user, Depends, User
from ..dependencies import logger, cache_db, push_job, ResponseMessage, JobStateRequest, Product

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

TRANSFER_KEY_PREFIX = 'order'

fake_items_db = {"plumbus": {"name": "Plumbus"}, "gun": {"name": "Portal Gun"}}


class ResponseTransferStateMessage(ResponseMessage):
    state: str = None


class Transfer(BaseModel):
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


class InboundProduct(Product):
    name: str
    description: str = None
    price: float


class InboundTransfer(Transfer):
    inbound_date: str
    products: List[InboundProduct]


class OutboundTransfer(Transfer):
    outbound_date: str
    products: List[Product]
    packaging: bool = False



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


@router.post("/outbound")
async def create_outbound(
        transfer: OutboundTransfer,
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> ResponseTransferStateMessage:

    payload = {
        "uuid": str(uuid4()),
        "partner_id": current_user.partner_id,
        **transfer.dict()
    }
    logger.info(f"OUT TRANSFER PAYLOAD: {payload}")
    # create and push job to queue
    try:
        push_job(payload=payload, actor_name='create_outbound_order', queue_name='outbound')
        return ResponseTransferStateMessage(uuid=payload.get('uuid'), state='accepted', message="Outbound order enqueued")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot process request: {str(e)}")


@router.post("/state")
async def transfer_state(
        job: JobStateRequest,
        current_user: Annotated[User, Depends(get_current_active_user)]
) -> ResponseTransferStateMessage:
    # case 1. Try to find existed state record in redis
    record_key = f"{TRANSFER_KEY_PREFIX}:{str(job.uuid)}"
    logger.info(f"Job redis key: {record_key}")
    user_data = cache_db.get(record_key)
    logger.info(f"Got data: {user_data}")
    if user_data is not None:
        # prepare response from existed data
        transfer_state_response = ResponseTransferStateMessage(**user_data)
        logger.info(f"Prepared response: {transfer_state_response}")
        # drop record from db
        cache_db.delete(record_key)
        # return data
        return transfer_state_response
    # case 2. if no data were found, send a job to queue to prepare state of order
    payload = {
        "uuid": str(job.uuid),
        "partner_id": current_user.partner_id
    }
    try:
        push_job(payload=payload, actor_name='transfer_state', queue_name='other')
        return ResponseTransferStateMessage(uuid=payload.get('uuid'), state='enqueued', message="Request for transfer state sent")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot process request: {str(e)}")
