import os
import time
from typing import Dict, Tuple
from fastapi import HTTPException


RATE = int(os.getenv("INGEST_RATE_LIMIT_PER_MIN", "600"))
REDIS_URL = os.getenv("REDIS_URL")

# state: key -> (window_start_epoch, count)
_STATE: Dict[str, Tuple[int, int]] = {}


def check_rate(key: str, quota: int | None = None):
    q = quota or RATE
    if REDIS_URL:
        try:
            import redis
            r = redis.Redis.from_url(REDIS_URL)
            bucket = f"rl:{key}:{int(time.time())//60}"
            val = r.incr(bucket)
            if val == 1:
                r.expire(bucket, 70)
            if int(val) > q:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            return
        except Exception:
            pass
    # fallback in-memory
    now = int(time.time())
    minute = now - (now % 60)
    win, cnt = _STATE.get(key, (minute, 0))
    if win != minute:
        win, cnt = minute, 0
    cnt += 1
    _STATE[key] = (win, cnt)
    if cnt > q:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
