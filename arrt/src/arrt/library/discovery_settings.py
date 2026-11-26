"""What discovery is allowed to do and what a provider charges: the allowances and prices as one value.

**This module imports no other `arrt` module**: configuration builds the value
and the discovery runner reads it, and neither may have to load the other to
share it. The runner still names it (`arrt.library.services.runner`), as this
same class.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DiscoverySettings:
    """What discovery is allowed to do, and what a provider charges for doing it.

    **Costs are `Decimal`, never `float`.** A tenth of a cent that cannot be
    represented exactly is a rounding error in the figure a curator is asked to
    authorise against, and then in a total nobody will reconcile against the
    provider's own.

    The two allowances are one cap in two parts, and the split is forced by what
    is knowable when: phase 1 has no work count to derive an allowance from,
    because producing the work count is what phase 1 is *for*. The estimate
    decomposes the same way, which is what lets a caller be told what asking will
    cost before anything has run.
    """

    phase1_search_allowance: int
    phase2_searches_per_work: int
    #: How many works a run may offer from a wired collection on top of what it
    #: proposed. Not a cost bound — browsing a museum API is free — but a bound on
    #: a curator's attention and on how far a supplement may outweigh the list
    #: they asked for. Zero switches the supplement off without unwiring it.
    offered_works_per_run: int
    search_cost_usd: Decimal
    input_cost_usd_per_mtok: Decimal
    output_cost_usd_per_mtok: Decimal
    #: What one phase-1 run may consume, as bounds rather than typical figures.
    #: The two are arrived at differently: input is a measurement with headroom,
    #: output is the provider's own reservation, which a run physically cannot
    #: exceed. So they are close in size even though real consumption is
    #: input-heavy — and a model with cheap input and expensive output is priced
    #: accordingly rather than getting the pass an input-dominated basis gave it.
    phase1_input_tokens: int
    phase1_output_tokens: int

    @property
    def phase1_estimate_usd(self) -> Decimal:
        """What asking a question costs, at the allowance's ceiling.

        **Bounded rather than typical.** A figure a run may freely exceed is not
        an estimate, and this is the number a curator or an agent decides on
        before anything has been spent — so it prices the whole search allowance
        whether or not a given run uses it.
        """
        return self._model_call_usd + self.phase1_search_allowance * self.search_cost_usd

    def phase2_estimate_usd(self, work_count: int) -> Decimal:  # noqa: ARG002 -- free at any count; callers say how many
        """What resolving a known work list costs. Nothing, on museum APIs.

        **Zero is measured, not assumed** (2026-08-02). Phase 2 asks museum APIs,
        which are open and unmetered, and establishes whether a result is the
        requested work by comparing titles and artists locally — so it makes no
        model call and no paid web search. Bandwidth is the only cost and nobody
        bills for it.

        This figure does not price `phase2_searches_per_work` as paid web searches,
        because the providers are free. That allowance still bounds a run's fan-out and is
        still reported beside a run's usage, but nothing it bounds is billed
        today, and pricing it would show a curator a charge that will not appear.
        **A paid provider added later reinstates the arithmetic here**, which is
        the one place it has to change.
        """
        return Decimal(0)

    @property
    def _model_call_usd(self) -> Decimal:
        return (
            self.phase1_input_tokens * self.input_cost_usd_per_mtok + self.phase1_output_tokens * self.output_cost_usd_per_mtok
        ) / 1_000_000
