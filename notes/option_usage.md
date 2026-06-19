# Option usage

TO DO

## `--grp-overlap`, `--no-grp-overlap`

## `--auto`, `-a`

## `--adjust-annots`

## `-dc`, `--delete-comments`

## `--compiler COMPILER`

## `-eme`, `--extra-mark-envs EXTRA_MARK_ENVS`

## `-cf`, `--comment-format COMMENT_FORMAT`

## `-ts`, `--tex-start TEX_START`
If there isn't a one-to-one correspondence between the annotated PDF and what the `.tex` file outputs, typically `annin` won't work. However, if the PDF the source renders matches up with the annotated PDF starting at a particular page, then `annin` can successfully map PDF coordinates LaTeX source positions if this option is provided correctly. 

Suppose the first page of an annotated PDF corresponds to what is **marked** as the 71st page of the PDF rendered by the LaTeX source. Then
```shell
annin --tex-start=71 pdf_file latex_file
```
will treat the 71st page of the PDF outputted by the LaTeX file as the first page of the annotated PDF, and the annotations will be inlined correctly.

It is worth emphasizing that the value you supply to `--tex-start` is the page number *rendered* by the source, not the absolute page number.
