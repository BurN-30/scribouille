# Contributing

Issues and small pull requests are welcome. Scribouille is maintained by one person, so
a focused change with a clear reason gets merged much faster than a large one.

Before opening an issue, please check the [known limits](README.md#known-limits): some
things are missing on purpose. Bug reports need the **log file**, never the audio.

## Development setup

```bat
git clone https://github.com/BurN-30/scribouille
cd scribouille
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
.venv\Scripts\pythonw transcriber.pyw
```

Python 3.9 or newer, Windows 64-bit. Speaker separation is installed from the button in the
"Speakers" panel of the app, in both modes, or with `installer.bat --locuteurs`. Nothing else, no build step for the interface:
`web/` is plain HTML, CSS and JavaScript, served to the WebView as is.

## Before opening a pull request

There is no unit test suite. What exists is a set of harnesses in `outils/`, meant to be
run by hand, without the network and without a window:

```bat
.venv\Scripts\python transcriber.pyw --verifier
.venv\Scripts\python outils\verifier_traductions.py
.venv\Scripts\python outils\verifier_chaine_lecture.py
.venv\Scripts\python outils\verifier_fonctions_peripheriques.py
.venv\Scripts\python outils\verifier_donnees.py
```

All of them exit with code 0 when everything passes. Run at least `--verifier` and
`verifier_traductions.py`, plus the one covering the area you touched. There is also
`outils/mesure_sauvegarde_progressive.py`, which measures the cost of progressive saving;
it is a measurement, not a check.

Please also add a line to the top section of [CHANGELOG.md](CHANGELOG.md). Do not bump
`VERSION` in `app/__init__.py`, releases are cut by the maintainer.

## Interface strings

**French is the source language.** Every visible string lives in two twinned catalogues,
`app/langues.py` for what Python produces and `web/langues.js` for what the interface
writes, with a French and an English dictionary in each. No string is ever hardcoded in
`web/app.js` or in `web/index.html`: the HTML carries `data-i18n` attributes only.

Adding a string means adding the key to both languages, in the right catalogue. English
parity is not optional and it is checked:

```bat
.venv\Scripts\python outils\verifier_traductions.py
```

It verifies that French and English keys match on both sides, that every key used by the
code exists, that no French text is left hardcoded in the web files, that substitution
variables are identical between the two languages, and that no em dash slipped in.

## Style

- French in the code: module names, comments and log messages. The logs in `logs/` are
  written in French on purpose, they are a maintainer tool.
- Short modules, one concern each, as in the existing `app/` layout.
- No new heavy dependency without discussing it in an issue first. The whole point of the
  setup being a few hundred megabytes is that PyTorch stays optional.
- No em dashes, anywhere, in any language. Commas or colons.
