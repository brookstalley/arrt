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
 * the client), so it reads as detected here. */

export const DETECTED = "detected";
export const NOT_DETECTED = "not-detected";
export const NOT_REPORTED = "not-reported";
export const UNREADABLE = "unreadable";
export const NOT_LISTED = "not-listed";

/* The state of one output, from a client's heartbeat as the client listing
 * carries it (`absent`, `problem`, `outputs`). */
export function screenState(heartbeat, outputName) {
  if (!heartbeat || heartbeat.absent) return NOT_REPORTED;
  if (heartbeat.problem) return UNREADABLE;
  const output = (heartbeat.outputs || []).find((each) => each.name === outputName);
  if (!output) return NOT_LISTED;
  return outputState(output);
}

/* The state of one output the report lists. The one place "detected" is
 * decided, so the Clients rows and the Walls line cannot come to disagree. */
export function outputState(output) {
  return output.connected ? DETECTED : NOT_DETECTED;
}

/* The Clients table's Screen column: glyph and word, as every badge here is. */
export function screenCell(output) {
  return outputState(output) === DETECTED ? "● detected" : "○ none detected (off or unplugged)";
}

/* The output picker's parenthesis, where the column's words would not fit. */
export function screenPhrase(output) {
  return outputState(output) === DETECTED ? "screen detected" : "no screen detected";
}

/* Walls' line for a wall assigned to `clientName`'s `outputName`. */
export function wallScreenLine(clientName, outputName, state) {
  const assigned = `Assigned to ${clientName} on ${outputName}`;
  if (state === DETECTED) return `Shown by ${clientName} on ${outputName}`;
  if (state === NOT_DETECTED) return `${assigned}, where no screen is detected (off or unplugged)`;
  if (state === NOT_REPORTED) {
    return `${assigned}. ${clientName} has not reported its outputs yet, so whether a screen is there is not known.`;
  }
  if (state === UNREADABLE) {
    return `${assigned}. ${clientName}'s last report could not be read, so whether a screen is there is not known.`;
  }
  if (state === NOT_LISTED) return `${assigned}. ${clientName}'s last report lists no output called ${outputName}.`;
  // A state added above and not worded here would otherwise fall through to a
  // sentence claiming one of the others.
  throw new Error(`no words for the screen state ${state}`);
}
