from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from scripts.oddsportal_one_match import _capture_failure_artifacts


class _FakeTracing:
    def __init__(self):
        self.stopped_to: Path | None = None

    async def stop(self, path: str | None = None) -> None:
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"trace")
            self.stopped_to = p


class _FakeContext:
    def __init__(self):
        self.tracing = _FakeTracing()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeLocator:
    async def count(self) -> int:
        return 0

    async def is_visible(self) -> bool:
        return False


class _FakePage:
    url = "https://example.test/"

    async def title(self) -> str:
        return "Example"

    async def screenshot(self, path: str, full_page: bool = True) -> None:
        Path(path).write_bytes(b"png")

    async def content(self) -> str:
        return "<html><body>ok</body></html>"

    async def inner_text(self, selector: str) -> str:
        return "plain body"

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator()


def test_capture_failure_artifacts_writes_meta_and_files() -> None:
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=True)

        ctx = _FakeContext()
        page = _FakePage()

        asyncio.run(
            _capture_failure_artifacts(
                context=ctx,
                page=page,
                run_dir=run_dir,
                reason="final_failure",
                err=TimeoutError("boom"),
                match_url="https://www.oddsportal.com/football/england/premier-league/brighton-liverpool-bm4x5tgU/#1X2;2",
                market_type="1X2",
                traces_started=True,
            )
        )

        meta_path = run_dir / "meta.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["reason"] == "final_failure"
        assert meta["market_type"] == "1X2"
        assert "selector_counts" in meta
        assert "block_signals" in meta

        assert (run_dir / "failure.png").exists()
        assert (run_dir / "failure.html").exists()
        assert (run_dir / "trace.zip").exists()
        assert ctx.closed is True
