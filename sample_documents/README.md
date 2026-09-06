# Sample protected documents

Ten fictional client and customer records for testing the Knowledge Shield.

**All of it is invented** — the people, companies, identifiers and card numbers
do not exist and belong to no one. The card numbers are Luhn-valid on purpose:
`entities.py` rejects digit runs that fail the checksum, so placeholder digits
would never be indexed and a test built on them would quietly prove nothing.

## What they're for

Upload them through **Knowledge Shield → Add Document** (admin only) to get a
populated index, then submit prompts and watch what gets caught. They are also
the fixtures behind `backend/tests/test_document_upload.py`, so regenerating
them badly will fail the suite rather than silently weakening detection.

The same content is seeded automatically by `python -m seed_data.seed` — these
files exist so the *upload* path can be exercised by hand, not just the seed.

## Formats

One file per supported upload type, so every parser has a fixture:

| Format | Files | Exercises |
|--------|-------|-----------|
| `.pdf` | 7 | `pypdf` extraction |
| `.docx` | 1 | `python-docx`, including table cells |
| `.csv` | 1 | plain-text path, exported client tables |
| `.md` | 1 | plain-text path |

## What each one is dense with

| Document | Entities it contributes |
|----------|------------------------|
| Client Master Record — Northwind Retail | contract no., account no., emails, phones, dates, ACV |
| Employee File — Priya Raghavan | SSN, DOB, employee ID, salary, IBAN |
| Patient Health Record — PT-88231 | SSN, DOB, patient/member/claim IDs, admission dates |
| Customer Payment Instruments | 5 Luhn-valid cards, settlement IBAN |
| Vendor Master Agreement — Kestrel | agreement no., PO no., committed spend, term dates |
| Insurance Policy Schedule | policy no., claim no., premium, deductible |
| Mortgage Origination File | two SSNs, loan ref, deposit account, closing date |
| Production Credentials Inventory | OpenAI, AWS, GitHub and Slack tokens |
| Project Bluefin — Acquisition Memo | offer size, exclusivity and signing dates |
| Customer Support Escalation Log | three case numbers, customer emails and phones |

Names and identifiers deliberately recur across documents — Dana Reyes appears
in the client record, the payment vault and the escalation log — so
cross-document matching is testable, not just single-document hits.

## Prompts worth trying

Should be caught:

- `Validate SSN 492-83-7291 for payroll`
- `ssn 205 71 6634 — is this borrower approved?` (reformatted; still matches)
- `Charge card 4532 5260 1815 9080 for the renewal`
- `Summarise contract NW-2024-8871 for the board`
- `What is claim CLM-99823 reserved at?`

Should **not** be caught — these are the false positives the two-signal split
exists to avoid:

- `What is a good annual salary for a staff engineer?`
- `Is the office open on 2024-03-01?` (one shared date is coincidence)
- `How do I write a mortgage pre-approval email template?`
