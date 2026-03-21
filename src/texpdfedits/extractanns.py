import pymupdf
import json
import argparse
import logging
logger = logging.getLogger(__name__)

import math
import re
import sys

import texpdfedits.utils as utils

pymupdf.TOOLS.set_small_glyph_heights(True)

PDF_ANNOT_TEXT = (0, 'Text')

PDF_ANNOT_HIGHLIGHT = (8, 'Highlight')
PDF_ANNOT_UNDERLINE = (9, 'Underline')
PDF_ANNOT_SQUIGGLY = (10, 'Squiggly')
PDF_ANNOT_STRIKE_OUT = (11, 'StrikeOut')

PDF_ANNOT_CARET = (14, 'Caret')
CARET_TAG = '<Caret>'
PDF_ANNOT_INK = (15, 'Ink')

MY_PDF_ANNOT_REPLACE = (28, 'Replace')
MY_PDF_ANNOT_REMOVE = (29, 'Remove')

# how many characters to include on either side of what was selected by an annotation
NUM_SELECTION_CONTEXT_CHARS = 12

# heuristic adjustment of annot rectangle heights (in points) to reduce overlapps
REDUCE_AMMOUNT_ABOVE = 2.5
REDUCE_AMMOUNT_BELOW = 1.5

class Annot:
    """
    Revised version of pymupdf's Annot which fixes the bounding box of the Caret annotation and isn't fragile. See getRobustAnnots().
    
    There's a good chance that there's already something in pymupdf which separates the annot from the page, though, in which case this
    should be removed and the code refactored.
    """
    def __init__ (self, pageno, type, info, xref, irt_xref, rect, vertices): #, _line_bb, _surr_lines):
        self.pageno = pageno        
        self.type = type
        self.info = info                
        self.xref = xref
        self.irt_xref = irt_xref
        self.rect = rect
        self.vertices = vertices
        
    def __str__ (self):
        return str({'pageno':self.pageno, 'type':self.type, 'info':self.info['content'], 'rect':self.rect})
    
    def __repr__ (self):
        return str(
            {'pageno':self.pageno,
             'type':self.type,
             'info':self.info,
             'xref':self.xref,
             'irt_xref':self.irt_xref,
             'rect':self.rect,
             }
        )
    
class Edit:
    """
    Represents the information necessary to carry out an edit. An edit has the following attributes:
    
    "pageno":    page number in the PDF the annotation appears on (won't ultimately be fed to the model)
    
    "type":      annotation type
                 The Edit types are mostly a subset of the Annot types (full list at
                 https://pymupdf.readthedocs.io/en/latest/vars.html#annotationtypes) with the exception
                 of "Replace" which corresponds to the combination of a Strikeout and Caret annotation
                 which are identified by isReplaceAnnot in getEdits(), not by pymupdf. 
    
    "message":   text in the annotation comment box and responses to it---typically edit directions
                 if it's not already self-evident from the type (e.g., Strikeout). The message itself
                 will contain one string for the original comment and a list of strings for the responses
    
    "selection": selected and surrounding text of the annotation from the PDF.

    Example
    {
      "pageno" : 1, 
      "type" : "Replace" 
      "message": {
                   "comment": "Theorem 3.14", 
                   "responses": ["COMP: pls link"]
                 }
      "selection": "We now prove the <Replace>following theorem</Replace>."
    }

    """

    CARET_NAME = 'Caret'
    
    def __init__ (self, pageno, type, message, selection, selection_bbs, annot_rect):
        self.pageno = pageno 
        self.type = type
        self.message = message
        self.selection = selection
        self.selection_bbs = selection_bbs # for debugging
        self.annot_rect = annot_rect # used in marktex routines
        
    def __str__ (self): 
        return json.dumps({
            "pageno": self.pageno, 
            "type": self.type, 
            "message": {
                "comment": self.message['comment'],
                "responses": self.message['responses']
            },
            "PDF text selection": self.selection
        }, indent=4, ensure_ascii=False)
    
    def __repr__ (self):
        return str(self)

def adjustCaretRect(caret_rect: pymupdf.Rect, page):
    """
    The bounding boxes of the original caret annotations often extend below the line they
    were inserted on, so they are resized to prevent that.
    """
    CARET_V_PROPORTION = 0.2
    CARET_H_PROPORTION = 0.2

    (x0, y0, x1, y1) = caret_rect

    # do simple adjustment
    extension = CARET_V_PROPORTION * (y1 - y0)
    caret_rect.y1 = y0 + extension
    caret_rect.y0 = y0 - 0.75 * extension

    # Once the newGetSelectionText is complete, this can be removed
    # reduction = CARET_H_PROPORTION * (x1 - x0)
    # caret_rect.x0 += reduction
    # caret_rect.x1 -= reduction
    
    # check intersecting spans
    raw_dict = page.get_text('rawdict')
    intersecting_spans = []
    for block in raw_dict.get('blocks'):
        for line in block.get('lines'):
            for span in line.get('spans'):
                if caret_rect.intersects(span['bbox']):
                    intersecting_spans.append(span)
    if len(intersecting_spans) != 1:
        SIMPLE_ADJUST = 3 # in points
        # logger.debug("(Adjusted) caret did not intersect exactly one span, continuing with simpler rectangle adjustment")
        return pymupdf.Rect(caret_rect.x0, caret_rect.y0-SIMPLE_ADJUST, caret_rect.x1, caret_rect.y1+SIMPLE_ADJUST)
    # set to span's true font height
    else:
        span = intersecting_spans[0]
        a, d, o = span['ascender'], span['descender'], pymupdf.Point(span['origin'])
        r = pymupdf.Rect(span['bbox'])
        descending_ammt = span['size'] * d / (a - d)
        y1 = o.y - descending_ammt
        y0 = y1 - span['size']
        return pymupdf.Rect(caret_rect.x0, y0, caret_rect.x1, y1)

def getRobustAnnots(doc, **kwargs):
    """
    pymupdf's annotations are kind of fragile---they are strongly bound to the page they
    come from (so when the page goes away, so does the annotation), and I've encountered issues
    with using the provided methods to update the annotations, so I'll just store the
    annotations with my own class which isn't tied to the page.
    """

    # previously, the x positions of the annotations have been accurate, but now I'm encountering annotations from another tool whose
    # left and right x coordinates are significantly wider than the actual selected text. For now I'm trying this very hacky and extremely simple
    # and specific response where I just remove a flat ammount from either side. I need to investigate where this discrepancy comes from, but
    # but this has been working surprisingly well so far.
    # But this hack only works (if therere's a problem to begin with and) if the font is cmr10 (or maybe 11 or 12, I don't recall)
    adjust_annots = kwargs.get('adjust_annots', False)
    HORIZONTAL_REMOVE = 2.75 # in points
    
    robust_annots = {pageno:[] for pageno in range(doc.page_count)}
    for pageno, page in enumerate(doc):
        for annot in page.annots():
            new_ann_rect = pymupdf.Rect(annot.rect.top_left, annot.rect.bottom_right)            
            if annot.type == PDF_ANNOT_TEXT:
                robust_annots[pageno].append(Annot(pageno, annot.type, annot.info, annot.xref, annot.irt_xref, new_ann_rect, annot.vertices))
                continue
            (x0, y0, x1, y1) = new_ann_rect
            
            if annot.type == PDF_ANNOT_CARET:
                new_ann_rect = adjustCaretRect(new_ann_rect, page)
            else:
                new_ann_rect.y0 = y0 + REDUCE_AMMOUNT_ABOVE
                new_ann_rect.y1 = y1 - REDUCE_AMMOUNT_BELOW

                # logging.debug(f"before horizontal hack: {new_ann_rect}")
                if adjust_annots:
                    new_ann_rect.x0 = x0 + HORIZONTAL_REMOVE
                    new_ann_rect.x1 = x1 - HORIZONTAL_REMOVE
                # logging.debug(f"after horizontal hack: {new_ann_rect}")

            robust_annots[pageno].append(
                Annot(pageno,
                      annot.type,
                      annot.info,
                      annot.xref,
                      annot.irt_xref,
                      new_ann_rect,
                      annot.vertices)
            )
    return robust_annots

def getAllResponses(robust_annots):
    """return dictionary where dict[xref] => [annots for which annot.irt_xref == xref]"""
    all_responses = dict()
    for pageno, annots in robust_annots.items():
        for annot in annots: 
            if annot.irt_xref == 0:
                continue
            if annot.irt_xref in all_responses:
                all_responses[annot.irt_xref].append(annot)
            else:
                all_responses[annot.irt_xref] = [annot]
    return all_responses

def getResponses(annot, all_responses):
    """
    return dictionary where dict[type] =>
    [annots for which annot.type == type and are a response to passed annot]
    """
    if annot.xref not in all_responses:
        return []

    resps_by_type = dict()
    for resp in all_responses[annot.xref]:
        if resp.type not in resps_by_type:
            resps_by_type[resp.type] = [resp]
        else:
            resps_by_type[resp.type].append(resp)

    for ann_type, resps in resps_by_type.items():
        # sort responses by creation date
        resps_by_type[ann_type] = sorted(resps, key = lambda r: r.info['creationDate']) 
    
    return resps_by_type

def getMultilineAnnotRects(annot: Annot):
    if annot.type not in {PDF_ANNOT_HIGHLIGHT, PDF_ANNOT_STRIKE_OUT, PDF_ANNOT_SQUIGGLY, PDF_ANNOT_UNDERLINE, MY_PDF_ANNOT_REPLACE, MY_PDF_ANNOT_REMOVE}:
        return None
    if annot.vertices is None:
        return None
    if len(annot.vertices) % 4 != 0:
        logger.warning(f"Multiline annotation vertex count was not a multiple of four for annot type {annot.type}")
        return None
    
    multiline_rects = [pymupdf.Rect(annot.vertices[i], annot.vertices[i+3]) for i in range(0, len(annot.vertices), 4)]

    # validate 
    for rect in multiline_rects:
        if not rect.is_valid:
            logger.warning("Rectangle in multiline annotation proccessing was not valid")
            return None

    return multiline_rects

def getCharCenter(char: dict[str, tuple | str]) -> pymupdf.Point:
    x0, y0, x1, y1 = char['bbox'] 
    return pymupdf.Point(x0 + (x1 - x0)/2, y0 + (y1 - y0)/2)

def AnnotRectsContainChar(annot_rects: list[pymupdf.Rect], char: dict[str, tuple | str]):
    char_center = getCharCenter(char)
    for rect in annot_rects:
        if rect.contains(char_center):
            return True
    return False

def charPosRelativeToCaret(caret_rect: pymupdf.Rect, char: dict[str, tuple | str]):
    """
    Return 0 if char is not in vertical span of caret_rect
    Return 1 if char is in vertical span and is TO THE LEFT  of caret center
    Return 2 if char is in vertical span and is TO THE RIGHT of caret center

    If the caret is at the beginning of a line, there should be a 0 to 2    
    If the caret is in the middle of a line, there should be a 1 to 2
    If the caret is at the end of a line there should be a 1 to 0
    """
    char_center = getCharCenter(char)
    if not (char_center.y >= caret_rect.y0 and char_center.y <= caret_rect.y1):
        return 0
    caret_center_x = get2DCenter(caret_rect)[0]
    return 1 if char_center.x < caret_center_x else 2

def charsIterator(page_rawdict):
    for block in page_rawdict.get('blocks'):
        for line in block.get('lines'):
            for span in line.get('spans'):
                for char in span.get('chars'):
                    yield char

def pointDistance(p1: tuple, p2: tuple):
    return math.hypot(*[a - b for a, b in zip(p1, p2)])

def closestToCaret(caret_rect: pymupdf.Rect, inds_and_chars: list[tuple[int, dict]]):
    caret_center = get2DCenter(caret_rect)
    m = (float('inf'), -1)
    for (idx, char) in inds_and_chars:
        char_center = get2DCenter(pymupdf.Rect(char['bbox']))
        dist = pointDistance(caret_center, char_center)
        if dist < m[0]:
            m = (dist, idx)
    return m[1]

def caretSelectionText(caret_annot, page_rawdict):
    caret_rect = caret_annot.rect
    page_chars = [char for char in charsIterator(page_rawdict)]
    relpos_string = [charPosRelativeToCaret(caret_rect, char) for char in page_chars]
    
    # (idx, char) tuples where idx is left of Caret center and idx+1 is right of Caret center    
    transitions = {'mid-line': [], 'start-line': [], 'end-line': []}

    def addTransition(key, idx):
        transitions[key].append((idx, page_chars[idx]))

    prev = relpos_string[0]                
    in_vertical_span_indices = [0] if prev > 0 else [] # maybe useful to consider in the future
    num_page_chars = len(relpos_string)
    
    for i, trit in enumerate(relpos_string):
        if i == 0:
            continue
        prev_idx = i-1
        if prev == 1 and trit == 2:
            addTransition('mid-line', prev_idx)
        elif prev == 0 and trit == 2:
            addTransition('start-line', prev_idx)
        elif prev == 1 and trit == 0:
            addTransition('end-line', prev_idx)
        # it is inserted at the very end of the page            
        elif prev == 1 and trit == 1 and i == num_page_chars-1:
            addTransition('end-line', i)
        if trit > 0:
            in_vertical_span_indices.append(i)
        prev = trit

    all_transitions = [pair for key in transitions for pair in transitions[key]]
            
    if len(all_transitions) == 0:
        logger.error(f"No caret point detected in {caret_annot}")
        return None
    elif len(all_transitions) > 1:
        logger.debug(f"Multiple insertion indices detected in {caret_annot}")        
        insertion_index = closestToCaret(caret_rect, all_transitions)
    else:
        insertion_index, _ = list(all_transitions)[0]

    # needs rewriting probably
    page_chars_with_synthetic = []
    synthetic_insert_indices = []
    i = 0
    synth_idx = 0
    for block in page_rawdict.get('blocks'):
        page_chars_with_synthetic.append(' ')
        synth_idx += 1
        for line in block.get('lines'):
            page_chars_with_synthetic.append(' ')
            synth_idx += 1
            for span in line.get('spans'):
                for char in span.get('chars'):
                    page_chars_with_synthetic.append(char['c'])
                    if i == insertion_index:
                        page_chars_with_synthetic.append(CARET_TAG)
                        synthetic_insert_indices.append(synth_idx+1)
                        synth_idx += len(CARET_TAG)
                    i += 1
                    synth_idx +=1

    assert len(synthetic_insert_indices) == 1
    first_insertion = min(synthetic_insert_indices)
    last_insertion = max(synthetic_insert_indices)

    start_with_context = first_insertion - NUM_SELECTION_CONTEXT_CHARS
    end_with_context = last_insertion + NUM_SELECTION_CONTEXT_CHARS
    
    start_char_idx = start_with_context if start_with_context >= 0 else first_insertion

    # string [:] retrieval will only ever go as high as it can, there's no issue with giving an upper index out of range
    return ''.join(page_chars_with_synthetic[start_char_idx:end_with_context+1])
    
    
def newGetSelectionText(annot: Annot, page_rawdict, page_words):
    """
    We iterate through the characters on the page and check if it's center (origin) is
    inside of the annotation.

    So we have two states 0 = outside annotation rectangle and 1 = inside annotation rectangle, so iterating through the characters
    gives us binary string. The sequence 01 (with, say, characters ab) corresponds to the start of the tag at a(b and the sequence
    10 corresponds to the closing tag a)b so
    010 would make
        a(b)c,
    and 0 1111 0 1 00 1 0 would make
        a(bcde)f(g)hi(j)k

    For noncaret annotations, everything before the first origin inside is before the annotation, and the first
    character whose origin is inside it will mark (just before the character) the start of the annotation tag
    and then each character 
    If the annotation is a caret, we track it's center and when we hit a character which intersects it
    """
    if annot.type == PDF_ANNOT_CARET:
        return caretSelectionText(annot, page_rawdict)
    
    intersecting_words = [word for word in page_words if annot.rect.intersects(pymupdf.Rect(word[0:4]))]
    line_nos = set(iw[6] for iw in intersecting_words)
    if len(line_nos) > 1:
        annot_rects = getMultilineAnnotRects(annot)
    else:
        annot_rects = [annot.rect]

def get2DCenter(rect):
    return (rect.x0 + rect.width / 2, rect.y0 + rect.height/2)

def getSelection(annot: Annot, page_words: list[tuple[int, int, int, int, str, int, int, int]], doc: pymupdf.Document):
    """
    Return: annotation's selected text, rectangle for latex source extraction,
    and selection bounding boxes for debugging

    page_words is list of (x0, y0, x1, y1, "word", block_no, line_no, word_no) tuples
    
    word[0] = x0
    word[1] = y0
    word[2] = x1
    word[3] = y1
    word[4] = pdf text
    word[5] = block_no
    word[6] = line_no
    word[7] = word_no
    """
    page = doc[annot.pageno]
    intersecting_words = []

    # <<< 0.10.1
    # ===============================
    if annot.type == PDF_ANNOT_CARET:
        caret_rect = annot.rect
        caret_center_x = get2DCenter(caret_rect)[0]
        sel_bbs = [[pymupdf.Rect(caret_center_x, caret_rect.y0, caret_center_x+.5, caret_rect.y1), pymupdf.Rect(0,0,.1,.1)]]
        return newGetSelectionText(annot, page.get_text('rawdict',sort=True), page_words), sel_bbs, annot.rect
    # >>> 0.11.0
    
    for word in page_words:
        word_rect = pymupdf.Rect(word[0:4])
        word_intersects = annot.rect.intersects(word_rect)
        if not word_intersects:
            continue
        intersecting_words.append(word)

    # <<< 0.10.1
    # if not intersecting_words:
    #     logger.warning(
    #         f"No selection text for {annot}: "
    #         "ann rectangle did not intersect ANY PDF word boxes"
    #     )
    #     return None, None, None
    # ===============================
    # often it is useful to include an annotation which doesn't intersect any text
    # e.g., 'adjust to fit' and pencil marks---at least I get pointed to somewhere in the source
    if not intersecting_words:
        message = f'None, annot.type = <{annot.type[1]}>'
        return message, None, annot.rect
    # >>> 0.11.0
        

    CARET_X_BUFF = 1 # in points
    OTHER_ANN_X_BUFF = .75 # in points

    NUM_CONTEXT_WORDS = 2 # words to add before and after which are not selected    
    first_sel_word = intersecting_words[0]
    last_sel_word = intersecting_words[-1]

    # logger.debug(
    #     f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
    #     f"intersecting_words: {intersecting_words}"
    # )

    # logger.debug(
    #     f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
    #     f"first_sel_word: {first_sel_word}\nlast_sel_word: {last_sel_word}"
    # )

    intersecting_words = {word : '' for word in intersecting_words} # make dict for fast lookup later

    start_word_idx = max(0, page_words.index(first_sel_word) - NUM_CONTEXT_WORDS)
    end_word_idx = min(len(page_words)-1, page_words.index(last_sel_word) + NUM_CONTEXT_WORDS)

    # logger.debug(
    #     f"annot page {annot.pageno} with content '{annot.info['content']}':\n"
    #     f"start_word: {page_words[start_word_idx]}\nend_word: {page_words[end_word_idx]}"
    # )    

    selection_name = annot.type[1]
    selection_bbs = []

    DIFF_THRESH = 1 # in points

    def wordsToStr(word_selection):
        return ' '.join([word[4] for word in word_selection])

    def insideAnnotRect(word_box):
        """ only call on words which intersect annot """
        left_diff = abs(annot.rect.x0 - word_box.x0)
        right_diff = abs(annot.rect.x1 - word_box.x1)
        
        return annot.rect.x0 < word_box.x0 and left_diff > DIFF_THRESH and word_box.x1 < annot.rect.x1 and right_diff > DIFF_THRESH

    def getCaretSelection(word_box):
        """word_box intersects the annot rectangle, but it is not "inside" it according to insideAnnotRect"""        
        x0 = annot.rect.x0 if annot.rect.x0 <= word_box.x0 else word_box.x0
        insertion_x = annot.rect.x0 + annot.rect.width / 2
        x1 = annot.rect.x1 if word_box.x1 <= annot.rect.x1 else word_box.x1

        y0, y1 = annot.rect.y0, annot.rect.y1
        left_rect = pymupdf.Rect(x0, y0, insertion_x - CARET_X_BUFF, y1)
        right_rect = pymupdf.Rect(insertion_x + CARET_X_BUFF, y0, x1, y1,)

        selection_bbs.append([left_rect, right_rect])

        left = wordsToStr(page.get_text('words', clip=left_rect, sort=True))
        right = wordsToStr(page.get_text('words', clip=right_rect, sort=True))
        return f"{left}<{Edit.CARET_NAME}>{right}"

    def getOtherSelection(word_box):
        """
        word_box intersects the annot rectangle, but it is not
        "inside" it according to insideAnnotRect---it is on the annotation "boundary"
        """        
        tag_insertion_xs = {'start': None, 'end': None}
        a_rect = annot.rect

        x0_diff = abs(a_rect.x0 - word_box.x0)
        x1_diff = abs(a_rect.x1 - word_box.x1)

        if (word_box.x0 <= a_rect.x0 or x0_diff < DIFF_THRESH)  and a_rect.x0 < word_box.x1:
            tag_insertion_xs['start'] = a_rect.x0
        if word_box.x0 < a_rect.x1 and (a_rect.x1 <= word_box.x1 or x1_diff < DIFF_THRESH):
            tag_insertion_xs['end'] = a_rect.x1

        y0, y1 = a_rect.y0, a_rect.y1
        
        if tag_insertion_xs['start'] is not None and tag_insertion_xs['end'] is None:
            left_rect  = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['start'] - OTHER_ANN_X_BUFF, y1)
            right_rect = pymupdf.Rect(tag_insertion_xs['start'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, right_rect])

            left  = wordsToStr(page.get_text('words', clip=left_rect, sort=True)) if left_rect.is_valid else ''    
            right = wordsToStr(page.get_text('words', clip=right_rect, sort=True))
            return f"{left}<{selection_name}>{right}"
            
        elif tag_insertion_xs['end'] is not None and tag_insertion_xs['start'] is None:
            left_rect  = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['end'] - OTHER_ANN_X_BUFF, y1)
            right_rect = pymupdf.Rect(tag_insertion_xs['end'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, right_rect])
            
            left  = wordsToStr(page.get_text('words', clip=left_rect, sort=True))
            right = wordsToStr(page.get_text('words', clip=right_rect, sort=True)) if right_rect.is_valid else ''                
            return f"{left}</{selection_name}>{right}"
            
        elif tag_insertion_xs['start'] is not None and tag_insertion_xs['end'] is not None:
            left_rect   = pymupdf.Rect(word_box.x0, y0, tag_insertion_xs['start'] - OTHER_ANN_X_BUFF, y1)
            middle_rect = pymupdf.Rect(tag_insertion_xs['start']+OTHER_ANN_X_BUFF, y0, tag_insertion_xs['end']-OTHER_ANN_X_BUFF, y1)
            right_rect  = pymupdf.Rect(tag_insertion_xs['end'] + OTHER_ANN_X_BUFF, y0, word_box.x1, y1)

            selection_bbs.append([left_rect, middle_rect, right_rect])

            left   = wordsToStr(page.get_text('words', clip=left_rect, sort=True)) if left_rect.is_valid else ''
            middle = wordsToStr(page.get_text('words', clip=middle_rect, sort=True))
            right  = wordsToStr(page.get_text('words', clip=right_rect, sort=True)) if right_rect.is_valid else ''
            return f"{left}<{selection_name}>{middle}</{selection_name}>{right}"

        else:
            logger.warning(
                f"Could not produce selection text for annot {annot}: "
                "There was neither a start or end boundary of the annotation on the word box"
            )
            return None

    def wordDistance(w1: tuple[int, int, int, int, str, int, int, int], w2) -> float:
        rect1 = pymupdf.Rect(w1[0:4])
        rect2 = pymupdf.Rect(w2[0:4])
        c_1 = get2DCenter(rect1)
        c_2 = get2DCenter(rect2)
        return pointDistance(c_1, c_2)

    MAX_WORD_DISTANCE_IF_DIFF_BLOCK = 24 # in points
            
    selected_text = []
    caret_inserted = False
    for idx in range(start_word_idx, end_word_idx + 1):
        word = page_words[idx]
        word_box = pymupdf.Rect(word[0:4])
        word_str = word[4]
        if word not in intersecting_words:
            # logger.debug(f"word '{word_str}' in {annot} doesn't intersect annot Rect")
            word_block_no = word[5]
            if word_block_no == first_sel_word[5] or wordDistance(word, first_sel_word) < MAX_WORD_DISTANCE_IF_DIFF_BLOCK:
                selected_text.append(word_str)
            continue

        if insideAnnotRect(word_box):
            # logger.debug(f"word '{word_str}' with box '{word_box}' in {annot} inside annot Rect")
            selected_text.append(word_str)
            continue
        
        if annot.type == PDF_ANNOT_CARET:
            if caret_inserted:
                continue
            selected_text.append(getCaretSelection(word_box))
            caret_inserted = True
        else:
            res = getOtherSelection(word_box)
            if res is None:
                return None, None, None
            selected_text.append(res)
    # logger.debug(f"selected_text for {annot} is {selected_text}")
    return ' '.join(selected_text), selection_bbs, annot.rect
    

def isNotForCOMP(message: dict[str, str | list[str]]) -> bool:
    head_comment = message['comment']
    responses = message['responses']
    first_response = responses[0] if responses else ''

    not_for_comp = r"\b(?:AU|PE|PTG|GA)\b:?"
    for_comp = r"\b(?:COMP|TEG)\b:?"

    if re.search(not_for_comp, head_comment, re.IGNORECASE) is not None:
        if re.search(for_comp, first_response, re.IGNORECASE) is not None:
            return False
        else:
            return True
    else:
        return False

def getEdits(filename, **kwargs):
    """return a list of Edits. See class Edit."""
    logger.info("Loading PDF annotations...")
    doc = pymupdf.open(filename)
    robust_annots = getRobustAnnots(doc, **kwargs)
    all_responses = getAllResponses(robust_annots)
    logger.info("Done.")

    target_num_edits = 0
    logger.info("Turning annotations into edits...")
    num_not_for_comp = 0
    edits = []

    num_pages_with_annots_to_extract = len([pageno for pageno, _ in enumerate(doc) if robust_annots[pageno]])

    bar = utils.TextProgressBar(num_pages_with_annots_to_extract)
    bar.showSize()
    
    for pageno, page in enumerate(doc):
        for annot in robust_annots[pageno]:
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine with another to make an annotation of type 'Replace'
                continue
            target_num_edits += 1
            
            responses = getResponses(annot, all_responses)
            text_responses = responses[PDF_ANNOT_TEXT] if PDF_ANNOT_TEXT in responses else []
            text_responses = [resp.info['content'] for resp in text_responses]
            message = {'comment': annot.info['content'], 'responses': text_responses}

            # skip annots whose comment text starts with AU:, PE:, or PTG: among other things, unless the first response has COMP: or TEG:
            if isNotForCOMP(message):
                logger.debug(f"Annot {annot} deemed not for COMP")
                num_not_for_comp += 1
                continue

            def isReplaceAnnot(ann, ann_resps):
                if not (ann.type == PDF_ANNOT_STRIKE_OUT or ann.type == PDF_ANNOT_CARET) or ann_resps == []:
                    return False, None
                
                assert ann.type not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = PDF_ANNOT_STRIKE_OUT if ann.type == PDF_ANNOT_CARET else PDF_ANNOT_CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False, None
                other_ann = ann_resps[other_ann_type][0]

                if not (ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == ''):
                    return False, None
                return True, other_ann
                
            is_replace, other_ann = isReplaceAnnot(annot, responses)
            
            if is_replace:
                if annot.type == PDF_ANNOT_CARET:
                    annot.rect = other_ann.rect
                    annot.vertices = other_ann.vertices
                annot.type = MY_PDF_ANNOT_REPLACE

            # rename strikeout to remove
            if annot.type == PDF_ANNOT_STRIKE_OUT:
                annot.type = MY_PDF_ANNOT_REMOVE

            page_words = page.get_text('words', sort=True)    
            # the sort option doesn't actually sort in lexicographic order... maybe it does it by rectangle positions.
            page_words = list(sorted(page_words, key = lambda w: (w[5], w[6], w[7])))
            
            selection_text, selection_bbs, latex_extraction_bb = getSelection(annot, page_words, doc)
            if selection_text is None:
                continue
            
            edits.append(Edit(annot.pageno, annot.type[1], message, selection_text, selection_bbs, latex_extraction_bb))

        if robust_annots[pageno]:
            bar.addProgress()
    bar.end()
        
    logger.info(f"Created {len(edits)} edits from {target_num_edits} PDF annotations")
    logger.info(f"Ignored {num_not_for_comp} annotation(s) deemed not for COMP")
    return edits
            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python extract.py',
                                     description = 'Return edits from annotated pdf as json')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    parser.add_argument("-pe", "--print-edits", action="store_true", help='print edits at the end')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    edits = getEdits(filename)    

    if args.print_edits:
        for edit in edits:
            print(edit)
