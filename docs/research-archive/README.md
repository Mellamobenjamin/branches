# Private research archive

The research archive stores document originals and working research artifacts.
It is separate from the public website and is excluded from Git.

## Local structure

Run `python tools/init_research_archive.py` to create:

```text
data/research_archive/
  inbox/         newly acquired, not yet accessioned
  originals/     unchanged source files
  derivatives/   crops, display copies, and OCR-ready versions
  transcripts/   transcriptions and OCR corrections
  exports/       temporary research packets and handoffs
```

Maintain an encrypted backup outside the repository. Git is not the backup for
these materials.

## Accession workflow

1. Place a new file in `inbox/` without altering it.
2. Assign the next artifact ID: `ARC-YYYY-NNNN`.
3. Calculate its SHA-256 checksum and record its acquisition metadata.
4. Move the unchanged file beneath `originals/<artifact-id>/`.
5. Record the people, events, places, and claims to which it relates.
6. Put OCR, crops, and resized copies in the corresponding derivative folders;
   never overwrite the original.
7. Set rights and access fields before considering public display.

Use `artifact-metadata-template.yaml` as the current metadata contract. The
canonical database will later store the same fields and relationships.

## Rights defaults

An item downloaded from Ancestry defaults to:

```yaml
access_level: private
rights_status: ancestry-research-copy
public_display: false
```

The public site may expose a citation and link to the Ancestry record, but should
not publish the downloaded image by default. Public display requires one of:

- the family owns the item;
- the rights holder has granted permission;
- an independently acquired copy has terms allowing display;
- the item has been confirmed public domain; or
- Ancestry has provided applicable written permission.

Living-person records, DNA information, private messages, and material supplied
by another user remain private unless explicit permission and the necessary
consent have been recorded.

## Audience levels

- `private`: editors only; the default for new acquisitions.
- `family`: reserved for a future authenticated family area.
- `public-citation`: metadata and an external link may be shown, not the file.
- `public-display`: the approved derivative may be displayed publicly.

Changing an audience level is an editorial decision. It must never be inferred
only from where a file was downloaded.
