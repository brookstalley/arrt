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
 * **The server judges it**, in each Player's `state` (`programming/player_state.py`
 * applies the contract's threshold), and every function here reads that state,
 * so one report cannot be current on one page and stale on another; the
 * threshold is kept here only for how long a screen waits for a report after
 * an act (`screens/walls.js`). */

import { ago } from "./dates.js";
import { GLYPHS } from "./glyphs.js";

/* How often a Player reports, both its client heartbeat and each wall's: the
 * contract's `timing.json`, which `arrt/tests/contract/test_staleness_threshold.py`
 * holds this to. */
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

/* One output of a Player as the server states it (`GET /api/clients`'s
 * `state.outputs`, `programming/player_state.py`): `{kind, name, state,
 * connected}`, or null where the server lists none by that name and kind. */
export function outputOf(player, outputName, kind = "display") {
  const outputs = player && player.state && Array.isArray(player.state.outputs) ? player.state.outputs : [];
  return outputs.find((each) => each.kind === kind && each.name === outputName) || null;
}

/* The state of one of a Player's screens, from the Player's state as the server
 * states it, never from its raw report: the server has already judged the
 * report's age against the contract's staleness (`timing.json`), so a report is
 * current on Walls exactly when it is on Players and on Status.
 *
 * A Player with no token, or no report yet, has not reported its screens; one
 * whose report cannot be read, or has stopped, cannot say; a reporting Player
 * whose report does not list the output does not have it now. */
export function screenState(player, outputName) {
  const playerState = player && player.state ? player.state.state : null;
  if (playerState === "report_unreadable") return UNREADABLE;
  if (playerState === "not_heard_from") return STALE;
  if (playerState !== "reporting") return NOT_REPORTED;
  const output = outputOf(player, outputName);
  if (!output || output.state !== "reporting") return NOT_LISTED;
  return outputState(output);
}

/* The state of one output the report lists. The one place "detected" is
 * decided, so the Players rows and the Walls line cannot come to disagree. */
export function outputState(output) {
  return output.connected ? DETECTED : NOT_DETECTED;
}

/* One output in a glyph and words, wherever a Player's outputs are listed
 * (Players, Status), from its state as the server states it
 * (`state.outputs[]`, whose `connected` is filled only while it is reporting):
 *
 * - reporting: a screen detected or none detected, a label panel answering or
 *   not connected. A label panel that is not connected is said as one and drawn
 *   as nothing being there (○), never as a fault: the server counts no trouble
 *   for it, and a Player with several panels, or only panels, reads the same way
 *   panel by panel (the owner's ruling 8 of 2026-11-19);
 * - an output the server recorded that a reporting Player's report does not
 *   list: not in its last report;
 * - a Player whose report has stopped or cannot be read: not known now, with
 *   what its last readable report said of the output (`was`, the reported
 *   `connected`, or null) where that is known;
 * - a Player with no token or no report yet: not reported yet. */
export function outputCell(output, player, was = null) {
  const playerState = player && player.state ? player.state.state : null;
  if (output.state === "reporting") {
    if (output.kind === "label") return output.connected ? `${GLYPHS.good} answering` : `${GLYPHS.none} not connected`;
    return output.connected ? `${GLYPHS.good} detected` : `${GLYPHS.none} none detected (off or unplugged)`;
  }
  if (playerState === "reporting") return `${GLYPHS.waiting} not in its last report`;
  if (playerState === "not_heard_from" || playerState === "report_unreadable") {
    if (was === null || was === undefined) return `${GLYPHS.waiting} not known now`;
    const said = output.kind === "label" ? (was ? "answering" : "not connected") : was ? "detected" : "none detected";
    return `${GLYPHS.waiting} not known now (was ${said})`;
  }
  return `${GLYPHS.waiting} not reported yet`;
}

/* A screen in the words a person reads (`information-architecture.md`
 * § Vocabulary: *HDMI 1*, not `hdmi-a-1`). The Player names its ports as the
 * kernel does, `hdmi-a-1` for the first HDMI connector, and a Samsung Frame by
 * its kind (`player-contract.md`), since it is reached over the network rather
 * than at a port; a port with no person's name here is shown as the Player
 * names it, never guessed at. */
export function screenName(outputName, kind = null) {
  if (kind === "frame") return "Samsung Frame";
  const hdmi = /^hdmi-[a-z]-(\d+)$/.exec(outputName);
  return hdmi ? `HDMI ${hdmi[1]}` : outputName;
}

/* The output picker's parenthesis, where the column's words would not fit. */
export function screenPhrase(output, stale = false) {
  if (stale) return "screen not known now";
  return outputState(output) === DETECTED ? "screen detected" : "no screen detected";
}

/* Walls' line for a wall assigned to `clientName`'s `outputName`. `heartbeat`
 * is the client's reading, for the age a stale report states. */
export function wallScreenLine(clientName, outputName, state, heartbeat = null) {
  return wallScreenParts(clientName, clientName, outputName, state, heartbeat).join("");
}

/* The same line in parts, with `named` (the client's name, or a link to it)
 * where the sentence first names the client and its plain `clientName` after,
 * so a line names its client once as a link and not twice.
 *
 * `outputName` null leaves the output unnamed: Walls names a port only with
 * `?debug` (the owner's ruling 1 of 2026-10-11), since on Walls the port is
 * engineering detail. `offSaid` drops the
 * "no screen is detected" clause where the line's reader has just been told the
 * screen is off, so the page says it once. */
export function wallScreenParts(named, clientName, outputName, state, heartbeat = null, { offSaid = false } = {}) {
  const on = outputName ? ` on ${outputName}` : "";
  const assigned = ["Assigned to ", named, on];
  if (state === DETECTED) return ["Shown by ", named, on];
  if (state === NOT_DETECTED && offSaid) return assigned;
  if (state === NOT_DETECTED) return [...assigned, ", where no screen is detected (off or unplugged)"];
  if (state === NOT_REPORTED) {
    return [...assigned, `. ${clientName} has not reported its outputs yet, so whether a screen is there is not known.`];
  }
  if (state === UNREADABLE) {
    return [...assigned, `. ${clientName}'s last report could not be read, so whether a screen is there is not known.`];
  }
  if (state === STALE) {
    return [...assigned, `. ${clientName} last reported ${ago(heartbeat.age_seconds)}, so whether a screen is there now is not known.`];
  }
  if (state === NOT_LISTED) {
    return [
      ...assigned,
      outputName ? `. ${clientName}'s last report lists no output called ${outputName}.` : `. ${clientName}'s last report does not list the output this wall is assigned to.`,
    ];
  }
  // A state added above and not worded here would otherwise fall through to a
  // sentence claiming one of the others.
  throw new Error(`no words for the screen state ${state}`);
}
