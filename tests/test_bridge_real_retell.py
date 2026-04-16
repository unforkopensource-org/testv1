"""Real-vendor end-to-end test for the Retell native bridge.

This test runs the real `decibench-bridge` Node sidecar, opens a real
Retell web call, streams a short PCM16 chunk in, and asserts the agent
emitted at least one agent-transcript or agent-audio event.

It is **gated** on three things being available in the environment:

  - `DECIBENCH_E2E_RETELL=1`     — explicit opt-in
  - `RETELL_API_KEY`             — server API key
  - `RETELL_TEST_AGENT_ID`       — agent id to call

If any of them are missing the test is skipped. CI runs it on a nightly job
that injects these via secrets; local developers never trip over it.
"""

from __future__ import annotations

import os

import pytest

from decibench.connectors.retell import RetellConnector
from decibench.models import AudioBuffer, EventType

REQUIRED_ENV = ("DECIBENCH_E2E_RETELL", "RETELL_API_KEY", "RETELL_TEST_AGENT_ID")


def _missing_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.environ.get(name)]


pytestmark = pytest.mark.skipif(
    bool(_missing_env()),
    reason=f"Missing env for real-Retell e2e: {_missing_env()}",
)


@pytest.mark.asyncio
async def test_real_retell_bridge_round_trip() -> None:
    """Real Retell call via the sidecar. Heavy — runs Playwright + Chromium."""
    agent_id = os.environ["RETELL_TEST_AGENT_ID"]

    connector = RetellConnector()
    handle = await connector.connect(
        f"retell://{agent_id}",
        {"retell_api_key": os.environ["RETELL_API_KEY"]},
    )
    try:
        # Send roughly half a second of silence as a stand-in caller turn.
        silence = AudioBuffer(data=b"\x00" * 16000, sample_rate=16000)
        await connector.send_audio(handle, silence)

        events = []
        async for ev in connector.receive_events(handle):
            events.append(ev)

        # Real agents typically emit at least a transcript or audio event.
        kinds = {e.type for e in events}
        assert kinds & {
            EventType.AGENT_TRANSCRIPT,
            EventType.AGENT_AUDIO,
        }, f"No agent activity received. Events: {[e.type for e in events]}"
    finally:
        await connector.disconnect(handle)
