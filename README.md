**English** · [Français](README.fr.md)

# Scribouille

Turn recordings into text on your own machine. No account, no cloud, no upload.

[![Release](https://img.shields.io/github/v/release/BurN-30/scribouille?label=release)](https://github.com/BurN-30/scribouille/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows%2064--bit-lightgrey)

Scribouille is a desktop app for Windows built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Drop audio files on the window, get text files next to them. It was written for meeting recordings: room audio, several voices, proper nouns and in-house jargon. The interface is available in English and French.

<!-- screenshot 1: main window, dark theme, drop area empty, hardware card visible -->

---

## Install

1. Download **`Scribouille-Setup-X.Y.Z.exe`** from the [Releases](https://github.com/BurN-30/scribouille/releases) page.
2. Run it.
3. Start **Scribouille** from the Start menu.

Nothing else to install. The setup is per user, **no administrator rights**, and it installs into `%LOCALAPPDATA%\Programs\Scribouille`. Your settings, glossary and logs live in `%LOCALAPPDATA%\WhiScribe`, never inside the program folder, so reinstalling a newer version over the old one loses nothing.

> **The application was called WhiScribe up to 2.3.3.** The repository name has changed, the old addresses redirect. On a machine that already has it, the update installs over the existing setup, in its original folder `%LOCALAPPDATA%\Programs\WhiScribe`, and the data folder keeps its name too: nothing to move, nothing lost.

The setup asks **where to keep the transcription models**, 1.6 to 3.1 GB depending on the preset. The models are not bundled: they are downloaded once, on first use, and the app tells you the size before starting. After that it works offline.

The installer is not signed, so SmartScreen may warn on first run: "More info", then "Run anyway". See [Known limits](#known-limits).

> **Speaker separation** does not ship inside the setup, on purpose: it needs PyTorch, about 3.6 GB once installed. It is added **from a button inside the application**, in the "Speakers" panel, which downloads and installs the components, announces the size and lets you cancel. Nothing else to do.

---

## What it does

- **Drop and go.** Drag files or a folder onto the window, pick a preset, start. Files are processed one after another, a failure does not stop the queue.
- **Formats in:** `m4a` (including phone recordings), `mp3`, `wav`, `ogg`, `flac`, `opus`, `webm`, `wma`, `aac`, `amr`, and the usual video containers (`mp4`, `mkv`, `mov`), whose audio track is extracted.
- **Formats out:** `.txt` with a header (source, duration, model, date, real compute time), plus optional `.srt` and `.vtt`. Output names follow a configurable pattern with `{nom}`, `{date}`, `{heure}` and `{modele}`.
- **Two presets.** *Highest quality* (`large-v3`) for anything that will be read back, *Fast* (`large-v3-turbo`) to get the gist. Other Whisper models are reachable in advanced mode.
- **Glossary and corrections.** A list of proper nouns primes the model before it transcribes, and a list of rewrite rules cleans up the recurring mistakes afterwards. See [the guide](docs/guide.md#vocabulary-and-corrections).
- **Read back in the app.** Uncertain words are highlighted, any word shows its confidence on hover, and correcting one can be remembered for good. See [the guide](docs/guide.md#reading-back-a-transcript).
- **Copy for AI.** One button puts your own instruction template, the metadata and the full text on the clipboard, ready to paste into the assistant of your choice. Nothing is sent by the app.
- **Progressive saving.** Text is written segment by segment. A crash or a power cut does not lose the work: the app offers to resume at the next start.
- **Watched folder,** off by default. A folder can be watched so that new recordings join the queue on their own, which suits a dictaphone or a meeting recorder that always drops files in the same place.
- **Speaker separation,** optional, installed from a button in the "Speakers" panel. Produces a labelled transcript, `Speaker 1`, `Speaker 2`, which is worth a lot for a meeting summary.
- **Taskbar progress,** disk usage report, export and import of your data as a single zip file, dark and light theme, three keyboard shortcuts and no more: `Ctrl` + `O`, `Ctrl` + `Enter`, `Esc`.

<!-- gif: drop two files, pick the Fast preset, start, progress bar filling, a finished line with its Read back button (about 15 s, no sound) -->

---

## Languages

- **Interface:** English and French. Follows your system language, switchable in the settings.
- **Transcription:** ten languages in the selector, French, English, Spanish, German, Italian, Dutch, Portuguese, Polish, Romanian, Arabic, each with an honest quality indicator, plus **automatic detection**, which opens up everything the Whisper models cover, about a hundred languages. One spoken language per recording.

---

## Privacy

**Nothing you transcribe leaves your computer.** No account, no API key, no upload to an online service, no telemetry. The audio is read from your disk, computed by your processor, and the text is written next to it.

Two things can use the network, both of them explicit:

- **Downloading a model**, once, the first time you use a preset. The app announces the size before starting.
- **The update check**, which is **off by default**. As long as it is off, the application makes no outgoing network call at all, apart from downloading the models you ask for.

Turned on, the update check queries the public releases page of this project at startup, **once a day at most**. Nothing about you or your files is sent, the call has a short timeout, and a failure, offline machine or firewall, produces no message at all: it goes to the log and that is it. A newer version shows a discreet banner with a button that opens the release page in your browser. Nothing downloads or installs on its own.

The Hugging Face token used for speaker separation is never included in an export, and never versioned.

---

## Known limits

- **Windows 64-bit only.** The code is portable, but hardware detection and the launch scripts target Windows. The interface relies on Microsoft Edge WebView2 Runtime, shipped with Windows 11 and up to date Windows 10; the setup installs it if missing.
- **One spoken language per recording.** Mixing languages inside the same conversation is handled poorly: Whisper settles on one language and transcribes the rest through it. English terms scattered through a French discussion are a different matter, and that is exactly what the glossary is for.
- **Designed for French first,** which is where it was tested most. Quality is equal or better in English and in the languages Whisper covers well, and the app tells you what to expect under the language selector: excellent, good, or variable.
- **The first run needs an internet connection** to download the model, 1.6 to 3.1 GB depending on the preset. After that, never again.
- **No AMD or Intel GPU acceleration.** Those machines transcribe on the processor.
- **Speaker separation installs separately**, about 0.8 GB to download and 3.6 GB on disk for the CPU build, more with an NVIDIA card. Keep 6 GB free while it installs. The button in the "Speakers" panel handles it, and a free Hugging Face token is still needed afterwards. Without it, everything else works.
- **The installer is not signed.** SmartScreen may warn on first run. A code signing certificate costs several hundred euros a year, which makes no sense for a free personal tool.
- **Audio is decoded entirely in memory,** about 230 MB per hour of recording. Comfortable up to several hours, but this is not stream processing.
- **Speaker labels are useful, not authoritative.** Overlapping speech and distant voices are the hard cases. Setting the number of participants improves the split noticeably.

---

**Want more?** Glossary and corrections, the reading view, speed by hardware, source install and diagnostics are covered in **[the full guide](docs/guide.md)**.

## Run from source

One reason left: **change the code**. Speaker separation installs from a button in both modes, so the source route is now for developers only.

```bat
git clone https://github.com/BurN-30/scribouille
installer.bat
lancer.bat
```

Details, manual install, speaker setup, project layout and build recipe: **[the full guide](docs/guide.md#run-from-source)**.

## Contributing

Issues and small pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE). Version history in [CHANGELOG.md](CHANGELOG.md).

Built on free software: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [CTranslate2](https://github.com/OpenNMT/CTranslate2), the [Whisper](https://github.com/openai/whisper) models from OpenAI, [pyannote.audio](https://github.com/pyannote/pyannote-audio), [pywebview](https://pywebview.flowrl.com/) and [FFmpeg](https://ffmpeg.org/).
