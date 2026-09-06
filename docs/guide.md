# Scribouille, the full guide

[Back to the README](../README.md)

---

## Vocabulary and corrections

Proper nouns, company names and technical terms are what automatic transcription mangles most. Two settings deal with that, and they complement each other.

**The glossary, `vocabulaire.txt`.** One term per line. The list is fed to the model **before** it transcribes, as the start of its context, which steers Whisper towards those spellings.

```
Jean Dupont
MyCompany
GitLab
Kubernetes
GDPR
```

A Whisper prompt cannot exceed **224 tokens**, roughly a hundred short terms. Beyond that, faster-whisper silently truncates. Scribouille truncates cleanly instead, keeping the terms **at the top of the list**, and says so in the interface. Put the important ones first. The token count is exact: it uses the tokeniser of the model actually loaded. The introduction sentence of the prompt follows the **spoken language** of the recording, never the interface language: the model reads it as the beginning of a text, and a French sentence has no business at the head of an English recording.

**The corrections, `corrections.txt`.** For the recurring damage the prompt does not prevent. One rule per line, applied to the final text, case insensitive, whole words only, so the rule `git` will not touch `digital`.

```
guitte lab => GitLab
cubernetes => Kubernetes
```

Both files are plain text. Edit them by hand or from the panels in the app. The **My data** panel exports them, with your settings and your AI template if you have one, as a single `scribouille-donnees-YYYY-MM-DD.zip` you can put on a USB stick or in a company backup. An import shows a preview of what would change and writes nothing before you confirm, and the previous state is saved next to it first.

---

---

## Reading back a transcript

A transcript opens **in the app**, no editor needed: click a line in the Transcripts tab, or the read button on a file that just finished.

<!-- screenshot 2: reading view, a paragraph with two or three amber highlighted words, the confidence tooltip visible on one of them -->

Whisper gives a probability for every word it writes. The reading view **highlights only the uncertain ones**, in discreet amber: below 0.50 the mark is light, below 0.30 it is clearer. Hovering any word shows its confidence, highlighted or not. In practice that flags around one word in ten in the worst case, and one in thirty-five with a decent model, so a handful of places to listen to again rather than a striped document.

These values live in a **companion `.json` file** written next to the text, a few tens of kilobytes per hour of audio. It is optional: an older transcript, or one produced with the option off, opens normally without highlighting.

Selecting a word or a short phrase offers to **correct it**. The app applies the replacement to the text on screen and to the saved file, updates the companion, and adds the rule to a dedicated section of `corrections.txt` so the same mistake is fixed automatically from then on.

**Copy for AI** puts an instruction template, the recording metadata and the full transcript on the clipboard. The template is your own file, `gabarit-ia.txt`, created on first use and editable from the settings, with `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` and `{modele}` replaced at copy time.

---

---

## Speed

The factor below is compute time divided by audio duration. Under 1 is faster than listening.

| Hardware | Highest quality | Fast | One hour of audio, in quality |
|---|---|---|---|
| Thin laptop, 12 to 14 threads, no dedicated card | about 1.2 x | about 0.3 x | about 1 h 15 |
| Desktop processor, 16 threads and up | about 0.7 x | about 0.2 x | about 40 min |
| Modest laptop, 4 to 8 threads | about 2 x | about 0.5 x | about 2 h |
| NVIDIA card (CUDA, float16) | about 0.1 x | about 0.05 x | about 6 min |

**These are starting estimates, not guarantees.** They are calibrated on public measurements and adjusted to the number of cores on your machine. The app shows the **time actually measured** after every transcription, and writes it in the header of the output file. Speaker separation adds roughly 0.2 x on CPU.

**They correct themselves.** As soon as a transcription completes, the observed factor is kept, and it is what the next announcements are based on: the hardware card then says "measured on this machine". The last five measurements are averaged, the most recent and the longest weighing the most, and every combination of model and beam width is tracked separately. Nothing to set up, and nothing goes online: the measurements live in `calibration.json`, next to your settings.

Acceleration in this version: **CPU everywhere** with `int8` quantisation, which is the default and perfectly usable, and **NVIDIA cards** in CUDA `float16`, automatically, when the driver and libraries answer. AMD Radeon cards, Intel integrated graphics and NPUs are detected and displayed but **not used**, because faster-whisper sits on [CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html), which supports x86-64 and ARM64 CPUs and NVIDIA GPUs only. The app says so plainly rather than implying an acceleration that does not exist.

<details>
<summary>What could change that, later</summary>

**whisper.cpp with the Vulkan backend** is the solid path, and the only realistic one to accelerate a Radeon on Windows: a C/C++ port independent of PyTorch and CUDA, doing multi-vendor GPU inference without vendor specific code. Public measurements put it around 8 x real time on an RX 9070 XT, and 3 to 4 times better than CPU alone on a Radeon 680M integrated GPU. It would ship as a prebuilt Windows Vulkan binary driven as a subprocess, so that nobody has to install a C++ toolchain. The cost is a second model format, GGUF instead of CTranslate2, and an engine abstraction layer, which is why it is not here yet.

**OpenVINO for Intel integrated GPUs and NPUs** is interesting but not mature enough for a turnkey tool: the backend wants a precise OpenVINO version, and Whisper model conversion breaks with some `transformers` versions. As for the NPU itself, its appeal is battery life, a few watts against 15 to 25 for the integrated GPU, not raw speed. If Intel acceleration ever becomes a goal, Vulkan is the simpler and more robust route.

</details>

---

---

## Run from source

One reason left to go this way: **change the code**. Speaker separation installs from a button inside the application, whichever version you run. For normal use, the setup above is enough.

1. Install [Python 3.9 or newer](https://www.python.org/downloads/), ticking **Add python.exe to PATH**.
2. Double-click **`installer.bat`**.
3. Answer the question about speaker separation, then let it run.
4. Double-click **`lancer.bat`**.

The installer is re-runnable, only installs what is missing, and creates an isolated environment in `.venv` without touching the system Python. It needs neither administrator rights, nor winget, nor Chocolatey: FFmpeg comes from a Python package that ships the binary.

| Option | Effect |
|---|---|
| `installer.bat` | Standard install, asks about speakers |
| `installer.bat --locuteurs` | Adds speaker separation (PyTorch and pyannote), the command line equivalent of the button in the app |
| `installer.bat --sans-locuteurs` | Light install, no question |
| `installer.bat --verifier` | Prints the state of the machine and exits |

Run from source, the app keeps everything next to the script: `config.json`, `logs/`, `modeles/`, glossary and corrections. That is the only behavioural difference with the installed version.

<details>
<summary>Manual install, for those who prefer to keep control</summary>

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

REM Only with an NVIDIA card: avoids the "cublas64_12.dll not found" error
REM without touching the system PATH.
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*

REM Only for speaker separation, and only if you insist on doing it by hand:
REM the button in the application does exactly this.
REM Without an NVIDIA card:
pip install torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cpu
REM With an NVIDIA card:
pip install torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cu124
REM The versions are repeated on purpose: pyannote.audio only sets lower
REM bounds, and pip would otherwise pull newer builds from PyPI, compiled
REM against a different PyTorch.
pip install -r requirements-locuteurs.txt torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple

.venv\Scripts\pythonw transcriber.pyw
```

The base is about 250 MB. Speaker separation adds 3.55 GB, measured, because it pulls in PyTorch, which is precisely why it is optional and why it stays out of the setup.

Check the state of the machine, the FFmpeg decoder, the work folders and hardware detection:

```bat
.venv\Scripts\python transcriber.pyw --verifier
```

</details>

<details>
<summary>Setting up speaker separation</summary>

**From the application, it is one button.** Open the "Speakers" panel and click "Install speaker separation". The app announces the download size, about 0.8 GB for the CPU build, the room needed on disk, 6 GB, and how much is free. Those figures are measured on a real install: 0.71 GB of wheels downloaded, 3.55 GB of files laid down. It asks for confirmation, then downloads in the background: progress is shown, cancelling is possible at any point, and transcription stays usable meanwhile. A network drop does not mean downloading everything again: what already arrived is kept, and a new run only asks the network for what is missing. It does lay the files down again, a few minutes of disk, the only safe way not to leave the leftovers of an interrupted attempt in place.

The button picks the right build on its own: CPU by default, CUDA when an NVIDIA card answers. In the installed version the components land in `%LOCALAPPDATA%\WhiScribe\extensions`, and a second button removes them, with their size shown. From source they land in the project `.venv`, exactly like `installer.bat --locuteurs`.

**Then the token.** That is a separate step, unrelated to the download.

The model that recognises voices, pyannote, is free but gated: its author asks you to accept the terms and identify yourself.

1. Create an account on [huggingface.co](https://huggingface.co).
2. Open [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) and accept the terms.
3. Create a **Read** access token in your account settings.
4. Paste it into the Speakers panel of the app.

The token is saved in `jeton_hf.txt`, with your data, and is never versioned. The `HF_TOKEN` environment variable is recognised too, and takes precedence. Without a token everything still works, simply without labels and with a clear message rather than an error.

Whisper and pyannote are **sequenced**, never loaded at the same time: the app transcribes, releases the Whisper model explicitly, forces a garbage collection, then loads diarisation. Peaks follow each other instead of adding up, so `large-v3` plus pyannote fit in 16 GB.

</details>

<details>
<summary>How the project is laid out</summary>

One engine, faster-whisper on CTranslate2. whisperX was removed: it forces PyTorch, its word level alignment is not needed here, its VAD is now built into faster-whisper, and driving a library rather than a subprocess gives per segment progress, exact control over memory release between stages, typed errors, and access to the model tokeniser to measure the prompt budget precisely.

```
transcriber.pyw       window, bridge to the interface, --verifier mode
installer.py          re-runnable installer, source version
app/
  chemins.py          locations, source or installed version
  materiel.py         processor, memory, GPU and NPU detection
  presets.py          presets, estimates, memory guardrails
  audio.py            FFmpeg, duration, 16 kHz mono decoding
  moteur.py           faster-whisper, loading and release
  diarisation.py      pyannote, token, speaker attribution
  extensions.py       speaker separation install, embedded pip
  vocabulaire.py      glossary, prompt, corrections
  sorties.py          txt, srt, vtt, headers
  nommage.py          output file name pattern
  surveillance.py     watched folder, polling and memory
  stockage.py         disk usage of models, data and program
  maj.py              optional check of published releases
  barre_taches.py     Windows taskbar progress
  compagnon.py        .json file of word by word confidence
  lecture.py          reading view, learned corrections, copy for AI
  gabarit.py          instruction template for an AI assistant
  reprise.py          progressive saving and resume after interruption
  traitement.py       sequential queue
  config.py           configuration
  journal.py          logging and translation of incidents
  langues.py          French and English catalogues, Python side
web/                  interface (HTML, CSS, JavaScript), langues.js
outils/               measurement and verification harnesses, outside the app
packaging/            PyInstaller recipe, Inno Setup script, icon
.github/workflows/    release pipeline
```

Where files live, depending on how the app was started:

| | Installed version | Source version |
|---|---|---|
| Program | `%LOCALAPPDATA%\Programs\Scribouille` | the cloned repository |
| Settings, logs, glossary | `%LOCALAPPDATA%\WhiScribe` | next to the script |
| Models | chosen at install time, changeable in the settings | `modeles/`, changeable in the settings |

The data folder still carries the old application name, on purpose: renaming it in 2.4.0 would have left the settings, the glossary and the models of every existing installation behind.

</details>

<details>
<summary>Building the installer</summary>

Publication is automated: pushing a `vX.Y.Z` tag triggers `.github/workflows/release.yml`, which builds, verifies, produces the setup and creates the Release with the file attached. Release notes are the matching section of [CHANGELOG.md](CHANGELOG.md). The same workflow runs by hand from the Actions tab, without a tag: it builds and verifies everything but publishes nothing.

```bat
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\scribouille.spec
dist\Scribouille\scribouille-verifier.exe
iscc /DVersionApp=2.3.0 packaging\setup.iss
```

The version number has a single source, `VERSION` in `app/__init__.py`, and the workflow refuses to publish if the tag does not match. PyInstaller 6.22 is the minimum: earlier versions cannot freeze numpy 2.5.

A release that cannot update in place is announced by writing `[reinstallation-requise]` anywhere in its CHANGELOG section. The update banner then tells the user to uninstall first, and that data and models are kept, which is true since they live outside the program folder.

</details>

---

---

## Diagnostics

Every failure is explained in the interface, in plain language: unreadable file, model to download, not enough memory, missing or invalid token, full disk, missing CUDA libraries. No traceback ever reaches the screen.

The technical detail goes to a timestamped file in `logs/`, whose name is quoted in the error message. The **Open the detailed log** button, in the bottom bar, opens it directly. The last 30 logs are kept. That file is what to attach to a bug report, and the logs are written in French: they are aimed at the maintainer, not at the user.

Three more modes cover speaker separation, again without a window. They are what the application runs against itself, in a background process, when the button in the "Speakers" panel is clicked; they also serve to validate a build without clicking anything:

```bat
REM Install the components, here into a scratch folder rather than the real one
dist\Scribouille\scribouille-verifier.exe --installer-locuteurs --cible D:\scratch --cpu

REM Actually import torch and pyannote. Exit code 0 when both answer.
dist\Scribouille\scribouille-verifier.exe --verifier-locuteurs --cible D:\scratch

REM Wipe it
dist\Scribouille\scribouille-verifier.exe --retirer-locuteurs --cible D:\scratch
```

`--paquets` replaces the list with your own, which proves the mechanism with a light package instead of several gigabytes. Without `--cible`, the real extensions folder is used. From source, the same options live on `python -m app.extensions`.

---

