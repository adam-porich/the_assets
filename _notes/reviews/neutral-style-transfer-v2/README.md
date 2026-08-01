# Neutral portrait style-transfer acceptance

This directory records the acceptance contract for the live neutral portrait
style. The deterministic renderer proof remains in
[`../amiga-ocs-v1`](../amiga-ocs-v1/); its stage reference is pixel-identical
to the checked-in `target-example-01.png`.

The live cohort is intentionally not run by repository automation. It requires
an operator to configure `OPENROUTER_API_KEY`, confirm the provider model and
price in Sources/Style Studio, and explicitly approve the paid cohort action.
The executable trial path, request ordering, consent gate, and review manifest
are checked in here so that run can be recorded without changing the style
contract.

To execute the pending run, start the API with the configured environment,
import or upload three varied portrait sources, open **Style Studio**, create a
draft, select an available live model, pin all three sources, and choose **Run
live cohort trial**. Review each final card and its collapsed provenance here
against [rubric.md](rubric.md), then activate only if every item passes and the
draft checksum is unchanged. Preserve the resulting batch directory and
update this manifest with its source/master/art/card paths and checksums.

Use [rubric.md](rubric.md) for independent review. A valid acceptance run must
retain source, canonical master, logical Amiga art, enlarged art, and card for
every cohort item, and must keep rejected attempts in provenance.
