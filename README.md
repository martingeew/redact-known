# redact-known

A small, single-purpose script that sanitises every CSV in a folder before
any of it is shown to an LLM.

It applies two layers of redaction, with one shared mapping file and one
shared set of columns across every file in the folder:

- **Shape-based identifiers** (account number, email, phone, tax ID) are
  found and replaced automatically with regex. The account number and tax
  ID patterns in the script are representative shapes, not universal ones
  - resize the digit counts and separators to match your own bank or
    country, or add another pattern under the same entity type.
- **Name-shaped values** have no predictable pattern, so they come from a
  small local mapping file you fill in yourself (`mapping.json`), which
  never needs to be pasted into any AI conversation.

Placeholders are stable and shared across the whole run: the same real
value always gets the same placeholder in every file it appears in, so a
pattern across months ("this person paid three times") survives.

## Use this as a blueprint, not a copy-paste-exact fit

The account number and tax ID shapes hardcoded here match one specific
bank and one specific country. Yours almost certainly look different. The
easiest way to adapt this script is to hand it to an AI coding assistant
along with an example of your own shapes, and ask it to update the two
patterns:

> Adapt this script for me: [paste the script or this repo's URL]. My
> account numbers look like 123-456-7890, and my tax ID looks like
> 12-3456789. Update the account number and tax ID patterns to match
> those shapes, keep everything else the same.

That way you never have to type your own regex, and you never have to
tell the AI what your actual account number or tax ID is, only its shape.

## Setup

```
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Mac or Linux
pip install pandas
```

## Usage

```
python redact_known.py --input raw/ --output sanitised/ \
    --mapping mapping.json --columns "Payee,Description"
```

- `--input` / `--output`: folders, not single files. Every `*.csv` in
  `--input` gets processed and written to `--output` under the same
  filename.
- `--mapping`: a local JSON file of `{"real value": "placeholder"}`
  pairs, e.g. `{"John Smith": "<PERSON_1>"}`. Optional - if omitted, only
  the regex-based redaction runs.
- `--columns`: comma-separated column names to scan, applied to every
  file in the folder.

Only a **count** of replacements per type is printed to the terminal,
never the matched values themselves, so the output you'd screenshot or
paste anywhere stays safe too.

`raw/march.csv` is a small synthetic fixture (fake names, fake account
number, fake email, fake phone number) you can run the script against to
see it work before pointing it at your own export.
