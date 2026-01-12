from texpdfedits.segmentsource import segment, getWordBoxes, sourceAsString, writeStringToFile
import logging
import argparse
import pymupdf

import os
from pathlib import Path

def validateSegmentOutput(filename):
    segment_output = segment(filename)

def test_unMarkWithPositions(tex_str, unmarked_str, filename):

    unmarked_filename = f"{Path('tmp_segmentsource') / Path(filename).stem}_unmarked.tex"
    writeStringToFile(unmarked_str, unmarked_filename)

    os.system(f"diff {filename} {unmarked_filename}")

    assert unmarked_str == tex_str

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    tex_str = sourceAsString(Path(args.filename))

    num_marks, marked_tex, unmarked_tex, mark_positions, document_word_boxes, all_metadata = segment(args.filename)

    test_unMarkWithPositions(tex_str, unmarked_tex, args.filename)
