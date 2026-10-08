/* One Get, watched while it works, at `#get/<id>`.
 *
 * Contextual: opened from Activity's Queue or History, from Ask as it
 * starts, or from a Get again started on the review grid or Wanted — and it
 * returns to the page it was opened from. The server calls it a run; the
 * curator reads a Get.
 *
 * **A Get's page is its review.** A Get's works were chosen by the curator, so
 * the review cards stand where a discovery run's work table stands, and there
 * is no second page to go to (the owner's ruling, 2026-10-02).
 */

import { attempt } from "../core/acting.js";
import { api, fetchAllCandidates } from "../core/api.js";
import { facts, reasonBadge, resolutionBadge, table } from "../core/badges.js";
import { agree, agreePartitive, counted } from "../core/counting.js";
import { destinationOf, destinationSentence, readThemes } from "../core/destination.js";
import { claimPoll, pollIsCurrent, schedulePollUnlessDone } from "../core/poll.js";
import { el, guard, render } from "../core/render.js";
import { museumName } from "../core/providers.js";
import { reviewSection, rowPicture } from "../core/reviewing.js";
import { backLink, link, refresh, setTitle } from "../core/router.js";
import { runTitle } from "../core/runs.js";
import { dollars, tierMark } from "../core/spend.js";
import { state } from "../core/state.js";

/* What this run's state means, in a sentence.
 *
 * Composed here rather than taken from the MCP surface's notice, which is
 * written for a model — it names fields in backticks and tells the caller to
 * call status again, neither of which is true of a page with buttons on it. The
 * numbers are the part that must not be written twice, and they are not: every
 * figure below is read from the tally the server computed.
 *
 * THE RATE IS STATED OVER WHAT THE MODEL PROPOSED, NEVER OVER THE TOTAL. Works a
 * collection offered arrived carrying their own images, so counting them in the
 * numerator reports a retrieval rate the run never achieved — with twelve
 * offered works behind one unresolved proposal, "12 of 13" describes a run that
 * in fact resolved nothing it was asked for. */
/* An if-chain rather than an object literal like the badge maps in `core`, and
 * the asymmetry is a decision rather than an oversight: several of these branches
 * read the tally, the run kind and whether image resolution is wired, so a map
 * of bare strings could not hold them. The cost is that the checker which reads
 * those maps cannot parse this, so `test_every_run_status_is_named_in_the_client`
 * takes the weaker form of asserting each status value appears somewhere in the
 * client — enough to fail when a tenth state is added, which is the property
 * wanted. */
export function runSentence(view) {
  const run = view.run;
  const tally = view.tally;
  if (run.status === "resolving_works") {
    return "Working out which works match the intent.";
  }
  if (run.status === "awaiting_approval") {
    // Only a run stored here before asking became the approval: no run stops
    // to ask any more, and these are decided as they always were.
    return `This Get proposed ${counted(tally.proposed, "work")} and stopped to ask, as a long list once did. Nothing further is spent until you decide.`;
  }
  if (run.status === "resolving_images") {
    if (!view.image_resolution_available) {
      // A discovery run's works to find are the ones it proposed; a re-search's
      // and a Get's are every work they hold.
      const waiting = run.kind === "discovery" ? tally.proposed : tally.total;
      return `There ${agree(waiting, "is", "are")} ${counted(waiting, "work")} to find images for, but no image provider is configured in this deployment, so the Get will stay here. Cancel it when you are done reading it.`;
    }
    if (run.kind === "resolve") {
      return `Looking again for images of the ${counted(tally.total, "work")} this Get covers.`;
    }
    if (run.kind === "get") {
      return `Looking for images of the ${counted(tally.chosen, "work")} you chose.`;
    }
    return `The work list of ${counted(tally.proposed, "work")} is settled, and the Get is looking for an image of each.`;
  }
  if (run.status === "completed") {
    // Both figures are counted and only one of them is the subject: in "1 of the
    // 2 works it covers", the head is the *1*. Keying the agreement on the
    // number printed immediately before the verb is the mistake that reads
    // right, and it shipped "1 of the 2 works it covers have an image" on the
    // screen a curator lands on first — the same disagreement `counting.js` was
    // written for, moved from the trailing count to the leading one.
    let sentence =
      run.kind === "resolve"
        ? `This Get finished: ${tally.resolved} of the ${counted(tally.total, "work")} it covers ${agreePartitive(tally.resolved, tally.total, "has", "have")} an image.`
        : run.kind === "get"
          ? `This Get finished: ${tally.resolved} of the ${counted(tally.chosen, "work")} you chose ${agreePartitive(tally.resolved, tally.chosen, "has", "have")} an image.`
          : // A Get from words says its figures as three counts under this line
            // (`runCounts`) rather than in it: the paragraph it replaced printed
            // two different counts that are often the same number, and a curator
            // could not tell which was which.
            "This Get finished.";
    if (tally.unresolved && run.kind !== "discovery") {
      sentence += ` ${tally.unresolved} could not be matched to any image and ${agree(tally.unresolved, "is", "are")} reported rather than dropped — each says which kind of nothing below.`;
    }
    if (tally.pending) {
      // Held apart from unresolved deliberately. "We looked and it is not
      // there" and "we could not look" lead to opposite actions, and merging
      // them tells a curator their painting does not exist because a museum was
      // briefly unreachable.
      sentence += ` ${tally.pending} could not be looked up at all — the image provider was unreachable for ${agree(tally.pending, "it", "them")}, which says nothing about whether ${agree(tally.pending, "it exists", "they exist")}.`;
    }
    return sentence;
  }
  if (run.status === "halted_by_budget") {
    // The provider's refusal at the cap is the server's `end_reason`, said on
    // the line beneath ("This month's budget is spent…").
    return "The provider refused further spend, so this Get stopped where it was. Asking again will fail the same way until the month's budget resets or is raised.";
  }
  if (run.status === "interrupted") {
    return "The process working on this Get stopped underneath it — a restart or a crash, not a fault in the Get. Start it again with the same intent.";
  }
  if (run.status === "failed") {
    // The reason itself is the line beneath this one. Only a run that failed
    // before reasons were kept has nothing but the log to send a curator to.
    return run.end_reason
      ? "This Get hit an error and stopped."
      : "This Get hit an error and stopped. The server log has the details.";
  }
  if (run.status === "declined") {
    return "The work list was declined, so no images were looked for and nothing further was spent.";
  }
  if (run.status === "cancelled") {
    return "This Get was cancelled. Anything already spent is still recorded.";
  }
  return `This Get is ${run.status}.`;
}

/* Slow enough not to hammer a Pi, fast enough that a curator watching a run does
 * not wonder whether the page is live. The server answers immediately rather
 * than holding the request open, so this interval is the whole of the latency. */
export const RUN_POLL_MS = 2000;

/* How many consecutive failures end the watch, and why a count rather than a
 * backoff curve.
 *
 * Two things actually happen here, and neither is the case backoff is for. A
 * blip — one 502, a request caught by a service restart — recovers within a tick
 * or two. A permanent condition — a bookmarked `#run/<id>` for a run that no
 * longer exists, which the service answers 400 — never recovers, and every retry
 * is identical. Backoff optimises the case in between, a long outage that comes
 * good, and there is no such case here: this server is on the same box in the
 * same house as the browser, so if it is unreachable for minutes the whole page
 * is dead and reloading is the natural move, not waiting out a curve.
 *
 * Five, because the realistic multi-second interruption is the operator
 * restarting the curation service while watching a run, and five attempts at
 * two-second spacing rides out about ten seconds of that. A stale bookmark fails
 * all five inside those ten seconds and then stops, instead of asking for a run
 * that will never exist every two seconds for as long as the tab stays open. */
export const RUN_POLL_MAX_FAILURES = 5;


/* A run's works in sections: the ones it was asked for, then the ones a
 * museum offered on top of them, under that museum's name, one section per
 * museum. Every row carries the picture found for it.
 *
 * The asked-for rows say why the run named each work, which is what a curator
 * judges a list by. The offered rows do not: the run named none of them, and
 * the heading says once what a per-row column used to say on every row. Which
 * museum offered a work is the museum of the scan it arrived with, the card's
 * `shown`; one whose card could not be read sits under "the collection". */
function worksBySource(works, reviewPage) {
  const cards = new Map((reviewPage ? reviewPage.works : []).map((card) => [card.work.work_id, card]));
  const asked = works.filter((work) => work.provenance !== "offered");
  const offeredBy = new Map();
  for (const work of works.filter((each) => each.provenance === "offered")) {
    const card = cards.get(work.work_id);
    const museum = card && card.shown ? museumName(card.shown.provider) : "the collection";
    if (!offeredBy.has(museum)) offeredBy.set(museum, []);
    offeredBy.get(museum).push(work);
  }
  const rowOf = (work) => [rowPicture(cards.get(work.work_id)), work.title, work.artist || "—", el("div", { class: "stack-tight" }, [resolutionBadge(work), reasonBadge(work)])];
  const sections = [];
  if (asked.length) {
    sections.push(
      el("section", { class: "asked-for" }, [
        el("h3", { text: `Asked for (${asked.length})` }),
        table(
          "The works this Get was asked for, each with the picture found for it and why the run named it.",
          ["Picture", "Title", "Artist", "Image", "Why it is here"],
          asked.map((work) => [...rowOf(work), work.rationale]),
          { stacked: true },
        ),
      ]),
    );
  }
  for (const [museum, offered] of offeredBy) {
    sections.push(
      el("section", { class: "offered" }, [
        el("h3", { text: `Also offered by ${museum} (${offered.length})` }),
        table(
          `Works ${museum} offered on top of the ones asked for, each with its picture.`,
          ["Picture", "Title", "Artist", "Image"],
          offered.map(rowOf),
          { stacked: true },
        ),
      ]),
    );
  }
  return sections;
}

/* A finished Get from words, as three counts: how many works it was asked
 * for, how many of those were found with an image, and how many could not be
 * matched to one. Offered works are not among them; they are listed under the
 * museum that offered them. Null for any other run, whose sentence carries its
 * own figures. */
function runCounts(view) {
  if (view.run.kind !== "discovery" || view.run.status !== "completed") return null;
  const list = facts([
    ["Asked for", view.tally.proposed],
    ["Found with an image", view.tally.resolved_proposals],
    ["Not matched", view.tally.unresolved],
  ]);
  list.classList.add("run-counts");
  return list;
}
/* Consecutive failures for the run currently being watched.
 *
 * Keyed by run id rather than by poll generation, though the issue that produced
 * it said generation: `state.poll` increments on *every* poll, so a
 * generation-keyed count would reset itself each tick and never reach any
 * threshold. What has to survive a tick is the watch, and what identifies a
 * watch is which run it is on — so opening a different run starts fresh, and a
 * success anywhere clears it. */
function noteWatchFailure(runId) {
  if (state.watch === null || state.watch.runId !== runId) state.watch = { runId, failures: 0 };
  state.watch.failures += 1;
  return state.watch.failures;
}

function noteWatchSuccess(runId) {
  state.watch = { runId, failures: 0 };
}

/* The next look at a run, deferring the timer and the generation guard to
 * `core/poll.js` and binding the two things that are this screen's own: which
 * view is being watched and how often. `done` is whether the run has stopped,
 * which the caller reads off the server rather than off a list of finished
 * states written here.
 *
 * **`done` is required and deliberately has no default.** The only value a
 * default could take is `false`, which means "keep polling forever" — so a
 * fourth call site that forgot the argument would get the silent failure this
 * whole chain exists to prevent, and would get it looking correct. */
function scheduleRunPoll(runId, generation, { done }) {
  schedulePollUnlessDone({ view: "get", detailId: runId, generation, intervalMs: RUN_POLL_MS, done });
}

/* The Get's works section this screen last painted, and under which navigation.
 *
 * Handed to the next paint of the same page so the cards whose works have not
 * changed are kept rather than rebuilt (`core/reviewing.js`). Keyed by the
 * navigation alone, because every navigation moves it — to another run, or
 * back to this one later — and a section from an earlier visit is not one the
 * curator is still working in. Module scope rather than `state`, as that file
 * asks of one screen's own bookkeeping. */
let shownReview = null;

export async function viewRun(runId, generation) {
  // Claimed at the top and checked after every await. This paint supersedes any
  // earlier one, and an earlier one still in flight must not paint over it or
  // schedule a second timer beside its own — pressing Approve while a poll is
  // mid-request is enough to have two running, and two chains double the request
  // rate on every tick thereafter.
  const pollGeneration = claimPoll();
  let view;
  try {
    view = await api(`/api/runs/${encodeURIComponent(runId)}`);
  } catch (failure) {
    // One blip must not end the watch. Without re-arming, the throw leaves the
    // last paint on screen looking current, `guard` writes a message naming a
    // URL, and no further poll is ever scheduled — so a curator watching a live
    // run through a single 502 is left with a stale page that never recovers
    // and never says it stopped.
    //
    // But re-arming unconditionally has no notion of *consecutive* failures, so
    // it did the same thing for a permanent one. Opening a stale bookmarked
    // `#run/<id>` after the run is gone had the service answer 400, the catch
    // re-arm, and the tab request that run every two seconds for as long as it
    // stayed open — bounded only by navigation, with nothing on screen saying
    // the watch was still retrying.
    if (noteWatchFailure(runId) >= RUN_POLL_MAX_FAILURES) {
      // Say the watch stopped, not only what failed. The two are different
      // facts and only one of them tells the curator what to do next: a message
      // naming a 400 leaves a live page indistinguishable from a dead one.
      throw new Error(
        `${failure.message} Gave up watching this Get after ${RUN_POLL_MAX_FAILURES} attempts — ` +
          "reload the page to start watching again."
      );
    }
    // Re-arm first, then re-throw so the message is still shown: the next tick
    // repaints and clears it if the blip has passed. Nothing is known about
    // whether the run has stopped — the request that would have said so is the
    // one that just failed — so this arm is unconditional by construction.
    scheduleRunPoll(runId, pollGeneration, { done: false });
    throw failure;
  }
  if (!pollIsCurrent(pollGeneration)) return;
  // A reachable run resets the count, so a watch is only ever ended by failures
  // with nothing between them. Recorded here rather than after the paint: what
  // the count is about is whether the server answered, and it just did.
  noteWatchSuccess(runId);
  const run = view.run;
  const tally = view.tally;

  /* A poll that repaints an unchanged view is not free: `render` replaces the
   * whole subtree, which destroys whatever the keyboard user was standing on —
   * so tabbing to "Approve" and pausing to read loses the focus two seconds
   * later, every time, on the one screen whose whole job is to be decided on.
   * Nothing changed means nothing to touch. Compared against the payload rather
   * than against the status alone, because a work list filling in underneath a
   * settled status is exactly the change worth repainting for. */
  const body = JSON.stringify(view);
  if (state.painted !== null && state.painted.runId === runId && state.painted.body === body) {
    scheduleRunPoll(runId, pollGeneration, { done: run.is_terminal });
    return;
  }

  // Read only when the page is about to be painted, so an unchanged poll costs
  // no second request. A failure is said in the sentence rather than thrown:
  // the watch must not end because a theme's name could not be read.
  const themes = await readThemes();
  if (!pollIsCurrent(pollGeneration)) return;

  // The gate is the point of decision for phase 2, so its price and what that
  // price is made of belong beside the buttons rather than on a costs panel
  // further down. Asked for only at the gate: every other state either has no
  // decision pending or has already spent whatever it was going to.
  let gateEstimate = null;
  let gateEstimateProblem = null;
  if (run.status === "awaiting_approval") {
    // A failure to price must not cost the curator their approve button — the
    // estimate explains a decision, it is not the decision. But it is said
    // rather than swallowed: a gate that silently stops showing a price looks
    // exactly like a gate whose price is nothing.
    try {
      gateEstimate = await api(`/api/estimate?run_id=${encodeURIComponent(runId)}`);
    } catch (failure) {
      gateEstimateProblem = `The cost of approving could not be read: ${failure.message}`;
    }
    if (!pollIsCurrent(pollGeneration)) return;
  }

  /* What asking for this actually cost, all in. The run record carries only its
   * OWN spend, so a run billed little whose re-searches cost ten times more
   * reads as cheap from the run alone — and "what did asking for Dalí cost" is
   * the family total, which lives nowhere else. Fetched once the run has
   * stopped: while it is still working the figure is mid-flight, and a total
   * that climbs under a heading saying what something cost invites reading a
   * partial as a final. */
  let familySpend = null;
  let familySpendProblem = null;
  if (run.is_terminal) {
    try {
      familySpend = await api(`/api/runs/${encodeURIComponent(runId)}/spend`);
    } catch (failure) {
      // Said, not swallowed — the same call the gate estimate makes above, for
      // the same reason. Losing the rollup must not cost the curator the costs
      // panel, and it must not do so in silence either: this is the only place
      // the family total appears, so a panel that quietly drops the row leaves
      // "Spent by this run alone" reading as what asking cost, which is the
      // exact misreading that row was added to prevent.
      familySpendProblem = `The total including every Get again could not be read: ${failure.message}`;
    }
    if (!pollIsCurrent(pollGeneration)) return;
  }

  /* The works as review cards, read only when the page is about to be
   * painted, like the themes above: a Get of chosen works is judged here as
   * cards, and every other run's rows take their pictures and the museum that
   * offered them from the same cards. A failure is said where the works would be
   * rather than thrown: the watch, the sentence and the costs are still worth
   * having, and a Get page that went blank because one listing failed would
   * hide that the Get itself is fine. */
  let reviewPage = null;
  let reviewProblem = null;
  if (view.works.length) {
    try {
      reviewPage = await fetchAllCandidates(runId);
    } catch (failure) {
      // A Get still looking asks again on its next look, because this paint is
      // not recorded as one to leave alone (below). A finished one is not
      // watched, so nothing on the page will ask again and the curator is told
      // what will.
      reviewProblem = `This Get's works could not be read: ${failure.message}`;
      if (run.is_terminal) reviewProblem += " Reload the page to try again.";
    }
    if (!pollIsCurrent(pollGeneration)) return;
  }

  /* What the keyboard is standing on, read before anything below is built.
   * Keeping a card means lifting it out of the page into the new one, and the
   * browser drops focus from anything lifted out — so it is read here and given
   * back once the paint lands, where it is still on the page. */
  const focused = document.activeElement;
  const keptFrom = shownReview !== null && shownReview.generation === generation ? shownReview.section : null;

  const decisions = el("div", { class: "row" }, [
    run.status === "awaiting_approval"
      ? el("button", {
          class: "action",
          type: "button",
          text: "Approve the list",
          onclick: (event) =>
            attempt(event.currentTarget, "approve the list", () => api(`/api/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" }), {
              then: () => refresh(),
            }),
        })
      : null,
    run.status === "awaiting_approval" && gateEstimate ? tierMark(gateEstimate.tier) : null,
    run.status === "awaiting_approval"
      ? el("button", {
          class: "action quiet",
          type: "button",
          text: "Decline it",
          onclick: (event) =>
            attempt(event.currentTarget, "decline the list", () => api(`/api/runs/${encodeURIComponent(runId)}/decline`, { method: "POST" }), {
              then: () => refresh(),
            }),
        })
      : null,
    run.is_terminal
      ? null
      : el("button", {
          class: "action quiet",
          type: "button",
          text: "Cancel",
          "aria-label": "Cancel this Get",
          onclick: (event) =>
            attempt(event.currentTarget, "cancel this Get", () => api(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }), {
              then: () => refresh(),
            }),
        }),
  ]);

  setTitle(generation, runTitle(run));
  const panels = [
    el("p", {}, [backLink()]),
    el("h1", { text: runTitle(run) }),
    el("div", { class: "panel" }, [
      el("p", { class: "note", text: runSentence(view) }),
      runCounts(view),
      // Why the worker ended it, in its own words, under the sentence saying
      // what that ending means. Text, never markup: a halt's reason quotes the
      // provider.
      run.end_reason ? el("p", { class: "muted run-end-reason", text: `Why it stopped: ${run.end_reason}` }) : null,
      // The engine's own reading of the request, beside the request. A work list
      // is judged against how the intent was read rather than against its
      // wording, which is what makes a surprising list explicable.
      run.strategy ? el("p", { class: "muted", text: `How it read the request: ${run.strategy}` }) : null,
      el("p", { class: "muted run-destination", text: destinationSentence(destinationOf(run, themes)) }),
      // What approving commits to, in the place the commitment is made. The
      // second sentence is the load-bearing half: the figure is zero because
      // finding images asks museum APIs, and a bare "$0" beside an approve
      // button invites the reading that the gate is about money. It is about
      // the size of the work list, and the sentence says so.
      gateEstimate
        ? el("p", {
            class: "muted",
            text: `Approving costs ${dollars(gateEstimate.estimated_cost_usd)}. Finding the images asks museums, which is free, so what approving decides is the size of the list.`,
          })
        : null,
      gateEstimateProblem ? el("p", { class: "note", text: gateEstimateProblem }) : null,
      decisions,
    ]),
    el("div", { class: "panel" }, [
      el("h2", { text: "What it cost" }),
      facts([
        // Named for what it actually is. This figure is written when phase 1
        // finishes and the work count is known, so it prices *resolving the work
        // list* — labelling it as the estimate made before starting would put
        // the phase-1 price under a heading describing phase 2.
        ["Estimated to find the images", run.estimated_cost_usd === null ? null : dollars(run.estimated_cost_usd)],
        // Labelled as this run's own, because that is what it is: the record
        // carries `run_cost(run_id).direct`. Left unqualified it reads as the
        // whole cost of having asked, which it is not the moment a re-search
        // descends from it.
        ["Spent by this Get alone", run.actual_cost_usd === null ? null : dollars(run.actual_cost_usd)],
        // The family total — what asking for this cost altogether, re-searches
        // included. A run billed little whose re-searches cost ten times more is
        // exactly the case the two figures exist to keep apart, and it is the
        // only place this number appears.
        [
          "Spent including every Get again",
          familySpend === null ? null : dollars(familySpend.cost_usd),
        ],
        // Two numbers, never a verdict: the usage is this run's history and the
        // allowance is the deployment's setting as it stands now.
        // The model's own web lookups while choosing works, not the free search.
        ["Web lookups used", `${view.searches.used} of an allowance of ${view.searches.allowance}`],
      ]),
      // The row's absence, said out loud. `facts` drops a null pair entirely, so
      // without this the total simply is not there — and a panel showing only
      // what this run spent, with nothing to say a figure is missing, is read as
      // the whole cost of having asked.
      familySpendProblem ? el("p", { class: "note", text: familySpendProblem }) : null,
    ]),
  ];

  // A Get's works were chosen, so neither the asked-for nor the offered count
  // applies to them, and the cards are the table.
  let section = null;
  if (run.kind === "get") {
    section = el("section", { class: "get-review", "aria-label": "This Get's works" }, [
      el("h2", { text: `Works (${tally.total})` }),
      el("p", { class: "muted", text: `${counted(tally.chosen, "work")} you chose.` }),
      reviewProblem ? el("p", { class: "note", text: reviewProblem }) : null,
      ...(reviewPage ? reviewSection(reviewPage, { keptFrom }) : []),
      view.works.length ? null : el("p", { class: "muted", text: "This Get holds no works." }),
    ]);
    panels.push(section);
  } else
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `Works (${tally.total})` }),
        // The way from watching a run to judging what it brought back. Offered
        // only once the run holds works: a button onto an empty grid is a promise
        // the next screen cannot keep.
        view.works.length
          ? el("p", {}, [link({ view: "review", id: runId }, { class: "action", text: "Review these works" })])
          : null,
        reviewProblem ? el("p", { class: "note", text: reviewProblem }) : null,
        ...(view.works.length
          ? worksBySource(view.works, reviewPage)
          : [el("p", { class: "muted", text: "This Get has not settled on any works yet." })]),
      ]),
    );

  render(generation, ...panels);
  shownReview = { generation, section };
  if (focused !== document.activeElement && focused.isConnected) focused.focus({ preventScroll: true });

  // Recorded only when the paint is one worth leaving alone. A gate whose price
  // could not be read is not: the run itself is unchanged, so every later poll
  // would match the signature and the failure sentence would sit there until
  // something else about the run moved. Not recording it is what makes the next
  // poll try the price again.
  //
  // The family total's failure is deliberately NOT held out the same way, and
  // the asymmetry is the point rather than an oversight: it is fetched only for
  // a run that has stopped, and a stopped run schedules no further poll, so
  // there is no next attempt for withholding the signature to enable. The
  // sentence in the panel is the whole of that remedy.
  //
  // A destination that could not be looked up is held out for the same reason
  // as the gate's price: the run is unchanged, so the next poll would match and
  // leave the sentence saying so.
  //
  // A Get's cards that could not be read are held out for the same reason.
  if (gateEstimateProblem === null && themes !== null && reviewProblem === null) state.painted = { runId, body };

  // Poll only while there is something still to wait for. `is_terminal` comes
  // from the server rather than from a list of finished states written here,
  // which would go stale the day a tenth state is added and leave this polling
  // a finished run forever.
  scheduleRunPoll(runId, pollGeneration, { done: run.is_terminal });
}
