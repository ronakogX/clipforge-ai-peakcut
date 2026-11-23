# CLIPFORGE AI, powered by PeakCut

Native Python/FFmpeg rebuild based on the MIT-licensed original
[haziqahmedqasmi/PeakCut](https://github.com/haziqahmedqasmi/PeakCut), pinned at
`39c32a878648619e981b57af608ba4571a82247f`. The upstream license remains in LICENSE.
This is a separate build; the previous Cloudflare browser app has not been replaced.

## Run from a phone with a private Codespace

This is an on-demand development runtime, **not always-on free production hosting**.
Before creating one, check GitHub Settings → Billing and licensing → Budgets and alerts:
allow only included Codespaces usage and set any Codespaces paid-usage budget to $0 with
“Stop usage when budget limit is reached” enabled. An account without a payment method
is blocked when included usage runs out. Do not add a card or upgrade for this project.

1. Open this repository's Code → Codespaces tab and create the smallest (2-core) Codespace.
2. Wait for setup and the speech-model download. Open Ports → 8765 → Open in browser.
3. Keep port visibility **Private**. GitHub sign-in protects the studio; there is no separate app signup.
4. Upload your authorized video, choose Options, shape, layout and resolution, then Make clips.
5. Open a finished clip to download each stacked layout or adjust and re-render it.
6. Download your exports and stop the Codespace when finished. Work survives stopping;
   deleting the Codespace removes its data. Storage continues counting while stopped.

Personal GitHub Free currently includes 120 core-hours/month (about 60 clock-hours on a
2-core machine) and 15 GB-month storage. These are account-wide quotas, not this app's
allowance. Container images, models and source video all consume storage. Keep the
account's idle timeout short. Check the current
[GitHub billing documentation](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-codespaces/about-billing-for-github-codespaces).
No Codespace is created automatically by these files.

## What is implemented

- Native speech transcription and real word timestamps with the English Parakeet model.
- Whole-video analysis in blocks, rather than stopping at 300 seconds.
- Key-free highlight fallback based on loudness and transcript boundaries. Its score is
  an internal estimate; semantic AI ranking requires a separately configured model service.
- Native H.264/AAC MP4 export in 9:16 or 16:9, with animated captions.
- 360p draft, 720p and 1080p output sizes. Lower output resolution reduces encode work.
- Webcam-top and gameplay-top outputs from the exact same interval, plus gameplay-only
  fallback when no webcam is found. Both must finish before a dual-layout clip is done.
- Conservative geometric webcam detection and manual crop values in the clip editor.
  The independent gameplay crop excludes the embedded webcam using the largest remaining
  rectangle. This may remove some gameplay UI; hidden pixels cannot be recovered.
- Chunked uploads with a 2 GiB ceiling in the Codespace launcher. This is a size limit,
  not a claim that a physical 2 GB upload has been tested over mobile networks.
- Private saved jobs, retries and actual progress from PeakCut's worker pipeline.
- Resource monitoring that respects Linux cgroup v2 CPU and RAM limits.

Only process your own media or media you have permission to use. A URL is not proof of
permission. Platform links can be refused; do not bypass restrictions. Upload an authorized
export when no permitted media route is available. The first verified path is local-file
upload, not unrestricted YouTube downloading.

## Current limits

The upstream bundled speech models are English and Arabic. Hindi/Hinglish speech recognition
has not been implemented or verified in this rebuild. Roman-letter caption formatting does
not establish Hindi speech support. Webcam detection is heuristic, not a trained face model,
and needs manual correction on some streams. Uploaded sources have a touch drag-and-resize crop editor with numeric fields. Remote
sources without a retained local video use numeric correction fields. Background tabs or a sleeping free
runtime cannot guarantee uninterrupted long uploads. No claims of production readiness.

Hugging Face's current rules require a paid plan for new Docker compute Spaces, while the
free ZeroGPU exception requires verified email and an account older than 30 days. A newly
created free account is not an immediately available hosting route. See the
[current Spaces overview](https://huggingface.co/docs/hub/spaces-overview).

## Local verification

Python 3.11+, FFmpeg with libass and the packages in requirements.txt are required.
Run `python tests/run.py`. The upstream monitor measured host resources, which made its CPU saturation test fail
inside this two-core container with three visible cores. The rebuild reads Linux cgroup v2
CPU and memory limits; the real CPU saturation and queue tests now pass. See VERIFICATION.md
for the completed run and remaining unverified scenarios.

For an actual, authorized media fixture, download the English model with
`python -m studio.fetch_model`, then run:

```sh
PEAKCUT_ASR_THREADS=2 PEAKCUT_ASR_COPIES=1 python tools/verify_real_video.py /path/to/video.mp4
```

This runs real speech transcription, selection, captions and native rendering. Its two crop
orders exercise an explicitly supplied test region; they do not prove that a trailer contains
a webcam. Results and transcripts stay under ignored data/, never in GitHub.

## Security and operating cost

There are no embedded keys, paid AI calls or billable resource provisioning in the launcher.
The no-account studio must remain behind a private platform port. Do not make it public:
all visitors would share the same owner. Public multi-user deployment requires accounts,
ownership isolation, source-access review, quotas and a persistent video worker/storage host.
Cloudflare's free Workers cannot execute this native FFmpeg pipeline.
