"""WebSocket connection to a jamovi server instance."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import websockets
from google.protobuf.message import Message

from .proto import jamovi_pb2 as jcoms

log = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Raised when communication with the jamovi server fails."""


class JamoviConnection:
    """Manages a WebSocket connection to a jamovi instance."""

    def __init__(self, base_url: str, ws_url: str, access_key: str) -> None:
        self._base_url = base_url
        self._ws_url = ws_url
        self._access_key = access_key
        self._instance_id: str = ""
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._msg_id: int = 0
        self._pending: dict[int, asyncio.Future[tuple[str, bytes]]] = {}
        self._analysis_results: dict[int, bytes] = {}
        self._analysis_events: dict[int, asyncio.Event] = {}
        self._listen_task: asyncio.Task[None] | None = None

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def connect(self) -> None:
        """Connect to a new empty instance."""
        await self._create_empty_instance()
        await self._open_websocket()

    async def connect_with_file(self, file_path: str) -> str:
        """Open a data file via HTTP, then connect WebSocket to the data instance.

        Returns the instance ID of the data instance.
        """
        new_id = await self._http_open_file(file_path)
        await self._disconnect_ws()
        self._instance_id = new_id
        await self._open_websocket()
        return new_id

    async def _create_empty_instance(self) -> None:
        url = f"{self._base_url}/?access_key={self._access_key}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    path = location.split("?")[0].rstrip("/")
                    self._instance_id = path.split("/")[-1]
                else:
                    text = await resp.text()
                    raise ConnectionError(
                        f"Failed to create instance: HTTP {resp.status}\n{text}"
                    )
        if not self._instance_id:
            raise ConnectionError("No instance ID in redirect response")

    async def _http_open_file(self, file_path: str) -> str:
        """Open a file via HTTP POST, returning the new instance ID."""
        cookies = {"access_key": self._access_key}
        new_id: str = ""
        async with aiohttp.ClientSession(cookies=cookies) as session:
            data = {"options": json.dumps({"path": str(file_path), "title": ""})}
            async with session.post(f"{self._base_url}/open", data=data) as resp:
                async for line in resp.content:
                    line_text = line.decode("utf-8").strip()
                    if not line_text:
                        continue
                    msg = json.loads(line_text)
                    if msg.get("status") == "OK":
                        new_id = msg["url"].rstrip("/")
        if not new_id:
            raise ConnectionError(f"Failed to open file: {file_path}")
        return new_id

    async def save_file(self, file_path: str, overwrite: bool = True) -> dict[str, Any]:
        """Save the current instance through jamovi's HTTP save endpoint."""
        if not self._instance_id:
            raise ConnectionError("No active jamovi instance")

        cookies = {"access_key": self._access_key}
        options = {"path": str(file_path), "overwrite": overwrite}
        final_message: dict[str, Any] | None = None

        async with aiohttp.ClientSession(cookies=cookies) as session:
            data = {"options": json.dumps(options)}
            url = f"{self._base_url}/{self._instance_id}/save"
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ConnectionError(
                        f"Failed to save file: HTTP {resp.status}\n{text}"
                    )

                async for line in resp.content:
                    line_text = line.decode("utf-8").strip()
                    if not line_text:
                        continue
                    try:
                        message = json.loads(line_text)
                    except json.JSONDecodeError as e:
                        raise ConnectionError(
                            f"Invalid save response from jamovi: {line_text}"
                        ) from e

                    status = message.get("status")
                    if status == "error":
                        detail = message.get("message") or message.get("code") or message
                        raise ConnectionError(f"Failed to save file: {detail}")
                    if status == "OK":
                        final_message = message

        if final_message is None:
            raise ConnectionError(f"Failed to save file: {file_path}")
        return final_message

    async def _open_websocket(self) -> None:
        ws_path = f"{self._ws_url}/{self._instance_id}/coms"
        self._ws = await websockets.connect(
            ws_path,
            max_size=100 * 1024 * 1024,
            additional_headers={"Cookie": f"access_key={self._access_key}"},
        )
        self._listen_task = asyncio.ensure_future(self._listen())
        await self._send_instance_request()

    async def _disconnect_ws(self) -> None:
        """Disconnect WebSocket without stopping other state."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._analysis_results.clear()
        self._analysis_events.clear()

    async def disconnect(self) -> None:
        await self._disconnect_ws()

    async def _send_instance_request(self) -> None:
        request = jcoms.InstanceRequest()
        response = await self.send(request, payload_type="InstanceRequest")
        parsed = jcoms.InstanceResponse()
        parsed.ParseFromString(response)

    async def _listen(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg = jcoms.ComsMessage()
                msg.ParseFromString(raw)
                if msg.id == 0 and msg.payloadType == "AnalysisResponse":
                    response = jcoms.AnalysisResponse()
                    response.ParseFromString(msg.payload)
                    self._analysis_results[response.analysisId] = msg.payload
                    event = self._analysis_events.get(response.analysisId)
                    if event:
                        event.set()
                    continue
                if msg.status == jcoms.Status.IN_PROGRESS:
                    continue
                future = self._pending.pop(msg.id, None)
                if future and not future.done():
                    if msg.status == jcoms.Status.ERROR:
                        future.set_exception(
                            ConnectionError(
                                f"Server error: {msg.error.message} ({msg.error.cause})"
                            )
                        )
                    else:
                        future.set_result((msg.payloadType, msg.payload))
        except asyncio.CancelledError:
            pass
        except websockets.ConnectionClosed as e:
            log.warning("WebSocket closed: %s", e)
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionError(f"WebSocket closed: {e}"))
            self._pending.clear()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def send(
        self,
        message: Message,
        *,
        payload_type: str = "",
    ) -> bytes:
        """Send a protobuf message and wait for the response payload bytes.

        Args:
            message: The protobuf request message to send.
            payload_type: Type name matching the proto message class (e.g. "AnalysisRequest").

        Returns:
            The raw payload bytes from the response.
        """
        assert self._ws is not None

        msg_id = self._next_id()
        pt = payload_type or type(message).__name__

        coms = jcoms.ComsMessage()
        coms.id = msg_id
        coms.instanceId = self._instance_id
        coms.payload = message.SerializeToString()
        coms.payloadType = pt

        future: asyncio.Future[tuple[str, bytes]] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send(coms.SerializeToString())

        try:
            _response_type, payload = await asyncio.wait_for(future, timeout=300)
            return payload
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise ConnectionError("Request timed out after 300s")

    async def wait_for_analysis_result(
        self,
        analysis_id: int,
        timeout: float = 300,
    ) -> bytes:
        """Wait for an AnalysisResponse with matching analysisId and COMPLETE status."""
        from .proto import jamovi_pb2 as _jcoms

        event = asyncio.Event()
        self._analysis_events[analysis_id] = event

        try:
            # Check if result already arrived
            payload = self._analysis_results.get(analysis_id)
            if payload is not None:
                resp = _jcoms.AnalysisResponse()
                resp.ParseFromString(payload)
                if resp.status == _jcoms.AnalysisStatus.ANALYSIS_COMPLETE:
                    return payload

            # Wait for new results
            while True:
                try:
                    await asyncio.wait_for(event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise ConnectionError(
                        f"Timed out waiting for analysis {analysis_id}"
                    )

                event.clear()
                payload = self._analysis_results.get(analysis_id)
                if payload is not None:
                    resp = _jcoms.AnalysisResponse()
                    resp.ParseFromString(payload)
                    if resp.status == _jcoms.AnalysisStatus.ANALYSIS_COMPLETE:
                        return payload
        finally:
            self._analysis_events.pop(analysis_id, None)

    async def send_no_wait(self, message: Message, *, payload_type: str = "") -> None:
        """Send a message without waiting for a response."""
        assert self._ws is not None

        msg_id = self._next_id()
        pt = payload_type or type(message).__name__

        coms = jcoms.ComsMessage()
        coms.id = msg_id
        coms.instanceId = self._instance_id
        coms.payload = message.SerializeToString()
        coms.payloadType = pt

        await self._ws.send(coms.SerializeToString())
