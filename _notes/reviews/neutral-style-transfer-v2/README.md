# Neutral portrait style-transfer acceptance

This directory records the acceptance contract for the live neutral portrait
style. The deterministic renderer proof remains in
[`../amiga-ocs-v1`](../amiga-ocs-v1/); its stage reference is pixel-identical
to the checked-in `target-example-01.png`.

The live cohort is intentionally not run by repository automation. It required
an operator to configure `OPENROUTER_API_KEY`, confirm the provider model and
price in Sources/Style Studio, and explicitly approve the paid cohort action.
That authorized run is recorded in `manifest.json`; the active immutable style
is now `style_amiga_ocs_portrait_v5_8cc6de7e54`.

The accepted run used three varied local benchmark sources, the locked
`openai/gpt-image-1-mini` live model, and five paid calls in the final batch
including two explicit “Try another” attempts. The accepted cohort itself used
three calls and cost `$0.0320865`; superseded trials remain in the ignored
workspace for provenance and are summarized in the manifest. Each final card
and its collapsed provenance was reviewed against [rubric.md](rubric.md).

Use [rubric.md](rubric.md) for independent review. A valid acceptance run must
retain source, canonical master, logical Amiga art, enlarged art, and card for
every cohort item, and must keep rejected attempts in provenance.
