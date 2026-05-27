import logging
logger = logging.getLogger(__name__)

import re
from pathlib import Path
import texpdfedits.utils as utils
import argparse
from icecream import ic

MAYBE_BREAK = '<potential_newline_8543231235932>' # make sure this never matches original text
BREAK_FREQUENCY = 2
MODIFICATION_TAG = 'reflowed'
LINE_LEN_THRESH = 84

# a better approach might be to read each line, try to parse it with pylatexenc
# if you can, break it up using it across inline math or char nodes
# according to whitespace

def _choose_breaks(broken_line: str, frequency: int = BREAK_FREQUENCY) -> str:
    """
    Only make some of the matched breaks newlines according to frequency.
    
    If frequency is 1, we make them all newlines, if it is two,
    only every other one, and so on.
    """
    pieces = broken_line.split(MAYBE_BREAK)
    result = []
    num_breaks = 0
    for i, piece in enumerate(pieces):
        # since no split after last element
        if i == len(pieces)-1:
            result.append(piece)
            continue
        if i % frequency == 0:
            result.append(piece + '\n')
            num_breaks += 1
        else:
            # we can join with just ' ' from
            # arbitrary \s+ match because
            # the original match was 
            # restricted to a single line
            result.append(piece + ' ')
    return ''.join(result), num_breaks   

def reflow_lines(width: int, text_file: Path) -> Path:
    """
    Try to break up lines longer than width
    return a path to the modified version of the file
    """
    with open(text_file, 'r') as f:
        lines = f.readlines()
    result = []
    tot_breaks = 0
    for line in lines:
        # would be better to split line at first column and only try to reflow
        # what comes before that first comment on the line
        line_short_or_has_comment = (
            len(line) < width
            or re.search(r'[^\\]%|^%', line) is not None
        )
        if line_short_or_has_comment:
            result.append(line)
            continue

        viable_break = r'(\s+[a-z]+)\s+([a-z]+\s+)'
        broken_line, _ = re.subn(
            viable_break,
            rf'\1{MAYBE_BREAK}\2',
            line,
            flags=re.IGNORECASE,
        )
        broken_line, num_breaks = _choose_breaks(broken_line)
        tot_breaks += num_breaks
        result.append(broken_line)
        
    reflowed_file = utils.new_tagged_fname(text_file, MODIFICATION_TAG)
    with open(reflowed_file, 'w') as f:
        for line in result:
            f.write(line)
    return reflowed_file, tot_breaks

def main():
    
    logging.basicConfig(
        encoding='utf-8',
        level=logging.INFO,
        format='%(levelname)-8s | %(module)-11s | %(message)s',
    )
    
    argparser = argparse.ArgumentParser()
    argparser.add_argument('text_file')

    args = argparser.parse_args()
    text_file = Path(args.text_file)
    result, tot_breaks = reflow_lines(LINE_LEN_THRESH, text_file)
    print(f"Inserted {tot_breaks} line breaks: modified {text_file} written to {result}")

    if text_file.suffix == '.tex':
        ic(text_file, result)
        utils.compile_validate_clean(text_file, result, compiler='prdlatex')

if __name__ == '__main__':
    main()
    
