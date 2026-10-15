---
name: sign-pdf
description: Sign a PDF or form on Jason's behalf with his signature image (Hoelscher-Obermaier or Schreiber), optionally stamping place, date or name, and verify the placement visually. Use whenever Jason asks to sign, unterschreiben or countersign a document, put his Unterschrift on a contract, declaration or form, or produce a `_signed.pdf`. Not for digital certificates (qualified e-signatures, ID Austria, DocuSign flows).
---

# Sign a PDF

The setup lives in `~/Projects/ops/signing/`: `README.md` (workflow and rules), `sign_pdf.py` (executable uv script for inspection, preview, signing and rendering) and the two signature PNGs. This skill is only the entry point; all rules live in the README and are maintained there.

1. Read `~/Projects/ops/signing/README.md` in full before touching the document. If the folder or the script is missing on this host, say so and stop; do not recreate signature images or write substitute image code.
2. Follow it exactly, including its rules on which signature to use, empty name/place/date fields, fillable or rotated pages, .docx inputs, and verifying the check PNG and a full-page render before reporting done.
3. Never send or upload the signed file; delivery is Jason's.
