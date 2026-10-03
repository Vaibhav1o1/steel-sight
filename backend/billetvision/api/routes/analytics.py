from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from billetvision.api.deps import EngineDep
from billetvision.db import inspections_table
from billetvision.schemas_analytics import (
    StatusSeriesBucket,
    StatusSeriesResponse,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _parse_time_interval_seconds(interval: str) -> int:
    """Parse time interval string into seconds."""
    s = interval.strip().lower()
    if s.endswith("s"):
        return max(1, int(s[:-1]))
    if s.endswith("m"):
        return max(1, int(s[:-1])) * 60
    if s.endswith("h"):
        return max(1, int(s[:-1])) * 3600
    if s.endswith("d"):
        return max(1, int(s[:-1])) * 86400
    try:
        return max(1, int(s))
    except ValueError:
        return 300  # Default 5 minutes


def _compute_status_series(
    engine,
    mode: Literal["count", "time"],
    basis: Literal["final", "auto"],
    source_filter: Literal["all", "synthetic", "real"],
    bucket_size: int,
    interval: str,
    since: str | None,
) -> StatusSeriesResponse:
    """Query inspections and calculate status series & p-chart metrics."""
    with engine.connect() as conn:
        stmt = select(
            inspections_table.c.id,
            inspections_table.c.ts,
            inspections_table.c.status,
            inspections_table.c.auto_status,
            inspections_table.c.source,
        ).order_by(inspections_table.c.id.asc())

        if since:
            stmt = stmt.where(inspections_table.c.ts >= since)

        if source_filter == "synthetic":
            stmt = stmt.where(inspections_table.c.source == "synthetic")
        elif source_filter == "real":
            # Real includes non-synthetic or null/missing source for legacy rows
            stmt = stmt.where(
                or_(
                    inspections_table.c.source.is_(None),
                    inspections_table.c.source != "synthetic",
                )
            )

        rows = conn.execute(stmt).fetchall()

    total_inspections = len(rows)
    has_synthetic = any(r.source == "synthetic" for r in rows)

    overall_pass = 0
    overall_rework = 0
    overall_fail = 0
    overall_review = 0

    # Intermediate bucket representation: list of row lists
    raw_buckets: list[list] = []

    if mode == "count":
        bs = max(1, bucket_size)
        for i in range(0, total_inspections, bs):
            raw_buckets.append(rows[i : i + bs])
    else:  # time mode
        interval_s = _parse_time_interval_seconds(interval)
        time_map: dict[int, list] = {}
        for r in rows:
            try:
                # Format: 2026-10-03T14:05:09.231
                dt = datetime.fromisoformat(r.ts)
                epoch = int(dt.timestamp())
                bucket_key = (epoch // interval_s) * interval_s
            except Exception:
                bucket_key = 0
            time_map.setdefault(bucket_key, []).append(r)

        # Sort chronological by bucket timestamp
        for k in sorted(time_map.keys()):
            raw_buckets.append(time_map[k])

    # First pass: count items and accumulate totals
    bucket_counts: list[dict] = []
    total_eval_all = 0
    total_nonconf_all = 0

    for idx, b_rows in enumerate(raw_buckets):
        p_cnt = 0
        r_cnt = 0
        f_cnt = 0
        v_cnt = 0
        ts_first = b_rows[0].ts if b_rows else None
        ts_last = b_rows[-1].ts if b_rows else None

        for row in b_rows:
            st = row.auto_status if basis == "auto" else row.status
            if st == "Pass":
                p_cnt += 1
                overall_pass += 1
            elif st == "Rework":
                r_cnt += 1
                overall_rework += 1
            elif st == "Fail":
                f_cnt += 1
                overall_fail += 1
            else:  # Review or unknown
                v_cnt += 1
                overall_review += 1

        tot = len(b_rows)
        # Nonconforming = Rework + Fail. Evaluated = Pass + Rework + Fail (Review excluded)
        eval_cnt = p_cnt + r_cnt + f_cnt
        nonconf_cnt = r_cnt + f_cnt

        total_eval_all += eval_cnt
        total_nonconf_all += nonconf_cnt

        if mode == "count":
            start_id = b_rows[0].id if b_rows else 0
            end_id = b_rows[-1].id if b_rows else 0
            label = f"#{start_id}–#{end_id}"
            b_id = f"batch_{idx + 1}"
        else:
            label = ts_first[:19].replace("T", " ") if ts_first else f"T{idx + 1}"
            b_id = f"time_{ts_first or idx}"

        bucket_counts.append(
            {
                "bucket_id": b_id,
                "label": label,
                "ts_start": ts_first,
                "ts_end": ts_last,
                "pass_count": p_cnt,
                "rework_count": r_cnt,
                "fail_count": f_cnt,
                "review_count": v_cnt,
                "total_count": tot,
                "evaluated_count": eval_cnt,
                "nonconforming_count": nonconf_cnt,
            }
        )

    # Process centerline p-bar
    if total_eval_all > 0:
        p_bar = float(total_nonconf_all / total_eval_all)
    else:
        p_bar = 0.0

    # Second pass: calculate per-bucket p-rates and control limits
    buckets: list[StatusSeriesBucket] = []
    for b in bucket_counts:
        n_i = b["evaluated_count"]
        if n_i > 0:
            p_i = float(round(b["nonconforming_count"] / n_i, 4))
            # Standard error of proportion sigma = sqrt(p_bar * (1 - p_bar) / n_i)
            sigma = math.sqrt(max(0.0, (p_bar * (1.0 - p_bar)) / max(n_i, 1)))
            ucl = float(round(min(1.0, max(0.0, p_bar + 3.0 * sigma)), 4))
            lcl = float(round(max(0.0, p_bar - 3.0 * sigma), 4))
            reliable = bool(n_i >= 20)
        else:
            p_i = None
            ucl = None
            lcl = None
            reliable = False

        buckets.append(
            StatusSeriesBucket(
                bucket_id=b["bucket_id"],
                label=b["label"],
                ts_start=b["ts_start"],
                ts_end=b["ts_end"],
                pass_count=b["pass_count"],
                rework_count=b["rework_count"],
                fail_count=b["fail_count"],
                review_count=b["review_count"],
                total_count=b["total_count"],
                evaluated_count=b["evaluated_count"],
                nonconforming_count=b["nonconforming_count"],
                p_rate=p_i,
                ucl=ucl,
                lcl=lcl,
                centerline=float(round(p_bar, 4)) if total_eval_all > 0 else None,
                reliable=reliable,
            )
        )

    return StatusSeriesResponse(
        mode=mode,
        basis=basis,
        source_filter=source_filter,
        buckets=buckets,
        total_inspections=total_inspections,
        total_evaluated=total_eval_all,
        total_nonconforming=total_nonconf_all,
        overall_p_bar=float(round(p_bar, 4)) if total_eval_all > 0 else None,
        pass_count=overall_pass,
        rework_count=overall_rework,
        fail_count=overall_fail,
        review_count=overall_review,
        has_synthetic=has_synthetic,
    )


@router.get("/status-series", response_model=StatusSeriesResponse)
async def get_status_series(
    db: EngineDep,
    mode: Annotated[
        Literal["count", "time"],
        Query(description="Bucketing mode: count or time"),
    ] = "count",
    basis: Annotated[
        Literal["final", "auto"],
        Query(description="Status basis: final (with overrides) or auto"),
    ] = "final",
    source: Annotated[
        Literal["all", "synthetic", "real"],
        Query(description="Source filter: all, synthetic, or real"),
    ] = "all",
    bucket_size: Annotated[
        int,
        Query(ge=1, le=500, description="Bucket size for count mode"),
    ] = 20,
    interval: Annotated[
        str,
        Query(description="Time interval for time mode (e.g. 1m, 5m, 1h, 1d)"),
    ] = "5m",
    since: Annotated[
        str | None,
        Query(description="Filter inspections since timestamp"),
    ] = None,
) -> StatusSeriesResponse:
    """Return status time-series and p-chart control limits data."""
    return await run_in_threadpool(
        _compute_status_series,
        engine=db,
        mode=mode,
        basis=basis,
        source_filter=source,
        bucket_size=bucket_size,
        interval=interval,
        since=since,
    )
