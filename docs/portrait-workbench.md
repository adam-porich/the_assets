# Input, pipeline, candidate, and collection workbench contract

The supported surfaces are `Inputs`, `Pipeline`, `Candidates`, and `Collection`.
An original image is not available downstream until its normalization preview
has been explicitly accepted as an Input.

## Input ingest

Uploads and Pexels results begin as temporary pending records. The preparation
dialog shows the original beside a generative preparation preview and exposes
its cleanup prompt and quality. Generated previews record consent, model,
usage, cost, prompt, seed, checksums, and timing and never apply a style
reference. `OK` promotes the completed preview without another provider call.
Cancelling a new record deletes its staging files; reopening an accepted Input
allows a replacement preview while preserving the currently accepted revision.

Accepted records live below `inputs/<input-id>/`. The workspace exposes only
accepted Inputs to later surfaces. Candidate and trial batches snapshot the
accepted normalized bytes and checksum, so replacing an Input never changes an
existing result.

## Style pipeline and production

Schema-v3 pipelines contain one style prompt, shared model settings, ordered
`generation-reference` assets, composition, the deterministic Amiga renderer,
and card assembly. Normalization is not a pipeline stage. A target example is a
review-only renderer proof and is structurally excluded from model requests.

Candidate generation uses the same preview/tweak/accept pattern as Input
preparation. The selected pipeline prompt remains locked while an optional,
separately recorded content direction describes the requested semantic change.
The dialog permits reruns without conflating content direction with style.
Ready previews remain outside candidate packs until explicitly accepted.

Each preview or trial sends the accepted Input first and style references after
it, making exactly one provider call. Generation is constrained to an isolated
foreground on a dynamically chosen green or magenta key. The raw output and
extracted alpha foreground are retained. A named renderer preset then supplies
the background and composites the foreground directly at the art ratio. The
foreground and background are reduced independently before compositing at
168×138 logical pixels: the subject keeps a 32-colour OCS palette while the
background receives its own derived 16-colour OCS palette. Card chrome remains
on stable house colours, and the assembled 210×300 logical card is enlarged
exactly 2× without a final whole-card palette pass. The default adaptive
foreground mode retains ten house-colour anchors and derives the other 22
colours from opaque subject pixels. Fixed foreground mode uses the original
house 32 for comparison. Retries and `Generate another` append immutable
attempts; background or palette changes only rerender the saved foreground and
make no provider call.

Default placement fits the extracted foreground inside a safe region. Changing
the background preset is a no-generation preview or rerender.

The Pipeline editor exposes the single style prompt, generation model, quality,
references, renderer settings, and a selectable comparison cohort of up to
three accepted Inputs. Locked revisions and their checksums remain immutable.

## Storage and safety

Only one image-generation operation may run at a time across input preparation,
production, and trials. Every live action requires explicit consent at its API
boundary. Runtime data is stored in ignored `portrait-library/`; pipeline
definitions and style references survive catalog resets. The 2026-08-05 reset
was moved to `_archive/catalog-reset-20260805-2340` inside that workspace for
local recovery.

Favorites reference durable candidate attempts and follow their latest render
revision. Removing a favorite does not remove its production assets.
