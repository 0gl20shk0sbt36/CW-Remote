"""CodeWhale Runtime API 客户端。

连接 CodeWhale TUI 内置的 runtime_api（codewhale-tui serve --http，端口 7878）。
提供真实的 AI 调用能力。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
from httpx_sse import connect_sse


@dataclass
class RuntimeApiClient:
    """CodeWhale Runtime API 客户端（端口 7878）。"""

    base_url: str = "http://127.0.0.1:7878"
    auth_token: Optional[str] = None
    timeout: float = 300.0
    _client: Optional[httpx.AsyncClient] = field(default=None, init=False)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Bearer {self.auth_token}"
        return h

    async def _client_ctx(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ══════════════════════════════════════════════════════════════════
    # Health
    # ══════════════════════════════════════════════════════════════════

    async def health(self) -> dict:
        client = await self._client_ctx()
        resp = await client.get(f"{self.base_url}/health", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def runtime_info(self) -> dict:
        """GET /v1/runtime/info — 运行时信息（含版本号）。"""
        client = await self._client_ctx()
        resp = await client.get(f"{self.base_url}/v1/runtime/info", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # ══════════════════════════════════════════════════════════════════
    # Stream Turn（SSE）
    # ══════════════════════════════════════════════════════════════════

    async def stream_turn(
        self,
        prompt: str,
        model: str = None,
        mode: str = "agent",
        workspace: str = None,
        allow_shell: bool = True,
    ) -> tuple[str, str, list[dict]]:
        """POST /v1/stream — SSE 流式 AI 对话。返回 (thread_id, turn_id, events)。"""
        body = {"prompt": prompt, "mode": mode}
        if model:
            body["model"] = model
        if workspace:
            body["workspace"] = workspace
        if allow_shell is not None:
            body["allow_shell"] = allow_shell

        client = await self._client_ctx()
        thread_id, turn_id = "", ""
        events: list[dict] = []

        async with connect_sse(
            client, "POST", f"{self.base_url}/v1/stream",
            json=body, headers=self._headers()
        ) as sse:
            async for ev in sse.aiter_sse():
                try:
                    data = json.loads(ev.data) if isinstance(ev.data, str) else ev.data
                except json.JSONDecodeError:
                    continue
                events.append({"type": ev.event, "data": data})
                if ev.event == "turn.started":
                    thread_id = data.get("thread_id", "")
                    turn_id = data.get("turn_id", "")
                elif ev.event == "done":
                    break
        return thread_id, turn_id, events

    # ══════════════════════════════════════════════════════════════════
    # Threads — CRUD
    # ══════════════════════════════════════════════════════════════════

    async def create_thread(
        self, model: str = None, mode: str = "agent",
        system_prompt: str = None, workspace: str = None,
        allow_shell: bool = True,
    ) -> dict:
        body = {"mode": mode, "allow_shell": allow_shell}
        if model:
            body["model"] = model
        if system_prompt is not None:
            body["system_prompt"] = system_prompt
        if workspace is not None:
            body["workspace"] = workspace
        return await self._post("/v1/threads", body)

    async def list_threads(self, limit: int = None, include_archived: bool = None) -> dict:
        params = {}
        if limit is not None:
            params["limit"] = limit
        if include_archived is not None:
            params["include_archived"] = include_archived
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/v1/threads?{qs}" if qs else "/v1/threads"
        client = await self._client_ctx()
        resp = await client.get(f"{self.base_url}{path}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def get_thread(self, thread_id: str) -> dict:
        client = await self._client_ctx()
        resp = await client.get(
            f"{self.base_url}/v1/threads/{thread_id}", headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def update_thread(self, thread_id: str, **kwargs) -> dict:
        return await self._patch(f"/v1/threads/{thread_id}", kwargs)

    # ══════════════════════════════════════════════════════════════════
    # Threads — Actions
    # ══════════════════════════════════════════════════════════════════

    async def start_turn(
        self, thread_id: str, prompt: str, model: str = None,
    ) -> dict:
        body = {"prompt": prompt}
        if model:
            body["model"] = model
        return await self._post(f"/v1/threads/{thread_id}/turns", body)

    async def resume_thread(self, thread_id: str, model: str = None) -> dict:
        body = {}
        if model:
            body["model"] = model
        return await self._post(f"/v1/threads/{thread_id}/resume", body)

    async def fork_thread(self, thread_id: str) -> dict:
        return await self._post(f"/v1/threads/{thread_id}/fork", {})

    async def compact_thread(self, thread_id: str, reason: str = None) -> dict:
        body = {}
        if reason:
            body["reason"] = reason
        return await self._post(f"/v1/threads/{thread_id}/compact", body)

    async def interrupt_turn(self, thread_id: str, turn_id: str) -> dict:
        return await self._post(f"/v1/threads/{thread_id}/turns/{turn_id}/interrupt", {})

    # ══════════════════════════════════════════════════════════════════
    # Approvals
    # ══════════════════════════════════════════════════════════════════

    async def decide_approval(
        self, approval_id: str, decision: str = "allow", remember: bool = False,
    ) -> dict:
        body = {"decision": decision, "remember": remember}
        return await self._post(f"/v1/approvals/{approval_id}", body)

    # ══════════════════════════════════════════════════════════════════
    # Workspace / Usage / Snapshots
    # ══════════════════════════════════════════════════════════════════

    async def workspace_status(self) -> dict:
        client = await self._client_ctx()
        resp = await client.get(
            f"{self.base_url}/v1/workspace/status", headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def usage(
        self, group_by: str = "day", since: str = None, until: str = None,
    ) -> dict:
        params = [f"group_by={group_by}"]
        if since:
            params.append(f"since={since}")
        if until:
            params.append(f"until={until}")
        path = f"/v1/usage?{'&'.join(params)}"
        client = await self._client_ctx()
        resp = await client.get(f"{self.base_url}{path}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def snapshots(self, limit: int = 20) -> dict:
        client = await self._client_ctx()
        resp = await client.get(
            f"{self.base_url}/v1/snapshots?limit={limit}", headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    # ══════════════════════════════════════════════════════════════════
    # Internal
    # ══════════════════════════════════════════════════════════════════

    async def _post(self, path: str, body: dict) -> dict:
        client = await self._client_ctx()
        resp = await client.post(
            f"{self.base_url}{path}", json=body, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def _patch(self, path: str, body: dict) -> dict:
        client = await self._client_ctx()
        resp = await client.request(
            "PATCH", f"{self.base_url}{path}", json=body, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()


def create_client() -> RuntimeApiClient:
    base_url = os.environ.get("CODEWHALE_API_URL", "http://127.0.0.1:7878")
    auth_token = os.environ.get("DEEPSEEK_RUNTIME_TOKEN")
    return RuntimeApiClient(base_url=base_url, auth_token=auth_token)
