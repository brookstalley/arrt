"""The page under test, with the few things every browser test needs.

Here rather than in `conftest.py` so a test that builds a page of its own can import it:
`conftest` in `sys.modules` is whichever conftest was imported last, so `from conftest
import Ui` finds `system/conftest.py`, or the suite's root one, whenever other directories
are collected in the same run (`report_guard.py` says the same of its own module).
`conftest.py`'s `ui` fixture is the one most tests take.
"""

import io
import json

from PIL import Image


class Ui:
    """The page under test, with the few things every test here needs.

    Thin on purpose: the point of this level is that Playwright's own waiting is
    doing the work, so wrapping locators in helpers would only hide which
    assertion is actually waiting for what.
    """

    def __init__(self, page, base_url: str):
        self.page = page
        self.base_url = base_url
        self.requests: list[str] = []
        page.on("request", lambda request: self.requests.append(request.url))

    def open(self, fragment: str = "") -> None:
        """Load the shell and wait for the client's first paint to land."""
        url = f"{self.base_url}/{fragment}"
        same_document = self.page.url.partition("#")[0] == url.partition("#")[0]
        self.page.goto(url)
        # A goto that changes only the fragment is a hashchange, not a load: the
        # waits below would be met by the screen still painted, and a test that
        # opens a page again to read what the server kept would read what the
        # client still holds. So it is reloaded, as a person returning would.
        if same_document:
            self.page.reload()
        # The client marks <html> once it has started (`app.js`). The view is
        # served holding a "Loading the Library…" placeholder, so waiting on
        # its content returned before the script had run, and a test could act
        # on a top bar with nothing installed behind it. Then the first paint's
        # content, as before: `data-started` is set before the paint begins.
        self.page.wait_for_selector("html[data-started]", state="attached")
        self.page.wait_for_selector("#view *")

    def navigate(self, fragment: str) -> None:
        """Move to another page inside the client, as its links do, keeping what
        the client holds in memory: for a test about a page the curator comes
        back to. The new page may not have painted on return, so the caller waits
        on something only that page draws."""
        self.page.goto(f"{self.base_url}/{fragment}")

    def serve(self, pattern: str, payloads) -> None:
        """Answer `pattern` with each payload in turn; the last one repeats.

        A list rather than one body, because several behaviours here are about
        what happens *across* successive answers — a poll that changes nothing
        and then one that does — which a route with a single answer could not
        express.

        An entry may be a plain dict, answered 200, or a `(status, body)` pair.
        The pair is what lets a sequence express a *failing* answer, which the
        client's own failure model needs: "one blip then fine" and "broken from
        the first request and staying broken" are different behaviours, and
        neither can be written with successes alone.
        """
        entries = [payloads] if isinstance(payloads, (dict, tuple)) else list(payloads)
        served = {"count": 0}

        def handler(route):
            index = min(served["count"], len(entries) - 1)
            served["count"] += 1
            entry = entries[index]
            status, body = entry if isinstance(entry, tuple) else (200, entry)
            route.fulfill(
                status=status,
                content_type="application/json",
                body=json.dumps(body),
            )

        self.page.route(pattern, handler)

    def serve_image(self, pattern: str, *, colour=(84, 66, 132)) -> None:
        """Answer `pattern` with a real JPEG the browser can actually decode.

        Real bytes rather than a stub, because the assertion this supports is
        that a picture *renders* — a card whose `<img>` fails silently paints a
        blank box, which is the exact failure the review grid must not have, and
        an undecodable stub would make every such test look like that failure.
        """
        buffer = io.BytesIO()
        Image.new("RGB", (240, 180), colour).save(buffer, format="JPEG")
        body = buffer.getvalue()
        self.page.route(
            pattern,
            lambda route: route.fulfill(status=200, content_type="image/jpeg", body=body),
        )

    @property
    def view(self):
        """The screen's own region, for `expect(ui.view).to_contain_text(…, use_inner_text=True)`."""
        return self.page.locator("#view")

    def text(self) -> str:
        """The view's words, read once: the read `expect(ui.view)` replaces (`docs/testing.md`)."""
        return self.page.inner_text("#view")  # one-shot: counted where each caller asserts on it

    def focused(self) -> str:
        """What the keyboard is standing on, named so a test can assert it."""
        return self.page.evaluate(
            "() => { const a = document.activeElement;" " return a ? (a.id || a.textContent || a.tagName) : 'none'; }"
        )

    def said_beside(self, control) -> str:
        """The failure `core/acting.js` put directly after `control`, once said.

        Asserted to be the alert beside the control and not the page's banner,
        which a failed act no longer uses: where the sentence is, is the claim.
        """
        # The element directly after the control, and only once it is the
        # failure with words in it: the control's own neighbour (Reject beside
        # Accept) has text too, and waiting on "the next sibling has text" would
        # pass on that before the failure arrived.
        # Here rather than at the top: this module is imported without the browser group installed.
        from playwright.sync_api import expect

        beside = control.locator(
            "xpath=following-sibling::*[1][contains(concat(' ', @class, ' '), ' act-failure ')]"
            "[@role='alert'][normalize-space(.) != '']"
        )
        beside.wait_for(state="visible")
        expect(self.page.locator("#error"), "a failed act was reported in the banner as well").to_be_hidden()
        # The sentence is written into the alert in one go, and the wait above
        # is for it to have words: what is read is the whole of it.
        return beside.inner_text()  # one-shot: read once the alert has its words, which arrive in one write

    def open_folds(self) -> None:
        """Open Review's fold lines, for a test about a card that starts folded.

        Review folds decided cards and found-none cards behind one line each
        (`test_review_folds.py` holds that); a test about such a card's own
        behaviour opens the lines first, as a curator would.
        """
        self.page.wait_for_selector("#view li.review-card", state="attached")
        self.page.evaluate("() => document.querySelectorAll('#view details.fold').forEach((d) => { d.open = true; })")

    def requests_matching(self, needle: str) -> list[str]:
        return [url for url in self.requests if needle in url]

    def show_more(self, *, until: int | None = None, presses: int = 400) -> None:
        """Press Artworks' *Show more* until `until` tiles are on screen, or until it is gone.

        As a keyboard user reaches the end of a grid that pages as it scrolls.
        The scroll asks for pages too — pressing brings the row into view — so
        a press can find the button moving under a page arriving, or gone once
        the last one has; each is retried rather than read as a failure.
        """
        # Here rather than at the top: this module is collected without the
        # browser group installed, and only a browser test reaches this line.
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        tiles = self.page.locator("ul.grid > li")
        for _ in range(presses):
            # A loop that polls, rather than an assertion: each read decides
            # whether to press again, and the next turn reads again.
            if until is not None and tiles.count() >= until:  # one-shot: polled, once a press
                return
            button = self.page.locator("#view button.show-more")
            if button.count() == 0:  # one-shot: polled, once a press
                if until is not None:
                    raise AssertionError(f"Show more ran out at {tiles.count()} tiles, short of {until}")  # one-shot: the message
                return
            try:
                button.click(timeout=2_000)
            except PlaywrightTimeoutError:
                continue
        raise AssertionError(f"Show more was still offered after {presses} presses")
