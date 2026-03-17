from __future__ import annotations
from datetime import datetime, time, timedelta

def _work_intervals_for_day(d: datetime):
    wd = d.weekday()
    if wd >= 5:
        return []
    morning_end = time(12, 0)
    morning = (time(8, 0), morning_end)
    if wd == 4:
        afternoon = (time(13, 0), time(17, 0))
    else:
        afternoon = (time(13, 0), time(18, 0))
    return [morning, afternoon]


def _clamp_interval(start: datetime, end: datetime, a: datetime, b: datetime) -> timedelta:
    if end <= a or b <= start:
        return timedelta(0)
    s = max(start, a)
    e = min(end, b)
    if e <= s:
        return timedelta(0)
    return e - s


def business_minutes_between(start: datetime, end: datetime) -> int:
    if end <= start:
        return 0
    total = timedelta(0)
    cur = start
    end_day = end.date()
    while cur.date() <= end_day:
        intervals = _work_intervals_for_day(cur)
        for (hh1, hh2) in intervals:
            a = datetime.combine(cur.date(), hh1, tzinfo=start.tzinfo)
            b = datetime.combine(cur.date(), hh2, tzinfo=start.tzinfo)
            total += _clamp_interval(start, end, a, b)
        cur = cur + timedelta(days=1)
        cur = cur.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(total.total_seconds() // 60)

