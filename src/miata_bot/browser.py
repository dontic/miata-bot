"""Fetch result pages with a real Chrome (via nodriver), getting past Cloudflare.

What we learned probing the site:
  * Every URL (even robots.txt) sits behind a Cloudflare managed challenge, so plain
    HTTP clients, including TLS-impersonating ones like curl_cffi, get a 403.
  * The challenge is a Turnstile checkbox. Headless Chrome never passes it, but a
    headful Chrome on a virtual display (Xvfb) passes after one trusted-looking click.
  * Calling `tab.evaluate()` (CDP Runtime) while the challenge is up gets the click
    rejected. We only use DOM-domain calls + Input events until we're through.
  * Once past, the cf_clearance cookie lets further navigations through, and keeping
    a persistent profile often skips the challenge on the next run entirely.
"""

import asyncio
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path

import nodriver as uc
from nodriver import cdp

from .parser import is_challenge_page

log = logging.getLogger(__name__)

WINDOW = (1280, 900)
TURNSTILE_SELECTOR = "div:has(> input[name=cf-turnstile-response])"


class ChallengeFailed(RuntimeError):
    pass


class VirtualDisplay:
    """Start Xvfb if there's no X display (e.g. on a server or in a container)."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "VirtualDisplay":
        if os.environ.get("DISPLAY"):
            return self
        if not shutil.which("Xvfb"):
            raise RuntimeError("No DISPLAY and Xvfb is not installed (apt install xvfb)")
        read_fd, write_fd = os.pipe()
        self.proc = subprocess.Popen(
            ["Xvfb", "-displayfd", str(write_fd), "-screen", "0", f"{WINDOW[0]}x{WINDOW[1]}x24", "-nolisten", "tcp"],
            pass_fds=(write_fd,),
        )
        os.close(write_fd)
        with os.fdopen(read_fd) as f:
            display = f.readline().strip()
        os.environ["DISPLAY"] = f":{display}"
        log.debug("Started Xvfb on :%s", display)
        return self

    def __exit__(self, *exc) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
            os.environ.pop("DISPLAY", None)


class Scraper:
    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = profile_dir
        self.browser: uc.Browser | None = None
        self.tab: uc.Tab | None = None

    async def __aenter__(self) -> "Scraper":
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.browser = await uc.start(
            headless=False,  # headless is detected by Turnstile
            sandbox=False,  # Chrome's sandbox doesn't work in unprivileged containers
            user_data_dir=str(self.profile_dir.resolve()),
            browser_args=[f"--window-size={WINDOW[0]},{WINDOW[1]}", "--test-type"],
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self.browser:
            process = self.browser._process
            self.browser.stop()
            if process:
                # Reap Chrome before the event loop closes, or asyncio warns on exit.
                await asyncio.wait_for(process.wait(), timeout=10)

    async def open(self, url: str) -> str:
        """Navigate to url and return its HTML once past the Cloudflare challenge."""
        self.tab = await self.browser.get(url)
        await asyncio.sleep(5)
        await self._pass_challenge()
        await self._dismiss_consent()
        return await self.tab.get_content()

    async def goto_page(self, page: int) -> str | None:
        """Click the pagination link for `page` on the current results page.

        Pagination is a JS form POST, not a URL parameter, so we have to click.
        Returns None if there's no such page.
        """
        links = await self.tab.select_all(f'a[href="javascript:ctrl.set_pageReload({page})"]', timeout=5)
        if not links:
            return None
        before = await self.tab.get_content()
        await links[0].scroll_into_view()
        await asyncio.sleep(1)
        await links[0].mouse_click()
        for _ in range(30):
            await asyncio.sleep(1)
            html = await self.tab.get_content()
            if html != before and "li-result" in html:
                await asyncio.sleep(2)  # let the list finish rendering
                return await self.tab.get_content()
        log.warning("Page %d did not load", page)
        return None

    async def _pass_challenge(self, attempts: int = 4) -> None:
        for attempt in range(1, attempts + 1):
            html = await self.tab.get_content()
            if not is_challenge_page(html):
                return
            log.info("Cloudflare challenge detected, attempt %d/%d", attempt, attempts)
            box = await self._turnstile_box()
            if box:
                left, top, bottom = box
                await self._human_click(left + 22, (top + bottom) / 2)
            await asyncio.sleep(10)
        if is_challenge_page(await self.tab.get_content()):
            raise ChallengeFailed("Could not get past the Cloudflare challenge")

    async def _dismiss_consent(self) -> None:
        """Accept the cookie banner; its overlay swallows clicks on the page.

        The choice is stored in the persistent profile, so this is usually a no-op.
        """
        button = await self.tab.select(".qc-cmp2-summary-buttons button[mode=primary]", timeout=5)
        if button:
            await button.mouse_click()
            await asyncio.sleep(1)

    async def _turnstile_box(self) -> tuple[float, float, float] | None:
        """Locate the Turnstile widget using only DOM-domain CDP calls (no JS eval)."""
        doc = await self.tab.send(cdp.dom.get_document(depth=-1))
        node_id = await self.tab.send(cdp.dom.query_selector(doc.node_id, TURNSTILE_SELECTOR))
        if not node_id:
            return None
        quads = await self.tab.send(cdp.dom.get_content_quads(node_id=node_id))
        if not quads:
            return None
        quad = quads[0]  # x1,y1 (top-left), x2,y2, x3,y3 (bottom-right), x4,y4
        return quad[0], quad[1], quad[5]

    async def _human_click(self, x: float, y: float) -> None:
        x += random.uniform(-3, 3)
        y += random.uniform(-3, 3)
        await self.tab.mouse_move(x - random.uniform(30, 60), y + random.uniform(20, 50))
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await self.tab.mouse_move(x, y, steps=random.randint(6, 12))
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await self.tab.mouse_click(x, y)
