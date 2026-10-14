"""Thin async wrapper around the E2B sandbox SDK.

:class:`SandboxFactory` brings sandboxes into existence;
:class:`SandboxService` drives one sandbox that already exists, bound to its
id at construction.

Both rely on the ``E2B_API_KEY`` environment variable, which the E2B SDK reads
itself; neither accepts or stores credentials.
"""

from __future__ import annotations

import os
from typing import Literal

from e2b import AsyncSandbox, CommandResult, SandboxOnResume, SnapshotInfo
from e2b.sandbox.filesystem.filesystem import WriteInfo

SnapshotMode = Literal["full", "filesystem"]

DEFAULT_TEMPLATE = "base"
DEFAULT_TIMEOUT = 120


def _require_api_key() -> None:
    """Fail fast unless ``E2B_API_KEY`` is set"""
    if not (os.getenv("E2B_API_KEY") or "").strip():
        raise RuntimeError(
            "E2B_API_KEY is not set; export it before using the sandbox services"
        )


class SandboxFactory:
    """Create sandbox and return id"""

    def __init__(self) -> None:
        """Validate that the E2B API key is configured."""
        _require_api_key()

    async def create_sandbox(
        self,
        template: str = DEFAULT_TEMPLATE,
        *,
        timeout: int | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
    ) -> str:
        """Start a new sandbox and return its id."""
        sandbox = await AsyncSandbox.create(
            template=template,
            timeout=timeout,
            metadata=metadata,
            envs=envs,
        )
        return sandbox.sandbox_id


class SandboxService:
    """Drives one E2B sandbox, bound to its id at construction."""

    def __init__(self, sbx_id: str) -> None:
        """Target an existing sandbox and validate the E2B API key is set."""
        _require_api_key()
        self._sbx_id = sbx_id

    async def load_from_snapshot(
        self,
        snapshot_id: str,
        *,
        timeout: int | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
    ) -> str:
        """Start a sandbox restored from a snapshot; returns its new id."""
        sandbox = await AsyncSandbox.create(
            template=snapshot_id,
            timeout=timeout,
            metadata=metadata,
            envs=envs,
        )
        return sandbox.sandbox_id

    async def save_snapshot(
        self,
        name: str | None = None,
        *,
        mode: SnapshotMode | None = None,
    ) -> SnapshotInfo:
        """Snapshot the sandbox's state; the sandbox itself keeps running."""
        sandbox = await self._connect()
        return await sandbox.create_snapshot(name=name, mode=mode)

    async def pause_sandbox(
        self,
        *,
        keep_memory: bool | None = None,
        mode: SnapshotMode | None = None,
    ) -> bool:
        """Pause the sandbox so it can be resumed; ``False`` if it was gone."""
        return await AsyncSandbox.pause(
            self._sbx_id, keep_memory=keep_memory, mode=mode
        )

    async def resume_sandbox(
        self,
        *,
        on_resume: SandboxOnResume = "restore",
    ) -> AsyncSandbox:
        """Wake the paused sandbox and return the attached handle.

        E2B has no explicit resume call: connecting to a paused sandbox
        resumes it. ``on_resume="reboot"`` cold-boots instead of restoring
        memory. The returned sandbox has no ``close()``; call
        :meth:`close_sandbox` to shut it down.
        """
        return await AsyncSandbox.connect(self._sbx_id, on_resume=on_resume)

    async def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        envs: dict[str, str] | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
    ) -> CommandResult:
        """Run a shell command in the sandbox and return its result."""
        sandbox = await self._connect()
        return await sandbox.commands.run(command, cwd=cwd, envs=envs, timeout=timeout)

    async def close_sandbox(self) -> bool:
        """Kill the sandbox; ``False`` means it was already gone."""
        return await AsyncSandbox.kill(self._sbx_id)

    async def read_file(
        self,
        path: str,
        *,
        binary: bool = False,
    ) -> str | bytearray:
        """Read a file as text, or as bytes when ``binary`` is set."""
        sandbox = await self._connect()
        return await sandbox.files.read(path, format="bytes" if binary else "text")

    async def write_file(
        self,
        path: str,
        data: str | bytes,
    ) -> WriteInfo:
        """Write text or bytes to a path, creating or overwriting it."""
        sandbox = await self._connect()
        return await sandbox.files.write(path, data)

    async def _connect(self) -> AsyncSandbox:
        """Connect to the bound sandbox; never use ``async with`` here."""
        return await AsyncSandbox.connect(self._sbx_id)
