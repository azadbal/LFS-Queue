from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import requests


REPORT_PATH = Path(r"C:\Dev\3DGS\LFS-plugins\lfs-queue\gui_queue_mcp_verify_report.json")
DEFAULT_ENDPOINT = "http://127.0.0.1:45677/mcp"
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_POLL_SECONDS = 0.5
PROTOCOL_VERSIONS = (
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
)


class McpHttpClient:
    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._session = requests.Session()
        self._request_id = 0
        self._session_id: str | None = None
        self.protocol_version: str | None = None

    def initialize(self) -> dict[str, Any]:
        last_error: Exception | None = None
        for protocol_version in PROTOCOL_VERSIONS:
            try:
                result = self._rpc(
                    "initialize",
                    {
                        "protocolVersion": protocol_version,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "lfs-queue-gui-verifier",
                            "version": "0.1.0",
                        },
                    },
                )
                self.protocol_version = str(result.get("protocolVersion") or protocol_version)
                self._notify("notifications/initialized", {})
                return result
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Unable to initialize MCP HTTP session: {last_error}")

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list", {})
        return list(result.get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._rpc(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self._rpc(
            "resources/read",
            {
                "uri": uri,
            },
        )

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._post(payload, expect_response=False)

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        body = self._post(payload, expect_response=True)
        if not isinstance(body, dict):
            raise RuntimeError(f"Unexpected MCP response body type: {type(body)!r}")
        if "error" in body:
            raise RuntimeError(f"MCP error for {method}: {body['error']}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Unexpected MCP result for {method}: {result!r}")
        return result

    def _post(self, payload: dict[str, Any], *, expect_response: bool) -> Any:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        response = self._session.post(
            self._endpoint,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

        session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id

        if not expect_response:
            return None

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in content_type:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                return json.loads(raw_line[5:].strip())
            raise RuntimeError("MCP event-stream response did not contain a data payload.")
        return response.json()


def _write_report(payload: dict[str, Any]) -> None:
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _extract_json_resource_text(resource_result: dict[str, Any]) -> Any:
    contents = resource_result.get("contents") or []
    if not contents:
        return None
    text = contents[0].get("text")
    if not text:
        return None
    return json.loads(text)


def _resolve_tool_name(preferred_name: str, available_tools: list[str]) -> str:
    if preferred_name in available_tools:
        return preferred_name
    plugin_name = f"plugin.{preferred_name}"
    if plugin_name in available_tools:
        return plugin_name
    for name in available_tools:
        if name.endswith(preferred_name):
            return name
    return preferred_name


def _runtime_job(jobs_payload: Any, job_id: str) -> dict[str, Any] | None:
    if not isinstance(jobs_payload, dict):
        return None
    for item in jobs_payload.get("jobs") or []:
        if isinstance(item, dict) and item.get("id") == job_id:
            return item
    return None


def _last_queue_event_name(events_payload: Any) -> str:
    if not isinstance(events_payload, dict):
        return ""
    events = events_payload.get("events") or []
    if not events:
        return ""
    last = events[-1]
    if isinstance(last, dict):
        return str(last.get("event") or "")
    return ""


def main() -> int:
    endpoint = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENDPOINT
    timeout_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TIMEOUT_SECONDS
    poll_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_POLL_SECONDS

    report: dict[str, Any] = {
        "endpoint": endpoint,
        "timeout_seconds": timeout_seconds,
        "poll_seconds": poll_seconds,
        "started_at": time.time(),
    }

    try:
        client = McpHttpClient(endpoint)
        report["initialize"] = client.initialize()

        tools_payload = client.list_tools()
        report["tools"] = tools_payload
        available_tools = [str(item.get("name")) for item in tools_payload if isinstance(item, dict)]
        resolved_tools = {
            name: _resolve_tool_name(name, available_tools)
            for name in ("queue.state", "queue.run_all", "queue.debug_events", "queue.stop")
        }
        report["resolved_tools"] = resolved_tools

        report["queue_state_before"] = client.call_tool(resolved_tools["queue.state"])
        report["queue_run_all"] = client.call_tool(resolved_tools["queue.run_all"])

        started = time.monotonic()
        snapshots: list[dict[str, Any]] = []
        final_queue_state: dict[str, Any] | None = None
        final_queue_events: dict[str, Any] | None = None
        final_runtime_state: Any = None
        final_runtime_events: Any = None

        while (time.monotonic() - started) < timeout_seconds:
            queue_state_result = client.call_tool(resolved_tools["queue.state"])
            queue_events_result = client.call_tool(resolved_tools["queue.debug_events"], {"limit": 120})
            runtime_state_result = client.read_resource("lichtfeld://runtime/state")
            runtime_events_result = client.read_resource("lichtfeld://runtime/events")

            final_queue_state = queue_state_result
            final_queue_events = queue_events_result
            final_runtime_state = _extract_json_resource_text(runtime_state_result)
            final_runtime_events = _extract_json_resource_text(runtime_events_result)

            queue_state_payload = queue_state_result.get("structuredContent") or {}
            queue_events_payload = queue_events_result.get("structuredContent") or {}
            import_job = _runtime_job(final_runtime_state, "import.dataset")
            training_job = _runtime_job(final_runtime_state, "training.main")

            snapshots.append(
                {
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "queue_phase": queue_state_payload.get("phase"),
                    "queue_status_message": queue_state_payload.get("status_message"),
                    "queue_active_job_id": queue_state_payload.get("active_job_id"),
                    "queue_last_event": _last_queue_event_name(queue_events_payload),
                    "import_status": (import_job or {}).get("status"),
                    "import_stage": (import_job or {}).get("stage"),
                    "training_status": (training_job or {}).get("status"),
                    "training_stage": (training_job or {}).get("stage"),
                }
            )

            if not queue_state_payload.get("is_running"):
                break

            time.sleep(poll_seconds)

        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["snapshots"] = snapshots
        report["queue_state_after"] = final_queue_state
        report["queue_debug_events_after"] = final_queue_events
        report["runtime_state_after"] = final_runtime_state
        report["runtime_events_after"] = final_runtime_events
        if isinstance(final_queue_state, dict):
            final_payload = final_queue_state.get("structuredContent") or {}
            report["timed_out"] = bool(final_payload.get("is_running"))
        else:
            report["timed_out"] = True

        _write_report(report)
        return 0
    except Exception as exc:
        report["exception"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        _write_report(report)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
