from __future__ import annotations

from queue import Queue
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from starlette.requests import HTTPConnection

from billetvision.logging_io import InspectionLogger
from billetvision.runtime.events import EventBus
from billetvision.runtime.state import RuntimeState


def get_state(conn: HTTPConnection) -> RuntimeState:
    return conn.app.state.runtime_state


def get_bus(conn: HTTPConnection) -> EventBus:
    return conn.app.state.event_bus


def get_engine(conn: HTTPConnection) -> Engine:
    return conn.app.state.db_engine


def get_db_logger(conn: HTTPConnection) -> InspectionLogger:
    return conn.app.state.db_logger


def get_job_queue(conn: HTTPConnection) -> Queue:
    return conn.app.state.job_queue


StateDep = Annotated[RuntimeState, Depends(get_state)]
BusDep = Annotated[EventBus, Depends(get_bus)]
EngineDep = Annotated[Engine, Depends(get_engine)]
DbLoggerDep = Annotated[InspectionLogger, Depends(get_db_logger)]
JobQueueDep = Annotated[Queue, Depends(get_job_queue)]
