/* Whether a screen is on the end of a client's output, in the words every screen uses.
 *
 * **`connected` is the client's hotplug reading, and a television switched off
 * reads exactly as one unplugged.** The client cannot tell the two apart (the
 * kernel reports the connector `disconnected` in both), so the words name both
 * rather than guessing: "none detected (off or unplugged)". "Not connected"
 * read as a cable fault on the evening the set was simply off.
 *
 * **A screen detected is the only state in which a wall is shown.** Walls says
 * "Shown by" from this and nothing else; the assignment alone says where a
 * wall is meant to go, not that anything is there. A report that has not
 * arrived, cannot be read, or does not list the output is *not known*, which is
 * its own sentence, never "none detected": a client not yet running is not a
 * television switched off.
 *
 * **Healthy is a different question**, and the top bar's (`core/status.js`): a
 * television switched off on purpose is an ordinary evening, so no state here
 * makes the product unwell. The owner ruled it so on 2026-10-07.
 *
 * A Frame output is reported connected because it is configured; whether the
 * television answers is the wall's own heartbeat (`clients.md` § What stays on
 * the client), so it reads as detected here.
 *
 * **A report older than `STALE_AFTER_SECONDS` says nothing about now.** A client
 * that crashed or lost its network leaves its last report behind, and that
 * report goes on saying "connected" for as long as anyone reads it. So past the
 * threshold the output is *stale*: not known now, with the report's age said.
 * Clients and Walls both read the threshold from here, so one report cannot be
 * current on one page and stale on the other. */

import { ago } from "./ages.js";

/* How often a Player reports, both its client heartbeat and each wall's:
 * `postarr/src/postarr/heartbeat.py`'s `INTERVAL_SECONDS`, which
 * `tests/preferences/test_staleness_threshold.py` holds this to. */
export const HEARTBEAT_INTERVAL_SECONDS = 60;

/* Three missed reports, not one: a report a few seconds late is a busy Pi, and
 * three in a row is a client that has stopped. */
export const STALE_AFTER_SECONDS = 3 * HEARTBEAT_INTERVAL_SECONDS;

export const DETECTED = "detected";
export const NOT_DETECTED = "not-detected";
export const NOT_REPORTED = "not-reported";
export const UNREADABLE = "unreadable";
export const NOT_LISTED = "not-listed";
export const STALE = "stale";

/* Whether a reading with this age is too old to say anything about now. A
 * reading with no age (never reported, unreadable) is not stale: it is one of
 * the states that say so in their own words. A report stamped ahead of this
 * server's clock is not stale either; its age is said as it is. */
export function isStale(reading) {
  return Boolean(reading) && typeof reading.age_seconds === "number" && reading.age_seconds > STALE_AFTER_SECONDS;
}

/* The state of one output, from a client's heartbeat as the client listing
 * carries it (`absent`, `problem`, `outputs`). */
export function screenState(heartbeat, outputName) {
  if (!heartbeat || heartbeat.absent) return NOT_REPORTED;
  if (heartbeat.problem) return UNREADABLE;
  if (isStale(heartbeat)) return STALE;
  const output = (heartbeat.outputs || []).find((each) => each.name === outputName);
  if (!output) return NOT_LISTED;
  return outputState(output);
}

/* The state of one output the report lists. The one place "detected" is
 * decided, so the Clients rows and the Walls line cannot come to disagree. */
export function outputState(output) {
  return output.connected ? DETECTED : NOT_DETECTED;
}

/* The Clients table's Screen column: glyph and word, as every badge here is.
 * From a stale report it says what was reported and that it is not known now. */
export function screenCell(output, stale = false) {
  if (stale) return outputState(output) === DETECTED ? "◌ not known now (was detected)" : "◌ not known now (was none detected)";
  return outputState(output) === DETECTED ? "● detected" : "○ none detected (off or unplugged)";
}

/* The output picker's parenthesis, where the column's words would not fit. */
export function screenPhrase(output, stale = false) {
  if (stale) return "screen not known now";
  return outputState(output) === DETECTED ? "screen detected" : "no screen detected";
}

/* Walls' line for a wall assigned to `clientName`'s `outputName`. `heartbeat`
 * is the client's reading, for the age a stale report states. */
export function wallScreenLine(clientName, outputName, state, heartbeat = null) {
  const assigned = `Assigned to ${clientName} on ${outputName}`;
  if (state === DETECTED) return `Shown by ${clientName} on ${outputName}`;
  if (state === NOT_DETECTED) return `${assigned}, where no screen is detected (off or unplugged)`;
  if (state === NOT_REPORTED) {
    return `${assigned}. ${clientName} has not reported its outputs yet, so whether a screen is there is not known.`;
  }
  if (state === UNREADABLE) {
    return `${assigned}. ${clientName}'s last report could not be read, so whether a screen is there is not known.`;
  }
  if (state === STALE) {
    return `${assigned}. ${clientName} last reported ${ago(heartbeat.age_seconds)}, so whether a screen is there now is not known.`;
  }
  if (state === NOT_LISTED) return `${assigned}. ${clientName}'s last report lists no output called ${outputName}.`;
  // A state added above and not worded here would otherwise fall through to a
  // sentence claiming one of the others.
  throw new Error(`no words for the screen state ${state}`);
}
