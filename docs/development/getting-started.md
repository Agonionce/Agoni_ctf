# Agonionce Development Guide

## Local setup

Use Python 3.10 or newer in a project-local virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Copy `config_template.json` to the Git-ignored `config.json` and configure an
OpenAI-compatible model endpoint. Do not put credentials into tracked files.

## CLI

```bash
python main.py --help
python main.py challenge create
python main.py challenge list
python main.py solve --manual
python main.py solve --challenge <challenge-id> --manual --no-resume
python main.py tools list
python main.py policy check
python main.py intelligence show
python main.py skill current
python main.py runtime list
python main.py runtime current
python main.py web status
python main.py experiment list
python main.py hypothesis list
python main.py evidence list
python main.py experience list
python main.py experience search sql
```

## Local challenge workbench

R14 adds a concise loopback-only challenge workbench. Build the static frontend
once, then start it from the repository root:

```bash
cd webui/frontend
npm install
npm run build
cd ../..
python main.py ui start
```

Open `http://127.0.0.1:8787` if the browser does not open automatically. The
workbench supports challenge naming, Markdown description, contained
attachments and source files, optional authorized targets, supervised start or
resume, exact user decisions, safe stop, concise outcomes, completion documents,
and reviewed Experience candidates. It intentionally has no live process output,
raw Tool arguments, internal identifiers, artifact-content viewer, or flag
submission.

Use `python main.py ui start --help` to select a different local port or private
workspace roots. The server still binds only to `127.0.0.1`.

As of R9.1, `--auto` selects the constrained `autonomous_local` mode. Only
Tools explicitly marked safe for that mode may run; Bash/Python and public
targets remain denied. In CLI manual or supervised runs, Tool calls classified
as requiring approval retain their detailed terminal review. The local
workbench instead presents a sanitized plain-language action and risk label
while preserving the exact same ApprovalManager decision.

## Validation

```bash
pytest -q
python -m pip check
python -m compileall -q agent cli ctf_platform skill skills utils tests main.py config.py
git diff --check
git status --short
```

Integration tests use fake local tools and temporary directories. They must not
contact network targets or invoke the real Shell backend.

## Project layout

```text
agent/          runtime, execution, domains, workspace, artifacts, intelligence
agent/challenge/  R8.5 manifest intake, workspace bootstrap, run binding
agent/intelligence/experiment/  R6 hypothesis, experiment, and evidence state
agent/experience/  R7 sanitized cross-run JSON memory and rule retrieval
cli/            commands and terminal interaction
ctf_platform/   challenge input and flag submission adapters
webui/          loopback-only R14 Presentation Layer and static frontend
docs/           architecture, cleanup, roadmap, and development guides
prompts/        active structured-output prompts
skill/          skill discovery
skills/         domain skill content
tests/          unit and local-only integration tests
```

Global R7 experience memory defaults to `experiences/global/experience.json`
in the public configuration. R8.5 private challenge records live separately
under `experiences/challenges/`. Both directories are ignored by Git and remain
separate from ordinary per-run checkpoints. Override the global location and
bounded Planner count through `experience.path` and
`experience.max_context_items` in local configuration.

## Platform adapters

Challenge sources implement `QuestionInputer`; flag submission paths implement
`FlagSubmitter`. Register implementations through `ctf_platform.registry` and
keep platform credentials in ignored local configuration. Platform adapters do
not bypass ToolPolicy or expand authorization scope.
