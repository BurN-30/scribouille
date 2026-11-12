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

### Vocabulary, format 2 (`vocabulaire.toml`)

The **Vocabulary and suggestions** button opens a screen that gathers both settings in a single file, `vocabulaire.toml`, readable and editable by hand (a subset of TOML). Each term carries its correct form, its category (person, company, acronym, product or tool, trade term, English word), what the model writes instead, a weight from 1 to 5, its origin and its state: **active**, **suggested** or **rejected**. Only active terms are used. Fictitious example:

```toml
format = "scribouille-vocabulaire"
version = 2

[[terme]]
forme = "Martin Lebrun"
categorie = "personne"
fautes = [
  "martin le brun",
  { forme = "martin", voisins = ["monsieur", "lebrun"] },   # only near these words
]
poids = 3
etat = "actif"
```

What the app does with it, in three stages:

1. **Prompt.** Terms are fed to the model within the 224-token limit. When they do not all fit, those suggested by the file name come first, then the heaviest; with OpenVINO, the prompt is rebuilt for each 30-second window from what the previous window just said.
2. **Correction afterwards**, deterministic: listed errors are brought back to their form (always, or only near their neighbours), casing is restored ("rgpd" becomes "RGPD"), and a form that **sounds** like a term ("Aokland" for "Auckland") is matched, with safeguards: never a common French word, never a term under four sounds, never when two terms are equally close. An error made of common words ("mon entreprise") is only applied in its context, or if you force it. Every replacement is listed in the reading view, with an **Undo** button.
3. **Clean-up by a small language model**: not included, studied only.

**Several files.** A team or project vocabulary is added under **Shared files**: it is read on top of yours, which has the last word. **Export** writes a file to share; **Import suggestions** pours a file into your vocabulary as suggestions.

**Learning from your corrections.** A correction made in the reading view without remembering a rule becomes a suggestion. And `scribouille-verifier.exe --apprendre-vocabulaire --brut RAW.txt --propre REVIEWED.docx [--cr MINUTES.docx] [--importer]` compares raw transcripts with their reviewed versions (text, Word, Markdown, text PDF) and suggests systematic errors (with their counts of occurrences and meetings), plus the proper nouns and acronyms of the clean documents. Nothing is used before it is accepted in the Vocabulary screen. The numbers-only report that comes with it contains no term.

**The old format is still read.** As long as `vocabulaire.txt` and `corrections.txt` contain terms, they are used as they are. **Convert** moves them into `vocabulaire.toml` without losing anything and keeps a copy of the old files.

**Measuring.** `scribouille-verifier.exe --mesurer-vocabulaire --vocabulaire V.toml --reunion AUDIO --reference REVIEWED` transcribes each meeting without, then with the prompt, applies the correction, and reports the word error rate, recall and precision of the terms by category, and the number of wrong corrections. Measure on meetings that were not used to learn the vocabulary.

The two format 1 files are plain text. Edit them by hand or from the panels in the app. **Settings, Application, My data** exports them, with your settings and your AI template if you have one, as a single `scribouille-donnees-YYYY-MM-DD.zip` you can put on a USB stick or in a company backup. An import shows a preview of what would change and writes nothing before you confirm, and the previous state is saved next to it first.

---

## Reading back a transcript

A transcript opens **in the app**, full screen, no editor needed: the **Review** button of a file that just finished, or of a row in the "Transcripts" list. The text shown is the file's text, paragraph by paragraph, with the time in the margin (and the voice when speakers are separated). The review resumes where it stopped: scrolling and playback position are kept for each transcript.

**One truth.** The screen, the `.txt`, the `.json` companion and the subtitles always say the same thing: every change is checked against the files read back, and a write that would make them differ is cancelled and reported. A `.txt` edited in a text editor is read as it is, on opening as during the review, and word-by-word listening is realigned to it.

**Listen.** Clicking a word places playback there, **Space** plays or pauses (whatever button was clicked last), the arrow keys go back or forward 5 s, comma and semicolon change the speed (`[` and `]` too); while playing, the word being heard is marked and the text follows. Clicking a paragraph's time plays it from its start. The recording must still be where it was.

**Search and check.** **Ctrl+F** searches regardless of case and accents, every result highlighted, **Enter** or **F3** for the next one. The **Points to check** list steps through, with **N** (Shift+N to go back), doubtful words, replacements made by the vocabulary (each one can be undone), silences over 5 s and paragraphs over 90 s; only non-empty categories are offered. With OpenVINO, which gives no per-word confidence, there are no doubtful words. After a correction, **N** carries on from where you were.

**Speakers.** Clicking "Speaker 1" renames it throughout the file, its companion and its subtitles; a name already in use merges the two voices, their paragraphs staying separate.

**Export.** Copy the text (exactly as in the file), with timestamps (when they are known), or as Markdown; save a `.md` next to the transcript. All of them start from the same text as the screen.

<!-- screenshot 2: reading view, a paragraph with two or three amber highlighted words, the confidence tooltip visible on one of them -->

Whisper gives a probability for every word it writes. The reading view **highlights only the uncertain ones**, in discreet amber: below 0.50 the mark is light, below 0.30 it is clearer. Hovering any word shows its confidence, highlighted or not. In practice that flags around one word in ten in the worst case, and one in thirty-five with a decent model, so a handful of places to listen to again rather than a striped document.

These values live in a **companion `.json` file** written next to the text, a few tens of kilobytes per hour of audio. It is optional: an older transcript, or one produced with the option off, opens normally without highlighting.

Selecting a word or a short phrase offers to **correct it** (button or **Enter**; with the keyboard alone, **N** then **Enter** corrects the word reached). The window lists every place in the file containing that form, with its context: the selected one is ticked, located by its exact position (part of a word, or a selection starting at an apostrophe, never corrects anywhere else), the others can be ticked one by one or all at once; **Enter** confirms from anywhere in the window. A case correction ("gitlab" to "GitLab") is accepted. The "Always replace" box, unticked by default, makes the rule apply to later transcripts; without it, the vocabulary learns nothing.

**Rewrite or delete a passage.** Under a selection of any length, **Edit** (key **E**) opens the passage; without a selection, **E** opens the paragraph of the word reached. **Del** deletes the selection. A paragraph left empty disappears.

**Undo.** **Ctrl+Z** undoes the last change, then the one before, up to fifty, even after closing the app; the file comes back byte for byte. **Export, Go back to the original text** restores the state before any change, and can be undone too.

**Copy for AI** puts an instruction template, the recording metadata and the full transcript on the clipboard. The template is your own file, `gabarit-ia.txt`, created on first use and editable from the settings, with `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` and `{modele}` replaced at copy time.

---

## Speed

The factor below is compute time divided by audio duration. Under 1 is faster than listening.

| Hardware | Highest quality | Fast | One hour of audio, in quality |
|---|---|---|---|
| Desktop processor, 8 cores / 16 threads (Ryzen 7 7800X3D), **measured** | 0.4 x | 0.15 x | about 23 min |
| Same processor, OpenVINO engine, **measured** | 0.24 x | 0.09 x | about 14 min |
| Intel graphics of a Core Ultra 7 265U, OpenVINO, measurement published by a third party | not measured | 0.12 x | estimated around 20 min |
| CPU alone of the same Core Ultra 7 265U, faster-whisper, measurement published by a third party | not measured | 1.04 x | over an hour |
| NVIDIA card (CUDA, float16), estimate, not measured | about 0.1 x | about 0.05 x | about 6 min |

The measured row was taken in November 2026 on a three-minute French excerpt, with other programs busy on the machine: an idle machine is a little faster. A more modest processor takes longer. Since 2.4.0, speech passages are decoded **in batches**, which, together with one compute thread per physical core, cuts compute time by two and a half to three at equal quality, for about 2.5 GB more memory. Below 12 GB of RAM the app skips batching, and compute takes about twice as long.

**Before the first transcription, the app shows a starting estimate, not a guarantee.** It is calibrated on public measurements and adjusted to the number of cores on your machine. The app shows the **time actually measured** after every transcription, and writes it in the header of the output file. Speaker separation adds roughly 0.2 x on CPU.

**They correct themselves.** As soon as a transcription completes, the observed factor is kept, and it is what the next announcements are based on: the durations shown are recalculated after each file. The last five measurements are averaged, the most recent and the longest weighing the most, and every combination of model and beam width is tracked separately. Nothing to set up, and nothing goes online: the measurements live in `calibration.json`, next to your settings.

Acceleration: **CPU everywhere** with `int8` quantisation; **NVIDIA cards** in CUDA `float16`, automatically, when the driver and libraries answer; and, since 2.4.0, **Intel integrated graphics** (and, experimentally, the NPU) through the optional **OpenVINO** engine. AMD Radeon cards are detected and displayed but not used.

### Intel laptops (Core Ultra and similar)

On a 15 W laptop without a dedicated card, the CPU alone can take longer to transcribe than the meeting lasted. Three things change that, all in the settings (**This computer**, **Engine and models**, **Benchmark**):

- **The number of compute threads follows the architecture.** Core Ultra U-series chips mix performance, efficient and low-power cores (2 + 8 + 2 on a Core Ultra 5 225U). The app recognises them and leaves out the low-power cores, capped at 2.4 GHz and without L3 cache, which would slow the whole computation down. It also stops Windows from throttling the transcription when the window is minimised.
- **The OpenVINO engine** (Intel, Apache 2.0 licence, about 90 MB from PyPI) transcribes on the integrated graphics. The only published measurement on a processor of the same family (Core Ultra 7 265U): 0.12 x with the Fast model on the integrated graphics, against 1.04 x on its CPU, identical text. Models in OpenVINO format (0.8 GB for Fast, 1.6 GB for Quality) are downloaded on first use. What you lose: the probability of each word, which this engine does not give (the review view then highlights no uncertain word). Everything else is kept: timestamped segments, word timestamps for speakers, glossary, resume after interruption, stop. If OpenVINO fails, the usual engine takes over without losing what is already transcribed.
- **The benchmark** transcribes a 44 s clip shipped with the app under several settings (compute threads, batches, Fast and Quality models, every available engine and device), compares the text with the reference, then recommends the fastest one that stays accurate. It takes five to ten minutes. Nothing changes until you click **Apply the recommended setting**; **Back to the automatic setting** undoes it all. The report (`rapports-banc\` in the data folder) contains no user name, machine name or path: it can be sent as is. Plug the laptop in before running it.

From the command line, without a window: `scribouille-verifier.exe --banc` in the installation folder (or `.venv\Scripts\python transcriber.pyw --banc` from source); add `--telecharger` to fetch missing models, `--npu` to try the NPU, `--appliquer` to apply the recommendation.

**Compare both engines on your own recordings.** The benchmark measures speed on 44 s of sentences read by a single voice: it says nothing about accuracy on a real meeting (several voices, broken sentences, swallowed words, English words, team vocabulary). The comparison transcribes the same excerpt of one of your files with CTranslate2 and with OpenVINO, each in its Quality setting, with your language, glossary and corrections, then writes into `comparaisons\` in the data folder:

- `cote-a-cote.html`, to open in the browser: both timestamped texts side by side, passages where they disagree highlighted, words CTranslate2 is unsure of underlined with dots, and clicking a time plays the passage. This page contains the transcript, like the `textes-*.json` files next to it: they stay on the computer;
- `rapport-chiffres.txt`: figures only (computing times, word counts, disagreement rate, diverging passages by kind, timing gaps, segments, glossary terms, common English words, uncertain words), without a single word of the transcript, name or path. This one can be shared.

From the window: **Settings, Compare engines** (once OpenVINO is installed). From the command line:

```
scribouille-verifier.exe --comparer "D:\Meetings\weekly.m4a" --debut 00:05:00 --duree 600 --ouvrir
```

`--debut` and `--duree` (seconds, or `hh:mm:ss`) choose the excerpt; its edges are moved to the nearest pause so that no sentence is cut. `--reference FILE` adds an already reviewed transcript of the same recording (text, SRT, VTT, Scribouille text export or `.json` companion; timestamps and speaker names are ignored): the report then gives each engine's error rate, and the page a third column. On an excerpt, the reference must be timestamped (SRT, or an export with timestamps): without timestamps, comparing with the reference is only possible on the whole file. A reference produced by Scribouille and lightly corrected favours CTranslate2, which wrote it. Other options: `--peripherique GPU|CPU|NPU` (by default the Intel integrated graphics if OpenVINO sees it), `--preset rapide`, `--sans-glossaire`, `--sans-corrections`, `--faisceau-openvino 5`. Expect two to three times the excerpt length on a laptop, much less on the integrated graphics.

What is already known, measured on three public meetings with three or four voices (SUMM-RE corpus) on the processor: OpenVINO is not less accurate than CTranslate2 there, equal on single-voice speech, slightly better where voices overlap. That is no guarantee for your meetings, nor for the integrated graphics, which computes differently (fp16): the comparison is there to check it.

**Choosing the setting on hand-transcribed meetings: the campaign.** The comparison shows where two engines diverge, without saying which is right. The campaign measures it, on 22.8 minutes of public French meetings with three or four voices, transcribed by hand (SUMM-RE ASRU corpus, Laboratoire Parole et Langage and LINAGORA, CC BY-SA 4.0 licence):

```
scribouille-verifier.exe --campagne
```

Seven settings run one after the other (CTranslate2 and OpenVINO, large-v3 and turbo, beams 1 and 5), glossary and corrections off. The report, without a transcribed word or path, gives for each the word error rate with its confidence interval, the words lost when two people speak at once, long insertions, speed, then the verdict: among the settings faster than the meeting and as accurate as the best, the fastest. `--appliquer` saves it as this computer's setting; without it, nothing changes. The corpus is read from `corpus-campagne-v1.zip` placed next to the program, or downloaded (476 MB, Hugging Face then ORTOLANG). An interrupted campaign resumes where it stopped; the computer does not go to sleep while it computes. Allow an hour and a half on a Core Ultra laptop with the graphics chip. `--reunion FILE --debut 00:05:00 --duree 600` then runs the same settings on one of your meetings and gives their agreement with the chosen setting, still without a word of the text. Other options: `--reglages ov-v3-f1,ct2-v3-f5`, `--limite-extraits 3`, `--recommencer`, `--corpus PACK.zip`, `--telecharger`.

**Checking that the setting holds: the endurance test.** `scribouille-verifier.exe --endurance` runs the setting chosen by the campaign thirty times in a row, on extracts of about two minutes from the same corpus, like the app's queue. The report, still without any text, gives the failure rate before and after the automatic replay, the exact error of each incident and the computer's free memory each time the model opens. `--pression` also loads, every other run, the CTranslate2 large-v3 model and leaves only 4 GB free (`--memoire-libre 4`), to test a busy computer. Allow half an hour to three quarters of an hour on a Core Ultra laptop. Other options: `--passages 30`, `--reglage ov-turbo-f1`, `--recommencer`, `--sans-diagnostic`.

On Intel integrated graphics, OpenVINO only decodes greedily (beam 1): this is a limit of OpenVINO GenAI 2026.4, and the app never applies a wider beam on that chip. If OpenVINO fails on a window, the app reopens the model and carries on on the graphics chip; if it happens again, it finishes the transcription with the usual engine, losing nothing already transcribed.

### Setting proposed for this computer

On first start, and each time you click **Recognise this computer** (**Settings, This computer**), the application looks at the computer (processor and core families, memory, Intel graphics chip seen or not by OpenVINO, NVIDIA card, NPU, battery or mains, Windows power mode) and proposes a setting, explained in one sentence, with the expected duration for an hour of meeting. If a campaign or a benchmark was run on the computer, its result comes before the table; if it no longer fits (graphics chip missing, broken driver, OpenVINO removed), the proposal says so and starts again from the hardware. Nothing changes without **Apply**, nothing is downloaded or installed on its own: a missing model is announced with its size and only downloaded when a transcription starts; OpenVINO keeps its own install button. From the command line: `scribouille-verifier.exe --reconnaitre`, then `--reconnaitre --appliquer`.

The table, read from top to bottom: NVIDIA card, Highest quality on the card; Intel graphics chip seen by OpenVINO, Fast on the chip (an hour in about 7 minutes on a Core Ultra 5, as accurate as Highest quality on the processor according to the campaign on the test laptop); Intel chip present but unusable, Fast with OpenVINO on the processor; under 10 GB of memory, Fast; processor only, OpenVINO if installed, otherwise Fast on a modest processor (under 12 threads or U series) and Highest quality on a desktop processor. The proposed pace is **Balanced, adapting automatically**.

### Working during a transcription

The **While transcribing** section of the settings bounds what the transcription takes from the computer:

| | Maximum speed (default) | Balanced | Low impact |
|---|---|---|---|
| Compute threads | all those of the computer's setting | about three quarters, two logical threads left free | half, placed on the efficient cores of a hybrid processor |
| Passage batches | those of the preset | 4 at most | one passage at a time (less memory) |
| Windows priority | normal | below normal | low, and input-output at low priority |
| Frequency (quality of service) | throttling lifted (as before) | decided by Windows | Windows "efficiency mode" (EcoQoS) |
| Graphics chip (OpenVINO) | unchanged | low-priority queue | low-priority, low-throttle queue, a pause equal to the computation after each window |
| Low free memory | nothing changes | batches, then a lighter model, and it is said | same |

**Adapt automatically**: the transcription takes the chosen pace while you use the computer (keyboard or mouse touched less than two minutes ago, other programs using more than 30 % of the processor, full screen or presentation, microphone open for a call, laptop on battery) and maximum speed when it is idle. Threads and batches are fixed when the model loads: they are then those of maximum speed, and switching goes through priority, quality of service and pauses. On battery, the chosen pace is kept until the laptop is plugged in. The remaining time shown follows the pace actually observed, switches included. The choice applies from the next transcription.

Measuring each pace on the computer: `scribouille-verifier.exe --banc --modes` (add `--peripherique GPU` for the graphics chip). For each pace: speed, memory, processor left free, and impact measured on a small probe task standing in for your applications. The measured duration ratios then replace the starting coefficients of the estimates.

During a transcription, the computer no longer goes to sleep for lack of activity (closing the lid keeps its effect), and closing the window asks for confirmation: what is already transcribed is kept and offered for resuming.

**Filtered company network.** If PyPI or Hugging Face are blocked, the error messages give the offline route: for a model, copy its `models--...` folder from a computer that already downloaded it into the models folder; for OpenVINO, drop the three `.whl` files (obtained elsewhere with `pip download`) into `paquets-hors-ligne\` in the data folder, then start the installation again. No administrator rights are needed: everything installs in the user's folder.

<details>
<summary>Options set aside for now, and why</summary>

**whisper.cpp with Vulkan or OpenVINO**: no official Windows binary with these backends (version 1.9.5, October 2026); it would have to be built in house, with another model format (GGUF). OpenVINO GenAI installs as three Python packages and reads models already converted by Intel: that is the path taken.

**The NPU**: supported by OpenVINO, but the only published run on a laptop of this family saw it hang with the Fast model (Core Ultra 7 265U, October 2026). The benchmark still offers it, experimentally, and it is never chosen unless it succeeded there.

**AMD Radeon cards**: CTranslate2 can compute on them with ROCm on Windows since 4.9.0, but the app does not ship those libraries yet (about 1.1 GB).

</details>

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

**From the application, it is one button.** In **Settings, Transcription**, "Speakers" block, click "Install speaker separation". The app announces the download size, about 0.8 GB for the CPU build, the room needed on disk, 6 GB, and how much is free. Those figures are measured on a real install: 0.71 GB of wheels downloaded, 3.55 GB of files laid down. It asks for confirmation, then downloads in the background: progress is shown, cancelling is possible at any point, and transcription stays usable meanwhile. A network drop does not mean downloading everything again: what already arrived is kept, and a new run only asks the network for what is missing. It does lay the files down again, a few minutes of disk, the only safe way not to leave the leftovers of an interrupted attempt in place.

The button picks the right build on its own: CPU by default, CUDA when an NVIDIA card answers. In the installed version the components land in `%LOCALAPPDATA%\Scribouille\extensions`, and a second button removes them, with their size shown. From source they land in the project `.venv`, exactly like `installer.bat --locuteurs`.

**Then the token.** That is a separate step, unrelated to the download.

The model that recognises voices, pyannote, is free but gated: its author asks you to accept the terms and identify yourself.

1. Create an account on [huggingface.co](https://huggingface.co).
2. Open [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) and accept the terms (CC-BY-4.0 licence; the form asks for an organisation and a use case, and pyannote may email you now and then). This model, more accurate than the older 3.1, is tried first; 3.1 is still used if you only accepted its terms.
3. Create a **Read** access token in your account settings.
4. Paste it into the "Speakers" block (Settings, Transcription).

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
  audio.py            16 kHz mono decoding (FFmpeg through PyAV), duration
  moteur.py           faster-whisper, loading and release
  diarisation.py      pyannote, token, speaker attribution
  extensions.py       speaker separation install, embedded pip
  vocabulaire.py      glossary, prompt, corrections (format 1)
  vocabulaire_v2.py   vocabulary format 2: file, merge, migration, review
  vocabulaire_usage.py prompt selection, correction afterwards and safeguards
  vocabulaire_interface.py Vocabulary screen
  lexique.py          common French words, phonetic key
  apprentissage.py    suggestions learned from reviewed transcripts
  documents.py        document text (Word, text PDF, Markdown, subtitles)
  mesure_vocabulaire.py gain of each stage, against a reference
  sorties.py          txt, srt, vtt, headers
  nommage.py          output file name pattern
  surveillance.py     watched folder, polling and memory
  stockage.py         disk usage of models, data and program
  maj.py              optional check of published releases
  barre_taches.py     Windows taskbar progress
  compagnon.py        .json file of word by word confidence
  lecture.py          reading view, learned corrections, copy for AI
  ecoute.py           local server of the audio for the reading view
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
| Settings, logs, glossary | `%LOCALAPPDATA%\Scribouille` (`WhiScribe` up to 2.4, taken over on first launch) | next to the script |
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

## Diagnostics

Every failure is explained in the interface, in plain language: unreadable file, model to download, not enough memory, missing or invalid token, full disk, missing CUDA libraries. No traceback ever reaches the screen.

The technical detail goes to a timestamped file in `logs/`, whose name is quoted in the error message. The **Open the detailed log** button, in the bottom bar, opens it directly. The last 30 logs are kept. That file is what to attach to a bug report, and the logs are written in French: they are aimed at the maintainer, not at the user.

Three more modes cover speaker separation, again without a window. They are what the application runs against itself, in a background process, when the button in the "Speakers" block is clicked; they also serve to validate a build without clicking anything:

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

