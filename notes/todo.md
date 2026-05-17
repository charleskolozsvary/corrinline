# TO DO 
## High priority
- Fix/revert no intersected TeX word box fall back sorting
- use SyncTeX instead of my marking procedure
- write correction number per page number
- try to get correct marking and mapping for `amsrefs` `\bib` bibliography items (`\bibitems` appear to be no issue---another reason to use SyncTeX)

## Medium priority
- limit selection text (sometimes it can be very long for large Ink annotations, for example)
- `--no-validate` option to not end `corrinline` even if a marked page differs by more than 50000 pixels
- `--pdf-start` analogue of `--tex-start`

## Low priority
- refactor marking 
- Identify and simplify contiguous selections like `%% Selection: "numerical value<Highlight>, e.g.</Highlight> <Highlight>ℏ=</Highlight> <Highlight>1,</Highlight> and the"` into `%% Selection: "numerical value<Highlight>, e.g. ℏ= 1,</Highlight> and the"`
- rewrite code to PEP standard, trying to get as close to idiomatic Python as possible







