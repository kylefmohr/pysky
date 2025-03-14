import sys
from datetime import datetime, timedelta, timezone

from peewee import fn

from pysky.logging import log
from pysky.models import APICallLog

# https://docs.bsky.app/docs/advanced-guides/rate-limits
WRITE_OPS_BUDGETS = {
    1: 5000,
    24: 35000,
}

WRITE_OP_POINTS_MAP = {
    "xrpc/com.atproto.repo.createRecord": 3,
    "xrpc/com.atproto.repo.deleteRecord": 1,
}


class RateLimitExceeded(Exception):
    pass


def get_budget_used(did, hours):

    assert did
    assert hours in [1, 24]
    budget_sum_row = (
        APICallLog.select(fn.sum(APICallLog.write_op_points_consumed))
        .where(APICallLog.timestamp >= datetime.now(timezone.utc) - timedelta(hours=hours))
        .where(APICallLog.request_did == did)
        .first()
    )

    try:
        return budget_sum_row.sum or 0
    except AttributeError:
        return 0


def check_write_ops_budget(did, hours, points_to_use, override_budget=None):

    assert did
    assert hours in [1, 24]
    budget = override_budget or WRITE_OPS_BUDGETS[hours]

    budget_used = get_budget_used(did, hours)
    budget_used += points_to_use

    if budget_used >= budget:
        raise RateLimitExceeded(
            f"This operation would meet or exceed write operations {hours}-hour budget: {budget_used}/{budget} points used"
        )

    if budget_used > (0.95 * budget):
        pctg = f"{(budget_used/budget):.2%}"
        log.warning(
            f"Over 95% of the {hours}-hour write ops budget has been used: {budget_used}/{budget} ({pctg})"
        )
