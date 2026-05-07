# Option usage

TO DO

## `--grp-overlap`, `--no-grp-overlap`

## `--auto`

## `--adjust-annots`

## `--delete-comments`

## `--compiler COMPILER`

## `--extra-mark-envs EXTRA_MARK_ENVS`

## `--comment-format COMMENT_FORMAT`

## `--source-start-page SOURCE_START_PAGE`
If there isn't a one-to-one correspondence between the annotated PDF and what the `.tex` file outputs, typically `corrinline` won't work. However, if the source matches up with the annotated PDF starting at a particular page, then the documents can successfully sync if this option is provided correctly.

Suppose the first page of an annotated PDF corresponds to what is marked as page 71 by the LaTeX source. Then simply run
```shell
corrinline --source-start-page=71 ANNOTATED_PDF_FILE LATEX_FILE
```
and the annotations should insert as expected into the source.

It is worth emphasizing that the value you supply to `--source-start-page` is the page number *rendered* by the source, not the absolute page number.

This means for the time being there is also the unfortunate downside that numbers marked with roman numerals are ignored, and so if there is *already* a one-to-one correspondence between the source and annotated PDF but the source generates roman numerals for the front matter, then the script would not work either. But this does not mean version 0.14.0 (which provided this option) introduces a regression with such a case. Before, the page number was written from `\the\value{page}`, which doesn't distinguish between roman numeral and decimal page numbers, so the syncing behavior was silently bugged in this case anyway.
