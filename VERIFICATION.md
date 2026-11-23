# Verification — 2026-11-23

Base: PeakCut `39c32a878648619e981b57af608ba4571a82247f`, MIT licensed.
Python 3.12, native FFmpeg, sherpa-onnx 2.0.1, English Parakeet TDT 0.6b int8.
Staging environment: two-core CPU quota, 8 GiB RAM limit, three visible CPU cores.

## Automated checks

`python tests/run.py`: **All tests passed** on the final run. This includes ownership and
permission checks, abuse and input limits, chunked uploads, long-video block processing,
queue saturation, restart/retry handling, caption timing, webcam detection, no-account
operation and the new CLIPFORGE regression suite.

The original baseline failed two checks: uniform compressed noise was incorrectly detected
as a webcam, and host-wide CPU measurements missed the container's actual saturation.
The rebuild requires relative stillness for geometric webcam candidates and measures cgroup
v2 CPU/RAM limits. Both failures pass after the fixes; neither check was removed.

The CLIPFORGE suite has seven tests covering finite/in-bounds crop validation, allowed shapes
and ratios, cgroup quota calculations, identical timestamps for both outputs, failure of the
second render remaining a failure, owner-only source previews, deleting variant files,
webcam-free fallback, undistorted 4:3 → 16:9 fitting, and refusing unsupported YouTube media
access and browser-cookie imports. Upstream cookie-import expectations were intentionally
replaced with assertions that imports are rejected.

`node --check` passes on the extracted web script. Both launcher scripts pass `bash -n`.
No Docker image or hosted Codespace was built in this environment.

## Real media

Authorized fixture: Blender's [Sintel trailer](https://durian.blender.org/download/),
CC BY 3.0, 52.208 seconds, 854×480 with source audio. Actual transcribed speech includes:

> What brings you to the land of the gatekeepers? I'm searching for someone.

The native pipeline extracted audio, ran the downloaded speech model, found timestamped
words, selected an 8.31-second highlight (36.55–44.86 seconds), burned captions and generated
real H.264/AAC MP4 files. No AI API key was configured: the candidate was explicitly labelled
as selected by loudness. Total first verification, including transcription and five renders,
was 62.2 seconds in this staging runtime.

Both 9:16 (360×640) and 16:9 (640×360) were rendered in each stacked order. The trailer has no
streamer webcam: the dual-layout render tests used a deliberately supplied test rectangle,
not a claim of automatic webcam detection. Synthetic webcam tests cover top-left,
bottom-right and an edge location, plus the no-webcam case.

The actual web upload endpoint accepted the fixture. Its background job completed with a
real landscape clip. A 390×844 mobile Chromium viewport then opened its editor, moved the
crop box, switched to portrait, and requested both stacked outputs. Both MP4 download
responses returned actual bytes with attachment headers. There were no page JavaScript
errors or horizontal viewport overflow.

Both decoded audio waveforms correlated 0.9761 with the same source interval at zero offset
after loudness normalization and AAC encoding. Both streams start at timestamp 0; both
layouts have identical audio. Output video duration was 8.3 seconds and AAC duration 8.4
seconds, including its small encoding tail.

Native export-only benchmark, same 8.31-second interval and captions, two layouts generated
sequentially with two encoder threads:

| Output | Both layouts |
| --- | ---: |
| 360×640 | 5.76 seconds |
| 720×1280 | 11.45 seconds |

This excludes upload, model download, transcription and highlight analysis. Free hosts can
be slower or suspend; it is not a latency guarantee.

## Remaining acceptance work

- Physical iPhone Safari and Android testing, including long uploads and downloads.
- A real 2 GB upload and an entire long gaming VOD through the hosted runtime.
- Real streamer webcams in diverse lighting, moving layouts and game-face distractors.
- Hindi/Hinglish speech recognition and manual word-level transcript correction in the UI.
- Semantic/multimodal highlight ranking without a paid API, 60 FPS export and richer safe-area controls.
- A permitted creator-authorized YouTube media adapter. Metadata alone is insufficient.
- Persistent hosting/storage, cleanup automation, public multi-user security review and production deployment.

## Deployment status and cost

The native rebuild is not deployed. GitHub's connected token rejected `CreateRepository`,
and its billing API is not accessible through that integration. The browser requires sign-in.
An empty private `ronakogX/clipforge-ai-peakcut` repository and permission to push are needed
before publishing. Codespaces paid usage must be blocked at $0 or payment details absent
before starting a runtime; included allowance has not been verified for this account.

No Codespace, paid plan or billable resource was created. Existing Cloudflare and Supabase
resources were left unchanged. The previous browser app remains available at
https://clipforge-ai.pandyaaarav214.workers.dev and is separate from this native build.
