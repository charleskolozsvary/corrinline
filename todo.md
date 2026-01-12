In roughly decreasing priority:

# Identify overlapping corrections
Do this with the output of getCorrections in `prompt.py`

For now we'll just flag these and set them aside

# Send prompts to LLM and retreive repsponses
I need to extract the desired information from the responses.
* check that there's only one markdown codeblock
* try to check leading or trailing whitespace

Overwrite original snippets with edited ones.

I can make a no-change response which just returns something like
```
```latex
<original snippet>
```
This is a dummy response.
```

For testing the response extraction

In the case of corrections which overlap, find the start:end span which contains all the overlapping snippets and change each snippet to the entire start:end span and then make sure to put the overlapping edits in sequence, replacing the subsequent one's snippet with the just edited snippet.

# Flag AU: and PE: directed corrections
Do this at the getCorrections level

