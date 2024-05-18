import sys
import os
import logging
import json
from dotenv import load_dotenv
from uuid import uuid4
from redis import Redis
from time import time
from pydantic import BaseModel, UUID4, Field, field_serializer

load_dotenv()
# REDIS_PASSWORD=qXV7PnU8u3+vjGR2CzaPxXvIXjsHc6FRA7j3irznbA41Gx8TSHlgu58Akvf2Qb+r;REDIS_USER=api;REDIS_HOST=localhost

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
# log_formatter = logging.Formatter("%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


cache_db = Redis(
    host=os.getenv("REDIS_HOST"),
    port=os.getenv("REDIS_PORT"),
    username=os.getenv("REDIS_USER"),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True
)


class DramatiqJobOptions(BaseModel):
    redis_message_id: UUID4 = Field(default_factory=uuid4)

    @field_serializer('redis_message_id')
    def serialize_redis_message_id(self, v: UUID4):
        return str(v)


class DramatiqJob(BaseModel):
    queue_name: str
    actor_name: str
    args: tuple = ()
    kwargs: dict
    options: DramatiqJobOptions = Field(default_factory=DramatiqJobOptions)
    message_id: UUID4 = Field(default_factory=uuid4)
    message_timestamp: float = Field(default_factory=time)

    @field_serializer('message_id')
    def serialize_redis_message_id(self, v: UUID4):
        return str(v)

    @field_serializer('message_timestamp')
    def serialize_ts(self, v: float):
        return int(v)


def push_job(payload: dict, actor_name: str, queue_name: str = 'default'):
    job = DramatiqJob(
        queue_name=queue_name,
        actor_name=actor_name,
        kwargs=payload
    )
    logger.warning(f"Pushing job {job.dict()}")
    cache_db.hset(f'dramatiq:{queue_name}.msgs', str(job.options.redis_message_id), json.dumps(job.dict()))
    cache_db.rpush(f'dramatiq:{queue_name}', str(job.options.redis_message_id))


# cache_db = Redis(
#     host="localhost",
#     port=6379,
#     # username="default", # use your Redis user. More info https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
#     # password="secret",  # use your Redis password
#     username=os.getenv("REDIS_USER"),
#     # password="qXV7PnU8u3+vjGR2CzaPxXvIXjsHc6FRA7j3irznbA41Gx8TSHlgu58Akvf2Qb+r",
#     password=os.getenv("REDIS_PASSWORD"),
#     # ssl=True,
#     # ssl_certfile="./redis_user.crt",
#     # ssl_keyfile="./redis_user_private.key",
#     # ssl_ca_certs="./redis_ca.pem",
#     decode_responses=True
# )

