/* How old something is, in the words the server already uses for it.
 *
 * **The server's `observations.in_words` and `ago`, written again here**, because
 * Walls states the age of a client's report beside a line it composes itself,
 * while Clients prints the server's own sentence ("It last reported 4 minutes
 * ago."). One report must read the same on both pages, so the units, the
 * boundaries and the rounding are the server's exactly: Python's `round` sends a
 * half to the even neighbour, and `Math.round` would not. `arrt/tests/unit/
 * test_ages.py` runs both over the same ages and fails on any that differ.
 *
 * Imports nothing and touches no DOM, so `node` can run it without a browser.
 */

/* Where each unit gives way to the next, and what to divide by once it does:
 * the server's `_UNITS`, read in order. */
const UNITS = [
  [90, 1, "second"],
  [90 * 60, 60, "minute"],
  [48 * 3600, 3600, "hour"],
  [Infinity, 86400, "day"],
];

/* Python's `round` on a float: a half goes to the even neighbour. */
function roundHalfEven(value) {
  const floor = Math.floor(value);
  const fraction = value - floor;
  if (fraction > 0.5) return floor + 1;
  if (fraction < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/* An age in the unit a person reads it in, with its direction: "4 minutes", or
 * "4 minutes in the future" for a report stamped ahead of this server's clock,
 * which is said as itself rather than folded into zero. */
export function inWords(seconds) {
  const magnitude = Math.abs(seconds);
  const [, divisor, unit] = UNITS.find(([limit]) => magnitude < limit);
  const count = roundHalfEven(magnitude / divisor);
  const phrase = `${count} ${unit}${count === 1 ? "" : "s"}`;
  return seconds >= 0 ? phrase : `${phrase} in the future`;
}

/* `inWords` as the tail of a sentence about when something happened. */
export function ago(seconds) {
  return seconds >= 0 ? `${inWords(seconds)} ago` : inWords(seconds);
}

/* How long ago an instant the server wrote was, from this browser's clock, in
 * the same words. For a record that carries no age of its own (a history
 * event); a heartbeat carries `age_seconds`, from the server's clock, and that
 * is the one to read for it. */
export function agoFrom(iso, now = Date.now()) {
  return ago((now - Date.parse(iso)) / 1000);
}
