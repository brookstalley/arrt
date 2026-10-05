# Learnings — core

**Apply a rule below where it bears on the decision in front of you, and cite it where it changed what you did.**

Each rule is one line of at most 250 characters. This file is capped, so a new rule is paid for by merging or retiring one.

- When a norm is ratified, re-read every artifact it governs against it, not just the code — because a spec that violates a norm is an instruction a builder will faithfully follow.
- When a test, lint or check is new or rewritten, watch it fail once against the unfixed code or a re-break — because 'not run', 'unreachable state' and 'passed' print the same green, and two agreeing runs can share one fault.
- When you delete a constant or add a required parameter, grep `tools/` and `scripts/` for consumers — because linter, type checker and suite are all silent about a file nothing imports.
- When a review returns 0 blocking with cheap observations, accept them or carry them into the next commit already happening — because each fix commit buys another review round.
- When a mutation's verdict flips between identical runs, apply it by hand and search for the rare input, then pin it with an example test — because a property finding the case by luck defends nothing.
- When a mutation survives, find why: unreachable (build the case first), inert or rescued by a sibling guard (delete, or one case per guard), or undefended (test it) — because all look alike from outside.
- When you drop or rewrite a test's assertion, replace a badly-shaped guard in the same commit, re-read the test's name against it and record why — because a dropped contract looks like adjusted wording.
- Before asking the owner to rule, grep the code and the records for that shape and put the built behaviour and any earlier ruling in the question — because code or the owner may have settled it already.
- When you write or cite 'exactly one', 'always' or 'never', state what the store or guard actually enforces — because a partial index enforcing 'at most one' gets read as 'exactly one'.
- When building an inventory of routes, operations or requirements, derive it from the thing itself and use debt lists only as a check — because a debt list answers the smaller 'what do we owe?'.
- When you fix a defect, make inputs the fix does not know fail by name, and grep the commit for the same shape — because the fix removes today's instance and leaves the silent mechanism and its siblings.
- When a boundary library reports success or failure, confirm it against the remote system's own state, keeping 'unconfirmable' apart from 'failed' — because clients misreport in both directions.
- When you clamp, filter or redact one named line in a dependency, open the dependency and read that line before choosing the threshold — because a guard built on memory protects nothing.
- When you retire, amend, descope or close anything, first grep the whole repo (no --include) for its nouns and OLD wording, justifying prose and 'there is no X' included — because survivors paraphrase.
- When a file documents its format with a filled example, write only the keys your entry needs, never paste the example — because its placeholders are illustrative and read in place of the rules.
- When you record something as verified, name what was measured (fields, cases, N) and keep the check in the suite if a change could void it — because the claim otherwise outlives its evidence.
- When a behaviour matters because something calls or reads it, test through that caller with a non-default value and mutate the lines you changed — because callee tests and default values stay green unwired.
- After a scripted mass edit, verify with a method keyed on something the edit did not key on, such as a roster or resolution check — because a check sharing the edit's pattern shares its blind spots.
- When an artifact works a rule on two cases, derive the rule from one and check the other.
- When testing idempotence, vary the inputs between runs, not just the repetition — because a test that holds the inputs still tests the wrong half.
- When a backlog body, 'cannot work here' note or comment describes current state, re-check the tree or machine before acting — because records freeze on the day written while the world moves.
- When code is added, moved or retired, ask which guards were scoped to the old shape or to where you looked, and carry them to the surviving code — because the guard stops at its scope and the failure does not.
- When prose explains a distinction, check a mechanism records it — because prose explaining a distinction is not a mechanism recording it.
- When you write a negative claim, run the search that would have falsified it.
- When you argue a derived artifact is device-independent, name a second, different device it would be wrong for — because with one device in the room every device-specific choice passes as content.
- When a dependency advertises a floor, 'no infrastructure' or a pluggable tier, check what it imports and find the code providing the capability — because declared and advertised are claims.
- Before answering the question a spec asks about a candidate, check that the candidate is one.
- When an index under-claims its enforcement, fix it — because an under-claiming index is defective, not conservatively safe.
- When a mutation sweep reports, confirm each mutation changed behaviour, matched once, and the run collected tests (exit 0 or 1) — because a no-op, ambiguous or empty run reads as a finding or a catch.
- When a finding or reviewer lists sites or items, treat the list as a checklist to tick off in the file and a sample to grep beyond — because partial consumption is how fixes ship incomplete.
- When a clause or notice is conditional, assert its absence in the case where it must not appear — because present-only assertions pass under every over-firing bug.
- When writing a fixture, add the member that would make the claim false, not just enough to reach the line — because a fixture that cannot falsify its assertion proves nothing.
- When a verify pass is silent on a finding you expected it to settle, check whether the fix sits in the reviewed interval's base and name the finding explicitly — because passes verify intervals.
- When a commit message states what it changed, count the hunks before repeating it — because a message is evidence about intent, never about content.
- When a change makes a previously impossible operation possible, treat every artifact claim about it as unverified and write the test its sentence describes — because a rule never violable was never implemented.
- When a store read or `caplog` promises no order, key assertions on identity, not position — because the test passes alone and fails in the suite.
- At the moment of a fix, ask what the change now covers that it did not before — because a wrapper for a read also catches the write beside it.
- When a claim already lives in prose, verify it against the code and add a pointer, never a copy — because copies are one piece of evidence that drift apart, and a sweep finds only the homes you recall.
- When a fixture seeds a file at a path the code derives, learn the path from an observed run — because a rename leaves the fixture pointing at nothing while the test stays green.
- When a comment justifies code by a constraint, or names what a guard excludes, check the constraint and what else the guard breaks — because a plausible reason covers only the cases its author imagined.
- When a chunk is parked behind access it lacks, check which dependencies actually need that access — because dependencies inherit parking by adjacency, and the one gating the work is cheapest early.
- When ruling out an enum value, search for every path that arrives at it, not the likeliest write site — because reachability belongs to the routes in.
- When a safety check guards a filtered feature, range it over the population the hazard lives in — because the filter that makes the feature correct can hide the colliding case.
- When derived output (index, checkbox, table) looks wrong, find and run its generator, then check the source tag against prior instances — because hand-fixing it hides the upstream fault.
- When a comment names a failure as unacceptable or a drift it prevents, write the test from that comment, not the diff, and re-read it when adding a caller — because stating a danger reads as defending against it.
- When a bug report, decision or record states a cause or premise, run the cheapest experiment that could refute it before building on it, labelling inference apart from measurement — because reasoning gets recorded as observed.
- When a comment names a symbol as the source of truth for a set, parametrise the test over that symbol — because a hand-copied list misses the member added later.
- Before bumping a dependency, exercise its call sites in a clean interpreter and read sibling lockfiles — because the suite may not install that manifest, and the next plane may already run the version.
- When a check can be quiet for more than one reason, give each quiet state its own output and match the form the tooling parses — because a quiet 'cannot tell' is read as a pass.
