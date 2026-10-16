/* Every date and age the client shows, in one place: a readable date and how
 * long ago it was.
 *
 * **One formatter, because a timestamp reaching the page as the server spells
 * it is the failure this exists to end**: `2026-10-05T14:46:52.225416+00:00`
 * wrapping every row of To review and History (`ux-review-2026-10.md` finding
 * 20). A screen showing a moment shows `dated` (or `stamp`, for a `<time>`);
 * the instant itself goes only into the element's `datetime`, or inside a
 * Details disclosure where raw fields are the point.
 * `tests/unit/test_one_date_formatter.py` refuses a date formatted anywhere
 * else in the client.
 *
 * **The ages are the server's `observations.in_words` and `ago`, written again
 * here**, because Walls states the age of a client's report beside a line it
 * composes itself, while Clients prints the server's own sentence ("It last
 * reported 4 minutes ago."). One report must read the same on both pages, so
 * the units, the boundaries and the rounding are the server's exactly: Python's
 * `round` sends a half to the even neighbour, and `Math.round` would not.
 * `arrt/tests/unit/test_ages.py` runs both over the same ages and fails on any
 * that differ.
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

/* A moment as a person reads it, in this browser's language and time zone:
 * "5 Oct 2026, 14:46". An instant that will not parse is said to be unknown
 * rather than shown as the string it arrived as. */
export function readable(iso) {
  const at = new Date(iso);
  if (iso === null || iso === undefined || Number.isNaN(at.getTime())) return "an unknown time";
  return at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* The readable date and how long ago it was, together: "5 Oct 2026, 14:46
 * (3 days ago)". The one way a moment is written on a screen. */
export function dated(iso, now = Date.now()) {
  const date = readable(iso);
  if (date === "an unknown time") return date;
  return `${date} (${agoFrom(iso, now)})`;
}

/* `dated` as a `<time>` element's attributes, for `el("time", stamp(iso))`:
 * the words as its text, and the instant where a machine reads it. */
export function stamp(iso, now = Date.now()) {
  return { datetime: iso, text: dated(iso, now) };
}
