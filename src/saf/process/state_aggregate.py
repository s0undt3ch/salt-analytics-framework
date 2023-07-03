# Copyright 2021-2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Aggregate the necessary job info into one event to be forwarded.
"""
from __future__ import annotations

import fnmatch
import logging
from typing import TYPE_CHECKING
from typing import AsyncIterator
from typing import Type

from saf.collect.event_bus import EventBusCollectedEvent
from saf.models import CollectedEvent
from saf.models import PipelineRunContext
from saf.models import ProcessConfigBase

if TYPE_CHECKING:
    from datetime import datetime
    from datetime import timedelta

log = logging.getLogger(__name__)


class StateAggregateConfig(ProcessConfigBase):
    """
    Job aggregate collector configuration.
    """


def get_config_schema() -> Type[StateAggregateConfig]:
    """
    Get the job aggregate collect plugin configuration schema.
    """
    return StateAggregateConfig


class StateAggregateCollectedEvent(CollectedEvent):
    """
    A collected event with aggregated state run information.
    """

    start_time: datetime
    end_time: datetime
    duration: timedelta
    minion_id: str


async def process(
    *,
    ctx: PipelineRunContext[StateAggregateConfig],
    event: CollectedEvent,
) -> AsyncIterator[CollectedEvent]:
    """
    Aggregate received events, otherwise store in cache.
    """
    if isinstance(event, EventBusCollectedEvent):
        salt_event = event.salt_event
        tag = salt_event.tag
        data = salt_event.data
        if fnmatch.fnmatch(tag, "salt/job/*/new"):
            # We will probably want to make this condition configurable
            if TYPE_CHECKING:
                assert isinstance(salt_event.data, dict)
            if data.get("fun") == "state.apply":
                jid = tag.split("/")[2]
                if "watched_jids" not in ctx.cache:
                    ctx.cache["watched_jids"] = {}
                # We are going to want a TTL at some point for the watched jids
                ctx.cache["watched_jids"][jid] = salt_event
        elif fnmatch.fnmatch(tag, "salt/job/*/ret/*"):
            split_tag = tag.split("/")
            jid = split_tag[2]
            if "watched_jids" not in ctx.cache:
                ctx.cache["watched_jids"] = {}
            if jid in ctx.cache["watched_jids"]:
                job_start_event = ctx.cache["watched_jids"][jid]
                minion_id = split_tag[-1]
                start_time = job_start_event.stamp
                end_time = salt_event.stamp
                duration = end_time - start_time
                yield StateAggregateCollectedEvent.construct(
                    data=data,
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    minion_id=minion_id,
                )
