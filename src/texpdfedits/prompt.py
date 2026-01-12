import logging
import argparse
import pymupdf
import json

from texpdfedits.extract import getEdits
from texpdfedits.segmentsource import segment, sourceAsString

from pathlib import Path


BOXES_ORDER_THRESHOLD_BUFF = 6
"""
when a rectangle doesn't intersect any word boxes we look for the word boxes before and after the rectangle.
If the inputted rectangle has y0 Y and a word box has y0 Y+.01 it is still recognized as coming "after" the inputted
rectangle when very often it could actually appear earlier in the line. To mitigate this, we extend the threshold a little, so
for a word box to be considered "after" (or before) its y0 needs to be greater than the inputted rectangle's y0 plus this buffer
(and less than the inputted buffer's y0 minus this buffer). This is used in determining boxes_before and boxes_after.
We may need to eventually find a new and better way to determine word box order if we continue to encounter issues.
"""

def rectangleToLatex(
        pageno: int,
        in_rectangle: pymupdf.Rect,
        document_word_boxes: dict[int, dict[str, pymupdf.Rect]],
        mark_positions: dict[str, tuple[int, int]],
        tex_str: str
) -> str | None:
    r"""
    Args:
        pageno: Zero-indexed page number
        in_rectangle: Rectangle on the page (pymupdf format)
        document_word_boxes: Dictionary from getWordBoxes()
        mark_positions: dictionary mapping mark_id -> (start, end) positions in tex_str 
        tex_str: original unmarked LaTeX source

    Returns: The (unmarked) source LaTeX snippet which "contains" the rectangle.

    Given some rectangle, we find the closest word box before and after that rectangle
    then return all of the LaTeX between (and including) those two word boxes.

    If the inputted rectangle intersects at least one word box, finding the preceding and following word boxes is simple:
    out of the word boxes that intersect, find the one with the smallest id and the one with the largest id, then just use the first
    existing id (because not all \markbox commands make it to the document_work_boxes dictionary) before the smallest and the next existing id
    after the largest.

    If the inputted rectangle doesn't intersect any document_word_boxes, then the "before" box is the one with the largest id whose topline (y0) is less than
    (higher up the page) than the topline of the inputted box, and the "after" box is the one with the smallest id whose topline is greater than the inputted box.
    """

    page_word_boxes = document_word_boxes[pageno]
    intersecting_word_boxes = {k: rect for k, rect in page_word_boxes.items() if in_rectangle.intersects(rect)} 

    def getNumericComponent(k: str) -> int:
        return int(''.join(filter(str.isdigit, k)))

    def getPrevKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)        
        prev_keys = [k for k in all_keys if getNumericComponent(k) < target_num]
        return max(prev_keys, key = getNumericComponent) if prev_keys else None

    def getNextKey(key: str, all_keys: list[str]) -> str | None:
        target_num = getNumericComponent(key)
        next_keys = [k for k in all_keys if getNumericComponent(k) > target_num]
        return min(next_keys, key = getNumericComponent) if next_keys else None        

    all_keys = [k for page_boxes in document_word_boxes.values() for k in page_boxes.keys()]
    
    if intersecting_word_boxes:
        logging.debug(f"Rectangle {in_rectangle} on page {pageno} did intersect word boxes")
        min_key = min(intersecting_word_boxes.keys(), key = getNumericComponent)
        max_key = max(intersecting_word_boxes.keys(), key = getNumericComponent)
        before_key = getPrevKey(min_key, all_keys)
        after_key = getNextKey(max_key, all_keys)
    else:
        # the boxes before and after are on the same page
        logging.debug(f"No word box was intersected by rectangle {in_rectangle} on page {pageno}")
        boxes_before = {k: rect for k, rect in page_word_boxes.items() if rect.y0 < in_rectangle.y0 - BOXES_ORDER_THRESHOLD_BUFF}
        boxes_after = {k: rect for k, rect in page_word_boxes.items() if rect.y0 > in_rectangle.y0 + BOXES_ORDER_THRESHOLD_BUFF}

        # logging.debug(f"boxes before: {boxes_before}\n\n")
        # logging.debug(f"boxes after: {boxes_after}\n\n")        
        
        before_key = max(boxes_before.keys(), key=getNumericComponent) if boxes_before else None
        after_key = min(boxes_after.keys(), key=getNumericComponent) if boxes_after else None

    if before_key is None:
        before_key = max(document_word_boxes[pageno-1].keys(), key=getNumericComponent) if pageno-1 in document_word_boxes else None

    if after_key is None:
        after_key = min(document_word_boxes[pageno+1].keys(), key=getNumericComponent) if pageno+1 in document_word_boxes else None

    if before_key is None or after_key is None:
        # This should only happen if the rectangle is before or after ALL marked boxes in the document.
        # This is a situation where we should check metadata, but I'll have to think more about that in general
        logging.warning(f"Cannot extract LaTeX: Rectangle outside marked boxes (before_key={before_key}, after_key={after_key})")
        return None, None

    logging.debug(f"Before key is {before_key} and after key is {after_key}")

    # NEW
    # the mark_positions.keys() should be a superset of the document_word_boxes.keys()
    # document_word_boxes should only not contain the keys whose individual word boxes were rejected---mark_positions has all of them
    # we could simplify what is above to just take the adjacent key by numeric component (checking if its just the number or preceded by 'm')
    # and this would actually slightly enhance the extraction---it would on average make the snippet smaller, including only what is needed
    # excluding, obviously, the cases where what needs to be edited is very far from the original inputted rectangle (like far down in an enumerate list)
    start_pos = mark_positions[before_key][0]
    end_pos = mark_positions[after_key][1]

    if start_pos > end_pos:
        # this shouldn't happen thanks to BOXES_ORDER_THRESHOLD_BUFF
        logging.warning(f"Cannot extract LaTeX: start_pos = '{start_pos}' > '{end_pos}' = end_pos")
        return None, None
    
    return tex_str[start_pos:end_pos], (start_pos, end_pos)

def markdownReplies(replies: list[str]):
    if not replies:
        return ''
    output = '\n\n## Replies '
    for i in range(len(replies)):
        output += f'\n\n### Reply {i+1}\n```text\n{replies[i]}\n```'
    return output

class Correction:
    """
    Includes all the information I could hope to need to produce and debug the
    individual correction prompts. See asMarkdownPrompt for which pieces actually get
    sent to the LLM. There's certainly room for improvement in the terminology I have so far,
    but right now an "edit" is just the information I get from a PDF annotation.
    A "correction" is that information alongside the corresponding latex_snippet which is required
    to carry out the edit. And a prompt is just the text prompted to the LLM.
    
    Attributes:
    index: the zero-indexed correction number
    
    pageno: the page the correction appears on
    
    type: the annotaiton type of the correction, e.g.,
            "Caret", "Strikeout", "Highlight"
    
    messages: the text written in the annotation comment box and
            any replies to it (which are sorted by date)
    
    pdf_selected_text: the text extracted from the PDF.
            HTML-like focus tags denote exactly which text was
            selected by the annotaiton. Granted, this still fails
            for annotations which select multiple lines of text because the
            required bounding box information is missing

    pdf_selection_line_rect: the rectangle used to select the text
            on that page of the PDF.

    pdf_selection_bbs: the rectangles used to partition the text
            extracted from the pdf_selection_line_rect into
            pieces which are and are not inside the HTML-like
            focus tags. See getSelection in extract.py for more on this
    
    latex_snippet: the latex source which corresponds to the pdf_selected_text.
            See segmentsource.py for more on how this was retrieved
    
    snippet_source_positions: the start and end positions of the latex_snippet
            in the original latex_string. That is, the latex_snippet is
            tex_str[start:end] where tex_str is the source LaTeX as a string
    """
    def __init__(
            self,
            _index: int,
            _pageno: int, 
            _type: str,
            _messages: dict[str, str | list[str]],
            _pdf_selected_text: str,
            _pdf_selection_line_rect: pymupdf.Rect,
            _pdf_selection_bbs: list[pymupdf.Rect],
            _latex_snippet: str,
            _snippet_source_positions: tuple[int, int]
    ) -> None:
        """Using underscores in the argument names isn't necessary, but I like setting the distinction"""
        self.index = _index
        self.pageno = _pageno
        self.type = _type
        self.messages = _messages
        self.pdf_selected_text = _pdf_selected_text
        self.pdf_selection_line_rect = _pdf_selection_line_rect
        self.pdf_selection_bbs = _pdf_selection_bbs
        self.latex_snippet = _latex_snippet
        self.snippet_source_positions = _snippet_source_positions

    def __str__ (self): # the model will not be given json, but I think this format is good for debugging
        return json.dumps({
            "index" : self.index,
            "pageno": self.pageno,
            "type": self.type,
            "messages": {
                "comment": self.messages['comment'],
                "responses": self.messages['responses']
            },
            "PDF selected text": self.pdf_selected_text,
            "PDF selection line rectangle": str(self.pdf_selection_line_rect),
            "LaTeX snippet": self.latex_snippet,
            "Snippet source positions": self.snippet_source_positions
        }, indent=4, ensure_ascii=False)

    def __repr__ (self):
        return str(self)

    def asMarkdownPrompt(self):
        replies = markdownReplies(self.messages['responses'])
        return rf"""## Type
{self.type}

## Comment
```text
{self.messages['comment']}
```{replies}

## PDF selected text
```text
{self.pdf_selected_text}
```
  
## LaTeX snippet
```latex
{self.latex_snippet}
```"""

def getCorrections(annot_filename: str, latex_filename: str) -> list[Correction]:
    edits = getEdits(annot_filename)
    num_marks, marked_tex, unmarked_str, mark_positions, document_word_boxes, all_metadata = segment(latex_filename)

    corrections = []
    for i, edit in enumerate(edits):
        progress = f"{i}/{len(edits)-1}"
        pageno = edit.pageno
        if pageno not in document_word_boxes:
            logging.warning(f"Could not create correction {progress}: Page '{pageno}' not in `document_word_boxes` for edit {edit}")
            continue
        
        pdf_selection_line_rect = edit.selection_line_rect
        latex_snippet, snippet_source_positions = rectangleToLatex(
            pageno,
            pdf_selection_line_rect,
            document_word_boxes,
            mark_positions,
            unmarked_str
        )
        
        if latex_snippet is None:
            logging.warning(f"Could not create correction {progress}: no LaTeX snippet for edit {progress}: {edit}")
            continue

        corrections.append(
            Correction(
                i, pageno, edit.type, edit.message, edit.selection,
                pdf_selection_line_rect, edit.selection_bbs, latex_snippet,
                snippet_source_positions
            )
        )
        logging.info(f"Created correction {progress}")

    logging.info(f"Produced {len(corrections)} corrections from {len(edits)} edit annotations.")                

    return corrections

def groupOverlaps(keyed_start_ends: dict[int, tuple[int]]) -> list[list[int]]:
    """
    I have a list of dictionaries where each dictionary has some key and its value is a tuple with a start and end value, a span
    I want to group together all keys whose start and end values overlap. If there are no such keys then I should return an
    empty list. The keys just happen to be ints in this case, but the ints don't have anything to do with the ordering
    """
    if not keyed_start_ends:
        return []
    
    # sort by starts    
    keys = list(sorted([k for k in keyed_start_ends], key = lambda k: keyed_start_ends[k][0])) 

    groups = []
    current_group = [keys[0]]
    curr_group_end = keyed_start_ends[keys[0]][1]
    for i, k in enumerate(keys):
        if i == 0:
            continue
        start, end = keyed_start_ends[k][0], keyed_start_ends[k][1]
        if start < curr_group_end:
            current_group.append(k)
            curr_group_end = max(curr_group_end, end)
        else:
            if len(current_group) >= 2:
                groups.append(current_group)
            current_group = [k]
            curr_group_end = end
    if len(current_group) >= 2:
        groups.append(current_group)
    return groups

def groupOverlappingCorrections(corrections: list[Correction], tex_filename: str) -> tuple[list[list[int]], list[str]]:
    if not corrections:
        return [], []
    tex_str = sourceAsString(tex_filename)
    keyed_start_ends = {corr.index: corr.snippet_source_positions for corr in corrections}
    groups = groupOverlaps(keyed_start_ends)
    
    snippets = []
    for group in groups:
        spans_in_group = [keyed_start_ends[k] for k in group]
        min_start = min(spans_in_group, key = lambda span: span[0])[0]
        max_end = max(spans_in_group, key = lambda span: span[1])[1]
        snippets.append(tex_str[min_start:max_end])
    
    return groups, snippets

def writeListOfPrompts(corrections: list[Correction], tex_filename: str) -> None:
    prompt_dir = Path('markdown_prompts')
    Path.mkdir(prompt_dir, exist_ok=True)
    
    savefile = f"{prompt_dir / Path(tex_filename).stem}_list_of_prompts.md"

    with open(savefile, 'w') as f:
        f.write('\n\n---\n\n'.join([f"#{corr.index}\n\n" + corr.asMarkdownPrompt() for corr in corrections if corr is not None]))
    logging.info(f"The list of prompts have been written to {savefile}.")
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('annot_filename')
    parser.add_argument('latex_filename')    
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    corrections = getCorrections(args.annot_filename, args.latex_filename)
            
    writeListOfPrompts(corrections, args.latex_filename)

    o_groups, o_snippets = groupOverlappingCorrections(corrections, args.latex_filename)

    # assert len(o_groups) == len(o_snippets)
    
    # for i in range(len(o_groups)):
    #     logging.info(f"Corrections {o_groups[i]} overlap")
    #     logging.info(f"Here's the spanning snippet for these corrections:\n```latex\n{o_snippets[i]}\n```\n")    
