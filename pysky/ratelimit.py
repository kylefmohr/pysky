import sys
from datetime import datetime, timedelta, UTC

from peewee import fn

from pysky.models import APICallLog

# https://docs.bsky.app/docs/advanced-guides/rate-limits
WRITE_OPS_BUDGET_1_HOUR = 5000
WRITE_OPS_BUDGET_24_HOUR = 35000

WRITE_OP_POINTS_MAP = {
    "xrpc/com.atproto.repo.createRecord": 3,
    "xrpc/com.atproto.repo.deleteRecord": 1,
}


class RateLimitExceeded(Exception):
    pass


def check_write_ops_budget():

    budget_used_hour = (
        APICallLog.select(fn.sum(APICallLog.write_op_points_consumed))
        .where(APICallLog.timestamp >= datetime.now(UTC) - timedelta(hours=1))
        .first()
        .sum
    )
    budget_used_day = (
        APICallLog.select(fn.sum(APICallLog.write_op_points_consumed))
        .where(APICallLog.timestamp >= datetime.now(UTC) - timedelta(hours=24))
        .first()
        .sum
    )

    if budget_used_hour > (0.80 * WRITE_OPS_BUDGET_1_HOUR):
        pctg = f"{(budget_used_hour/WRITE_OPS_BUDGET_1_HOUR):.2%}"
        sys.stderr.write(
            f"over 80% of the hourly write ops budget has been used: {budget_used_hour}/{WRITE_OPS_BUDGET_1_HOUR} ({pctg})\n"
        )

    if budget_used_day > (0.80 * WRITE_OPS_BUDGET_24_HOUR):
        pctg = f"{(budget_used_day/WRITE_OPS_BUDGET_24_HOUR):.2%}"
        sys.stderr.write(
            f"over 80% of the daily write ops budget has been used: {budget_used_day}/{WRITE_OPS_BUDGET_24_HOUR} ({pctg})\n"
        )

    if budget_used_hour >= WRITE_OPS_BUDGET_1_HOUR or budget_used_day >= WRITE_OPS_BUDGET_24_HOUR:
        raise RateLimitExceeded(
            f"at or exceeded write operations budget: {budget_used_hour}/{WRITE_OPS_BUDGET_1_HOUR} points used in the last hour, {budget_used_day}/{WRITE_OPS_BUDGET_24_HOUR} points used in the last 24 hours"
        )


"""
to do - implement these per minute/per day limits
[
    ("*", 3000, 5),
    ("xrpc/com.atproto.identity.updateHandle", 10, 5, 50),
    ("xrpc/com.atproto.server.createAccount", 100, 5, None),
    ("xrpc/com.atproto.server.createSession", 30, 5, 300),
    ("xrpc/com.atproto.server.deleteAccount", 50, 5, None),
    ("xrpc/com.atproto.server.resetPassword", 50, 1, None),
]
"""
