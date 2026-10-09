"""Pins on a phone whose stream has gone quiet without failing.

On an iPhone home-screen PWA, the EventSource often comes back from the
background neither delivering nor erroring. No onerror means no reconnect, and
the reconnect was the only thing re-reading /api/pinned on a streamless board
(see test_pins_follow_fallback_live.py, whose harness aborts the stream and so
always reconnects). The fallback poll and the return-to-page refetch re-read
sessions only.

So one failed pin read -- a phone's first request after waking often is one --
left every card drawn unpinned until a reload, and a pin made on the desktop
never reached the phone at all. Reported as: "on the iPhone the priority
widget sometimes looks unpinned; the desktop is fine".
"""

import pytest

import live_board
from live_board import open_board


def quadrant_of(page, name):
    return page.evaluate(
        """name => {
             const card = document.querySelector(`[data-session-name="${name}"]`);
             if (!card) return null;
             const box = card.closest('[data-quadrant]');
             return box ? box.dataset.quadrant : null;
           }""",
        name,
    )


@pytest.fixture
def phone(request):
    """A board whose stream hangs, optionally after N failed pin reads."""
    saved = (live_board.STREAM, live_board.PIN_READS_TO_FAIL)
    live_board.STREAM = "hang"
    live_board.PIN_READS_TO_FAIL = getattr(request, "param", 0)
    try:
        with open_board() as page:
            yield page
    finally:
        live_board.STREAM, live_board.PIN_READS_TO_FAIL = saved


@pytest.mark.parametrize("phone", [1], indirect=True)
def test_a_failed_first_pin_read_does_not_leave_everything_unpinned(phone):
    phone.wait_for_timeout(500)
    assert quadrant_of(phone, "claude_alpha") is None, "precondition: drawn unpinned"
    # The fallback poll runs every 5s; the next one has to fetch the pins too.
    phone.wait_for_timeout(7000)
    assert quadrant_of(phone, "claude_alpha") == "Q1"


def test_the_fallback_poll_follows_a_pin_made_elsewhere(phone):
    assert quadrant_of(phone, "claude_beta") == "Q2"
    phone.ctb_accepted.append({"Q1": ["claude_alpha", "claude_alpha_wt_topic", "claude_beta"],
                               "Q2": [], "Q3": [], "Q4": []})
    phone.wait_for_timeout(16000)            # 5s poll, 10s pin-read throttle
    assert quadrant_of(phone, "claude_beta") == "Q1"


def test_coming_back_to_the_app_reads_the_pins_at_once(phone):
    """Returning is exactly when the phone is most likely out of date, so it
    does not wait out the throttle."""
    assert quadrant_of(phone, "claude_alpha") == "Q1"
    phone.ctb_accepted.append({"Q1": ["claude_alpha_wt_topic"], "Q2": ["claude_beta"],
                               "Q3": [], "Q4": ["claude_alpha"]})
    phone.wait_for_timeout(1000)             # inside the 10s throttle on purpose
    phone.evaluate(
        """() => {
             Object.defineProperty(document, 'visibilityState',
               { configurable: true, get: () => 'visible' });
             document.dispatchEvent(new Event('visibilitychange'));
           }""")
    phone.wait_for_timeout(1500)
    assert quadrant_of(phone, "claude_alpha") == "Q4"
