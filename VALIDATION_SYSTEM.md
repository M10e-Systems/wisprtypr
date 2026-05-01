# WisprTypr Production Validation System

## Goal

Create an opt-in production validation loop that captures:

1. recorded audio for utterances
2. user corrections to the text generated from that audio

The system should upload structured validation records to a server. A downstream agent should consume those records and generate actionable tickets for:

- tuning default parameters
- improving normalization or injection logic
- improving speech recognition behavior
- identifying source code changes worth implementing

This design is intentionally grounded in the current WisprTypr architecture:

- audio capture flows through `AudioCapture` and `UtteranceDetector`
- transcript commits happen in `DictationController`
- text insertion happens in `TextInjector`
- tray/menu UX is the main current configuration surface

## Design Principles

- Strict opt-in. No audio or correction capture unless the user explicitly enables validation mode.
- Production-safe. Validation must not block dictation, text injection, or tray responsiveness.
- Bounded collection. Capture only utterance-scoped evidence needed for debugging model and product quality.
- Correlatable. Every uploaded artifact must tie together audio, raw transcript, normalized transcript, injected text, and any later correction event.
- Auditable. The client and server should preserve enough metadata to explain why a ticket was created.
- Privacy-first. The user should see clear consent text, retention policy, and a one-click way to disable and purge local pending data.

## User Experience

### Consent Surface

Add a new tray menu section:

- `Validation Mode`
- `Off`
- `On: audio + correction capture`
- `Upload pending now`
- `Delete pending validation data`

The first time the user enables validation mode, show a confirmation dialog with plain-language consent text:

- audio clips from dictated utterances will be saved
- the transcript and later edits near the insertion point may be captured
- data will be uploaded to the validation server
- the feature is optional and can be disabled any time

Persist the consent choice locally.

### Scope Rules

When validation mode is enabled:

- capture only utterances that were actually transcribed and injected
- do not continuously stream microphone audio
- keep capture bounded to the utterance plus small context metadata
- do not upload inline during the hot path unless a background queue accepts it immediately

When validation mode is disabled:

- do not save audio
- do not observe corrections
- do not upload validation records

## What Counts As A Correction

A correction is any user edit that appears to revise recently injected dictation text.

Because WisprTypr injects text into arbitrary X11 applications, exact document-state tracking is hard. The correction detector should therefore use a pragmatic, evidence-based heuristic:

1. For each injected commit, create a `validation_session` with:
   - utterance id
   - final transcript
   - injected text
   - injection timestamp
   - target window metadata if available
2. For a short configurable window after injection, observe user input events relevant to edits:
   - backspace/delete bursts
   - typed replacement text
   - paste events
3. Group nearby edit activity into a `correction_candidate`.
4. At session close, compute:
   - original injected text
   - estimated corrected text
   - edit distance
   - replacement spans
   - confidence that this was a true correction rather than unrelated typing

Only upload corrections above a confidence threshold, but keep the raw local event summary long enough to support debugging.

## Proposed Client Architecture

Add four new components.

### 1. `ValidationSettings`

Responsibility:

- persist opt-in state
- persist server endpoint and auth token if needed
- persist retention and queue settings

Suggested local path:

- `~/.config/wisprtypr/settings.json`

Fields:

```json
{
  "validation_enabled": false,
  "validation_server_url": "https://validation.example.com",
  "validation_upload_token": "env-or-local-secret",
  "validation_retention_days": 7,
  "validation_capture_edit_window_seconds": 20,
  "validation_max_pending_mb": 256
}
```

### 2. `ValidationRecorder`

Responsibility:

- receive finalized utterance audio and transcript metadata
- serialize audio to a durable local spool
- create a validation record before upload

Integration point:

- called from `DictationController._handle_transcribed_text(...)` when `update.is_final` is true and text was actually injected

Payload contents:

- utterance id
- raw final audio as mono 16 kHz WAV or FLAC
- chunk duration setting
- utterance detector settings
- whisper config
- raw transcript
- normalized transcript
- injected text
- timestamps
- app version / git revision if available

### 3. `CorrectionObserver`

Responsibility:

- monitor likely correction behavior after an injection
- produce a correction summary tied to the utterance id

Integration points:

- `TextInjector.inject_text(...)` notifies the observer when text is inserted
- low-level X11 event hook watches key activity for a short post-injection window

The observer should maintain a rolling session state:

- active utterance id
- injected text
- injection location/window fingerprint if detectable
- start timestamp
- sequence of edit-related events

At session end it emits:

- corrected text estimate
- confidence
- event summary
- latency to first correction
- edit distance metrics

### 4. `ValidationUploader`

Responsibility:

- background upload of queued records
- retries with exponential backoff
- mark local records uploaded only after server acknowledgement

Suggested spool layout:

- `~/.local/state/wisprtypr/validation/pending/*.json`
- `~/.local/state/wisprtypr/validation/audio/*.flac`
- `~/.local/state/wisprtypr/validation/uploaded/*.json`

The uploader must:

- never block dictation
- respect max queue size
- evict oldest pending records when storage cap is exceeded
- scrub orphaned audio files

## Record Model

Use an append-only utterance-centered schema.

### `utterance_record`

```json
{
  "utterance_id": "01JXYZ...",
  "user_id": "stable-client-id",
  "device_id": "stable-device-id",
  "created_at": "2026-03-31T18:42:15.231Z",
  "app": {
    "version": "0.1.0",
    "platform": "ubuntu-x11",
    "chunk_duration_seconds": 4
  },
  "audio": {
    "codec": "flac",
    "sample_rate_hz": 16000,
    "channels": 1,
    "duration_ms": 2740,
    "sha256": "..."
  },
  "stt": {
    "model_name": "small.en",
    "compute_type": "auto",
    "language": "en",
    "context_seconds": 12,
    "raw_transcript": "hello world again",
    "normalized_transcript": "hello world again",
    "injected_text": "hello world again"
  },
  "correction": {
    "observed": true,
    "confidence": 0.93,
    "corrected_text": "hello world, again",
    "latency_ms": 2200,
    "levenshtein_distance": 1,
    "kind": "punctuation_fix"
  },
  "window": {
    "app_name": "firefox",
    "title_hash": "..."
  }
}
```

### Event Detail Tables

The server should also keep normalized child tables for:

- `utterance_uploads`
- `correction_events`
- `parameter_snapshot`
- `agent_ticket_runs`

This makes downstream aggregation much easier than mining one monolithic blob.

## How To Infer Corrections Reliably

The hardest part is reconstructing what the user changed in arbitrary applications. The system should combine three levels of evidence.

### Level 1. Injection-Aware Edit Heuristic

Immediately after WisprTypr injects text, open a correction watch window for that utterance.

Signals that increase confidence:

- backspace/delete activity starts within 0 to 5 seconds
- replacement typing begins immediately after deletion
- replacement length roughly matches deleted span
- edit burst ends quickly

Signals that decrease confidence:

- long pause before typing
- cursor navigation without deletion
- lots of unrelated typing beyond the injected span
- app/window switch before edit sequence

This level is cheap and likely enough to catch many obvious fixes.

### Level 2. Clipboard/Paste Echo Evidence

When the user pastes soon after deleting dictated text, record that a paste happened and its length if observable. Do not attempt broad clipboard surveillance outside the active correction session.

This helps classify corrections such as:

- replacing a mistaken phrase with a manually copied phrase
- changing capitalization or punctuation via external tooling

### Level 3. Optional Explicit Mark

Add an optional tray action:

- `Mark last utterance as wrong`

That lets the user deliberately flag a bad transcript even when passive correction inference is weak. This record should still upload the audio and transcript, but mark `correction.observed = false` and `user_flagged_bad = true`.

This is especially useful for:

- users who move the caret elsewhere before fixing text
- applications where edit observation is noisy
- errors noticed later rather than immediately

## Server API

Use a simple authenticated HTTPS ingestion API.

### `POST /v1/validation/utterances`

Multipart or two-step upload:

- metadata JSON
- audio blob

Response:

```json
{
  "accepted": true,
  "utterance_id": "01JXYZ...",
  "deduplicated": false
}
```

### `POST /v1/validation/corrections`

Allows late-arriving correction summaries if the audio/transcript was uploaded first.

### `POST /v1/validation/client-heartbeat`

Optional. Tracks client version, queue depth, and upload health without sending user content.

## Server-Side Storage

Store:

- immutable utterance metadata rows
- immutable audio object blobs
- immutable correction rows
- derived aggregates for analytics

Recommended layout:

- relational DB for metadata and derived metrics
- object storage for audio

Retention:

- raw audio retention shorter than metadata retention
- configurable per environment
- server-side deletion endpoint keyed by `user_id` for privacy requests

## Derived Analytics

Compute nightly or streaming aggregates:

- correction rate by chunk duration
- correction rate by utterance duration
- correction rate by normalized text length
- correction latency distribution
- frequent substitutions
- punctuation-only correction rate
- capitalization-only correction rate
- window/app-specific failure patterns
- error clusters by model/config version

This is the bridge from raw evidence to engineering work.

## Agent Workflow For Ticket Generation

The downstream agent should not create tickets directly from individual bad samples. It should work in stages.

### Stage 1. Aggregate And Cluster

For a rolling time window:

- group by failure type
- compute frequency
- compute user impact
- sample representative utterances

Example clusters:

- sentence-final punctuation frequently missing
- short proper nouns often lowercased
- chunk size `1s` causes more split-word regressions
- repeated deletions suggest over-eager stable-prefix commits
- specific apps show paste/injection anomalies

### Stage 2. Map Clusters To Likely Levers

For each cluster, suggest likely remediation categories:

- tunable parameter adjustment
- normalization rule improvement
- utterance detector threshold change
- STT decode parameter change
- source code bug fix
- instrumentation gap

Examples:

- frequent premature partial commitments -> revisit stable-prefix logic in `DictationController`
- many punctuation fixes -> extend `normalize_transcript(...)` or add punctuation post-processing
- high correction rate on low-energy speech -> revisit audio normalization target RMS or utterance energy threshold

### Stage 3. Create Tickets With Evidence

Each ticket should include:

- concise problem statement
- estimated impact
- representative examples
- candidate root cause
- proposed fix type
- validation query to measure improvement after release

Example ticket titles:

- `Tune utterance silence threshold to reduce clipped phrase endings`
- `Improve transcript normalization for missing comma insertion around discourse markers`
- `Investigate over-commit behavior in stable-prefix merge logic for 1s chunks`

## Suggested Ticket Thresholds

Only auto-generate tickets when thresholds are met, for example:

- at least 25 high-confidence correction cases in 7 days
- affects at least 5 users or 3 devices
- correction rate materially above baseline
- cluster confidence above configured threshold

Otherwise, keep the cluster in an analyst queue or weekly report.

## Concrete Integration Plan For This Repo

### Phase 1. Client Plumbing

Add:

- `src/wisprtypr/settings.py`
- `src/wisprtypr/validation.py`
- `src/wisprtypr/upload.py`

Update:

- `src/wisprtypr/tray.py` to expose validation controls
- `src/wisprtypr/app.py` to wire settings, recorder, uploader
- `src/wisprtypr/controller.py` to emit finalized utterance records
- `src/wisprtypr/injection.py` to notify correction sessions

### Phase 2. Correction Detection

Add:

- X11 event observer for bounded post-injection edit capture
- correction session model and confidence scoring

### Phase 3. Server + Agent

Build:

- ingestion API
- object storage pathing
- aggregate jobs
- agent prompt + ticket creation workflow

## Important Edge Cases

- User disables validation while uploads are pending.
  - Stop new capture immediately and offer delete-or-finish-upload choice for pending data.
- Audio captured but no text injected.
  - Do not upload as a normal validation case unless explicitly flagged as a failed utterance.
- User edits text much later.
  - Do not infer a correction unless explicit mark mode is used.
- Injection fallback types text instead of paste.
  - Still open a correction session; source mechanism should be recorded.
- App crashes before upload.
  - Local spool must be crash-safe and resume on next start.

## Privacy And Compliance Notes

- Consent text should be explicit that speech audio may include sensitive content.
- Keep window titles hashed, not plaintext.
- Avoid collecting full surrounding document context in v1.
- Prefer FLAC over WAV for lower upload/storage cost without losing fidelity.
- Support local deletion of pending records and server-side deletion by stable user id.

## Success Metrics

The validation system is working if it can answer:

- Which user-visible transcript failures happen most often in production?
- Which failures are fixed by parameter tuning versus code changes?
- Did a release reduce correction rate for the targeted cluster?
- Which chunk duration and detector defaults minimize corrections?

## Recommended Initial Defaults

- validation disabled by default
- capture only finalized utterances that were injected
- 20 second correction observation window
- FLAC storage
- background upload every 30 seconds with exponential backoff
- 7 day local retention cap
- ticket generation on weekly batches plus urgent alerts for severe spikes

## Minimum Viable Version

If we want the smallest rigorous first version, ship:

- explicit opt-in
- finalized utterance audio capture
- transcript + normalized transcript + injected text upload
- explicit `Mark last utterance as wrong`
- no passive correction inference yet

That version is already enough for an agent to create useful tickets. Passive correction inference can follow once the ingestion and privacy model are proven out.
