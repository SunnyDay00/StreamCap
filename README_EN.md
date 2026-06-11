<div align="center">
  <img src="./assets/images/logo.svg" alt="StreamCap" />
</div>

<div align="center">
  English / <a href="./README.md">Chinese</a>
</div>

# StreamCap Fork Enhancements

This repository is a fork of [ihmily/StreamCap](https://github.com/ihmily/StreamCap).

This README only documents the features added or changed in this fork. For the original project capabilities, installation, runtime setup, supported platforms, configuration, and full usage guide, see the upstream documentation:

- [Upstream README](https://github.com/ihmily/StreamCap)
- [Upstream Wiki](https://github.com/ihmily/StreamCap/wiki)

## Added And Changed Features

### 1. Recording-To-Text Transcription

- Added transcription features to the **Storage** page.
- Supports per-file `Identify Text`, `Re-identify`, `View Text`, and `Export Text`.
- Supports `Identify All`, `Identify Remaining`, and `Batch Export`.
- Supports common media formats including `mp3`, `wav`, `m4a`, `mp4`, `mov`, `mkv`, `flv`, `wma`, `aac`, `flac`, `avi`, `ts`, and `webm`.
- Supports automatic transcription after recording completes. Segmented recordings are processed file by file after integrity checks pass.
- Transcription results are saved as sibling `.txt` files. Filenames include local/cloud source, model, and AI optimization state.
- Re-identification cleans up older results of the same type to reduce duplicate or conflicting text files.

### 2. Local Speech Recognition

- Added **Settings -> Identify Text -> Local Speech Recognition Models**.
- Supports checking, downloading, and updating local recognition models.
- Local ASR supports `Paraformer` and `Fun-ASR-Nano-2512`.
- Integrates VAD and punctuation restoration models for more readable transcriptions.
- Added optional `MossFormer2` vocal enhancement to reduce background music/noise before recognition.
- Supports inference device selection: Auto, CUDA, or CPU.
- Supports local batch recognition concurrency from 1 to 4.
- Added CPU protection logic that reserves system/UI resources based on CPU core count and concurrency settings.

### 3. Cloud Speech Recognition

- Added Alibaba Cloud DashScope speech recognition settings.
- Supports `Paraformer-v2` and `Paraformer-8k-v2`.
- Cloud recognition uses asynchronous tasks and is suitable for larger recording files.
- Long audio is split according to model limits, then merged after transcription.
- Batch transcription can process multiple files asynchronously.

### 4. AI Text Optimization

- Added AI text optimization through an OpenAI-compatible API.
- Defaults to an Alibaba Cloud Bailian-compatible endpoint, with custom `API Base URL`, model name, and system prompt.
- Cleans ASR drafts lightly by fixing obvious typos, repeated words, filler words, and basic punctuation issues.
- The default prompt is designed to preserve the original spoken style instead of rewriting speech into formal prose.
- The result dialog shows the transcription source and whether the text was AI optimized.

### 5. Dependency Management And Bundled Runtime

- Added **Settings -> Dependencies**.
- Checks FFmpeg, Node.js, and Python runtime library status, path, and version.
- Supports one-click install or reinstall for FFmpeg, Node.js, and Python runtime libraries.
- Prioritizes bundled `libs`, `ffmpeg`, and `node` resources on startup to reduce dependency on the system environment.
- Added automatic detection and repair for Python runtime libraries.

### 6. Recording Behavior Changes

- Existing rooms no longer start monitoring automatically when the app launches.
- Each recording card now has a manual live-status check button.
- Improved shutdown protection: the app waits for active recording, transcoding, or transcription tasks before exiting.
- Desktop mode supports minimizing to tray while keeping a force-close path.
- Improved automatic transcription after segmented recording.
- Fixed and improved Douyu recording compatibility.

### 7. Storage Page Improvements

- Added manual refresh to the Storage page.
- Added file duration detection and batch duration detection.
- Added duration badges in the file list.
- Supports writing detected duration into filenames for easier organization.
- Improved batch operations and media duration statistics.

## Feature Entry Points

- **Settings -> Identify Text**: Configure local recognition, cloud recognition, auto transcription after recording, and AI text optimization.
- **Settings -> Dependencies**: Check, install, or reinstall FFmpeg, Node.js, and Python runtime libraries.
- **Storage**: Transcribe, view text, export text, batch transcribe, batch export, and detect file durations.
- **Recording cards**: Manually check live status, start/stop monitoring, and inspect recording state.

## Upstream Documentation

This repository does not duplicate the upstream project's installation, implementation, deployment, or basic usage documentation. See:

- [Upstream README](https://github.com/ihmily/StreamCap)
- [Upstream Wiki](https://github.com/ihmily/StreamCap/wiki)

## License

This fork follows the upstream project license. See [LICENSE](./LICENSE) for details.
