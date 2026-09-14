from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .cache import RequestBudget, WorldPopCache, request_hash
from .models import CachedTaskResult, TaskStatus, TaskSubmission, WorldPopQuery


class WorldPopClientError(RuntimeError):
    pass


class WorldPopRateLimited(WorldPopClientError):
    pass


class WorldPopTaskFailed(WorldPopClientError):
    pass


class WorldPopClient:
    def __init__(
        self,
        base_url: str,
        cache: WorldPopCache,
        budget: RequestBudget,
        api_key: str = "",
        poll_initial_seconds: float = 2,
        poll_max_seconds: float = 16,
        task_timeout_seconds: float = 180,
        http_client: httpx.Client | None = None,
        sleep=time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache = cache
        self.budget = budget
        self.api_key = api_key
        self.poll_initial_seconds = poll_initial_seconds
        self.poll_max_seconds = poll_max_seconds
        self.task_timeout_seconds = task_timeout_seconds
        self.http = http_client or httpx.Client(timeout=30, follow_redirects=True)
        self.sleep = sleep
        self.http_request_count = 0
        self.cache_hits = 0
        self.log_path = cache.manifests / "http_requests.jsonl"

    def _log(
        self,
        method: str,
        endpoint: str,
        status: int | None,
        attempt: int,
        task_id: str | None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "method": method,
            "endpoint": endpoint,
            "task_id": task_id,
            "status": status,
            "attempt": attempt,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        task_id: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(1, 3):
            self.budget.consume()
            self.http_request_count += 1
            status: int | None = None
            try:
                response = self.http.request(
                    method, f"{self.base_url}/{endpoint.lstrip('/')}", headers=headers, **kwargs
                )
                status = response.status_code
                self._log(method, endpoint, status, attempt, task_id)
                if status == 429:
                    raise WorldPopRateLimited("WorldPop returned HTTP 429; checkpoint saved")
                if status >= 500:
                    last_error = WorldPopClientError(
                        f"WorldPop returned HTTP {status}: {response.text[:300]}"
                    )
                else:
                    response.raise_for_status()
                    return response
            except WorldPopRateLimited:
                raise
            except (httpx.HTTPError, WorldPopClientError) as error:
                if status is None:
                    self._log(method, endpoint, None, attempt, task_id)
                last_error = error
                if status is not None and status < 500:
                    raise WorldPopClientError(str(error)) from error
                if attempt == 1:
                    self.sleep(min(self.poll_max_seconds, 2 + random.uniform(0, 0.5)))
        raise WorldPopClientError(f"WorldPop request failed after bounded retry: {last_error}")

    def execute(self, query: WorldPopQuery) -> CachedTaskResult:
        key = request_hash(query)
        response_path = self.cache.response_path(key)
        cached_response = self.cache.read_json(response_path)
        if cached_response is not None:
            self.cache_hits += 1
            return CachedTaskResult(
                request_hash=key,
                task_id=cached_response["task_id"],
                result=cached_response["result"],
                response_path=response_path,
                cache_hit=True,
                submitted_at=cached_response.get("submitted_at"),
                retrieved_at=cached_response["retrieved_at"],
            )

        request_record = {
            "endpoint": query.endpoint.value,
            "payload": query.api_payload(),
            "request_hash": key,
        }
        self.cache.write_json(self.cache.request_path(key), request_record)
        task_record = self.cache.read_json(self.cache.task_path(key))
        if task_record is None:
            submitted_at = datetime.now(UTC)
            response = self._request(
                "POST", query.endpoint.value, json=query.api_payload()
            )
            submission = TaskSubmission.model_validate(response.json())
            task_record = {
                "request_hash": key,
                "task_id": submission.task_id,
                "status": submission.status,
                "submitted_at": submitted_at.isoformat(),
                "check_url": submission.check_url,
            }
            self.cache.write_json(self.cache.task_path(key), task_record)

        task_id = task_record["task_id"]
        started = time.monotonic()
        delay = self.poll_initial_seconds
        attempt = 0
        while time.monotonic() - started <= self.task_timeout_seconds:
            attempt += 1
            response = self._request(
                "GET", f"tasks/{task_id}", task_id=task_id
            )
            status_payload = response.json()
            status = TaskStatus.model_validate(status_payload)
            task_record.update(
                status=status.status,
                progress=status.progress,
                stage=status.stage,
                last_polled_at=datetime.now(UTC).isoformat(),
                poll_attempt=attempt,
            )
            self.cache.write_json(self.cache.task_path(key), task_record)
            normalized_status = status.status.lower()
            if normalized_status == "success":
                if status.result is None:
                    raise WorldPopClientError("successful task did not include result")
                retrieved_at = datetime.now(UTC)
                completed = {
                    "request_hash": key,
                    "task_id": task_id,
                    "submitted_at": task_record.get("submitted_at"),
                    "retrieved_at": retrieved_at.isoformat(),
                    "result": status.result,
                    "raw_task_status": status_payload,
                }
                self.cache.write_json(response_path, completed)
                return CachedTaskResult(
                    request_hash=key,
                    task_id=task_id,
                    result=status.result,
                    response_path=response_path,
                    cache_hit=False,
                    submitted_at=task_record.get("submitted_at"),
                    retrieved_at=retrieved_at,
                )
            if normalized_status == "failure":
                raise WorldPopTaskFailed(status.error or "WorldPop task failed")
            jitter = random.uniform(0, min(0.5, delay * 0.1))
            self.sleep(delay + jitter)
            delay = min(self.poll_max_seconds, delay * 2)
        raise WorldPopClientError(
            f"WorldPop task {task_id} exceeded {self.task_timeout_seconds}s timeout"
        )
