## DISCLAIMER: it's possible that it's much easier to track the box positions of words with lualatex
## than pdflatex with pylatexenc, but this appears to be working well enough as-is

import argparse
import logging
import re

## simple TeX parser >>>
from TexSoup import TexSoup
## <<<

from pylatexenc.latexwalker import LatexWalker, LatexNode, LatexMacroNode, LatexEnvironmentNode, LatexGroupNode, LatexMathNode, LatexCharsNode, LatexCommentNode
from pylatexenc.macrospec import LatexContextDb, std_macro, std_environment

from itertools import count
from pathlib import Path

import sys
import os
import subprocess

from collections.abc import Callable

RECOGNIZED_CSNAMES = {'emph': '{',
                      'textit': '{',
                      'textbf': '{',
                      'textsc': '{',
                      'texttt': '{',
                      'underline': '{',
                      'part': '*[{',
                      'chapter' : '*[{',
                      'section': '*[{',
                      'subsection': '*[{',
                      'subsubsection': '*[{',
                      'thanks': '{',
                      'subjclass': '[{',
                      'datereceived': '{',
                      'daterevised': '{',
                      'commby': '{',
                      'title': '[{',
                      'author': '[{',
                      'address': '[{',
                      'email': '[{',
                      'footnote': '[{', # \footnote[10]{text} sets the footnote to be footnote 10---only a number can be passed
                      'caption': '[{',
                      'item': '[',
                      'renewcommand': '*{[{',
                      'newcommand': '*{[{',
                      'theoremstyle' : '{',
                      'newtheorem': '*{[{['}
"""greedily read all possible arguments to newtheorem,
   even if optional is not quite right, but that's okay"""

OPTIONAL_ARG = ('[', ']')

REQUIRED_ARG = ('{', '}')

MARK_CSNAMES = {'emph', 'textit', 'textbf', 'textsc', 'underline', 'texttt'}

MARK_IDENTIFIERS = {'inline math': 'm',
                    'inside footnote': 'f'} ## may expand upon this >>> yes: match mark key as <letter(s) identifier><digits>

TRACKED_ENVIRONMENTS = {'abstract', 'figure', 'table', 'thebibliography', 'biblist'}

METADATA_CSNAMES = {'title', 'author', 'address', 'email', 'thanks', 'subjclass', 'keywords', 'datereceived', 'daterevised', 'commby'}

UNIQUE_FIELDS = {'title', 'subjclass', 'keywords', 'datereceived', 'commby', 'abstract'}

ALLOWED_MARK_ENVIRONMENTS = {'proof', 'enumerate', 'itemize', 'document', 'thebibliography', 'biblist', 'bibdiv', 'bibsec'}

DIFFPDF_DPI = 175
r"""
so far it appears for some reason \eqrefs produce very small differences in
the PDF output when the \markboxes are inserted
(but from what I can tell nothing else causes differences)

If there are 93 eqrefs on a page less than 50_000 pixels are marxed different
(when using DPI = 175; the larger the DPI, the larger the number of pixel differences)
And if a page breaks early by just one line the difference on that and subsequent pages is at
least 275_000
(based on from `diff-pdf teichmuller.pdf breakteich.pdf -v -s -m -g --output-diff=diff_break.pdf --dpi=175`),
so I think marking a page as not different if it differs by less than 50_000 pixels at this DPI is quite conservative.
"""
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 100_000

SCALED_POINTS_PER_TEX_POINT = 2 ** 16 # 65536

"""
there are 72.27 tex pts in an inch, while there are 
72 bp (what tex calls a big point) in an inch, which is what
pymupdf and other modern pdf systems use
"""
TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO = 72 / 72.27

"""
allow for half a point discrepancy between x0 + width and x1
in boxinfoToPDFRectangle()
"""
WORD_BOX_WIDTH_TOLERANCE = 10

def sourceAsString(filename: Path) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def writeStringToFile(string: str, filename: Path):
    with open(filename, 'w', encoding = 'utf-8') as f:
        f.write(string)
    return 0

def joinLatexVerbatimNodes(nodelist, start: int, end: int):
    return ''.join([node.latex_verbatim() for node in nodelist[start:end+1]])

def getEnunciations(preamble_nodes) -> tuple[list[str], str]:
    enunciation_names = set()
    start_idx, end_idx = -1, -1
    for i, node in enumerate(preamble_nodes):
        if node.isNodeType(LatexMacroNode) and node.macroname in {'theoremstyle', 'newtheorem'}:
            if start_idx < 0:
                start_idx = i
            end_idx = i
            if node.macroname == 'theoremstyle':
                continue
            ## otherwise try to process \newtheorem
            node_args = node.nodeargd.argnlist
            len_arg_spec = len(RECOGNIZED_CSNAMES[node.macroname])
            if len(node_args) == len_arg_spec and len_arg_spec > 1:
                arg_one = node_args[1]
                try:
                    enunciation_names.add(arg_one.nodelist[0].chars)
                except Exception as e: ## currently would fail with \\newtheorem{%\nthm}{Theorem}, which I think is fine for now
                    logging.warning(f"""! Attempting to extract the second argument of
                    '{node.latex_verbatim()}' raised Exception {e};
                    it's node.nodeargs[1] was {arg_one}; ignoring""")
            else:
                logging.warning(f"""! Malformed {node.macroname},
                '{node.latex_verbatim()}', did not match it's argument specification:
                {RECOGNIZED_CSNAMES[node.macroname]}""")
    if start_idx < 0:
        logging.warning("! No enunciations (newtheorem commands) found; continuing without them.")
    enunciation_source = joinLatexVerbatimNodes(preamble_nodes, start_idx, end_idx)
    return enunciation_names, enunciation_source

def getEnvironmentSources(node, recognized_environments, environments):
    """recognized environments as a dictionary with keys as the environment names
    and values as a list of verbatim latex_code of said environment
    This should preserve order, even though it's recursive since the nesting of nodes
    is still in document order
    Modify the passed environments dictionary
    """
    if node.isNodeType(LatexEnvironmentNode):
        if node.envname in recognized_environments:
            environments[node.envname] += [node.latex_verbatim()]
        else:
            for nested_node in node.nodelist:
                getEnvironmentSources(nested_node, recognized_environments, environments)
    elif node.isNodeType(LatexGroupNode):
        for nested_node in node.nodelist:
            getEnvironmentSources(nested_node, recognized_environments, environments)
    else:
        return
    
def getMetadataAndSelectEnvironments(preamble_nodes, document_node):
    r"""we probably also want to track \footnotes and \captions, too, but I'll think about that later..."""
    metadata = dict()
    start_idx, end_idx = -1, -1
    ## this assumes that there isn't weird nesting in the preamble
    ## we'll probably have to account for that later with a recursive approach, like with markNode
    ## and in extracting the figures, tables, and abstract
    for i, node in enumerate(preamble_nodes): 
        if node.isNodeType(LatexMacroNode) and node.macroname in METADATA_CSNAMES:
            if start_idx < 0:
                start_idx = i
            end_idx = i
            csname = node.macroname            
            verbatim_contents = node.latex_verbatim()
            if csname in metadata and csname in UNIQUE_FIELDS:
                logging.warning(f"! Found more than one instance of unique field '{csname}', overwriting earlier instance.")
                metadata[csname] = verbatim_contents
            elif csname in metadata:
                metadata[csname] = [metadata[csname], verbatim_contents] if type(metadata[csname]) != list else metadata[csname] + [verbatim_contents]
            else:
                metadata[csname] = verbatim_contents
    metadata_source = joinLatexVerbatimNodes(preamble_nodes, start_idx, end_idx)

    environments = {env_name: [] for env_name in TRACKED_ENVIRONMENTS}
    getEnvironmentSources(document_node, TRACKED_ENVIRONMENTS, environments)
    
    num_abstract = len(environments['abstract'])
    if num_abstract == 0:
        logging.warning("No abstract found in getMetadataAndSelectEnvironments()")
    elif num_abstract > 1:
        logging.warninig(f"! Found {num_abstract} abstracts; there should only be one")

    return metadata, metadata_source, environments

def runPDFlatex(tex_filename: Path, runs: int = 2) -> subprocess.CompletedProcess:
    """Run pdflatex. Run twice by default to resolve cross-references"""
    result = None
    tex_filename_dir = tex_filename.parent
    for i in range(runs):
        logging.info(f"Running pdflatex (pass {i+1}/{runs})")
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', tex_filename.name],
            cwd=tex_filename_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding='latin-1'
        )
        
        if result.returncode != 0:
            logging.error(f"""pdflatex failed on pass {i+1} of {tex_filename.name}: {result.stderr}. Output:
            {result.stdout}""")
            sys.exit(1)
        
    return result

def transferTeXFiles(tex_filename: Path, files_to: Path, move_or_copy: str):
    tex_file_dot_star = f"{tex_filename.stem}.*"
    os.system(f"{move_or_copy} {tex_filename.parent / tex_file_dot_star} {files_to}")

def runDiffpdf(first_fname: str, second_fname: str, output_dir: Path) -> subprocess.CompletedProcess:
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = ['diff-pdf',
                          f'--per-page-pixel-tolerance={DIFFPDF_PER_PAGE_PIXEL_TOLERANCE}',
                          f'--dpi={DIFFPDF_DPI}',
                          '--skip-identical',
                          '--grayscale',
                          '--mark-differences',
                          '--verbose',
                          f'--output-diff={diff_fname}',
                          first_fname,
                          second_fname]
    
    logging.info(f"Running `{' '.join(subprocess_command)}`...")
    result = subprocess.run(subprocess_command,
                            cwd=output_dir)
    
    if result.returncode != 0:
        logging.error(f"{first_fname} and {second_fname} are not identical. See {Path(output_dir) / diff_fname}")        
        sys.exit(1)
    else:
        logging.info(f"PDFs are identical according to diff-pdf")

    return result

def markRequiredArg(node: LatexNode, recMark: Callable[[LatexNode], str]) -> str:
    node_verbatim = node.latex_verbatim()
    
    def joinNodelist(transform: Callable[[LatexNode], str]) -> str:
        return '{' + ''.join([transform(nested_node) for nested_node in node.nodelist]) + '}'

    def markify(nested_node: LatexNode):
        return recMark(nested_node)
    
    if node.isNodeType(LatexGroupNode) and node.delimiters == REQUIRED_ARG:
        joined_verbatim_group = joinNodelist(lambda n: n.latex_verbatim())
        if joined_verbatim_group != node_verbatim:
            return node_verbatim
        else:
            return joinNodelist(markify)
    else:
        return node_verbatim

def markArgnlist(argnlist: list[None | LatexNode], recMark) -> str:
    return ''.join([markRequiredArg(node, recMark) if node != None else '' for node in argnlist])

def markNode(start_node: LatexNode, allowed_environments: set[str], chars_node_match_regex: str) -> str:
    """Recursively mark the passsed start_node"""
    counter = count(0)
    def markStr(string: str, mark_identifier: str) -> str:
        return rf'\markbox{{{mark_identifier}{next(counter)}}}{{{string}}}'
        
    def recMark(node):
        node_verbatim = node.latex_verbatim()
        if node.isNodeType(LatexEnvironmentNode):
            verbatim_contents = ''.join([n.latex_verbatim() for n in node.nodelist]) #every LatexEnvironmentNode has a nodelist
            joined_whole = rf'\begin{{{node.envname}}}{verbatim_contents}\end{{{node.envname}}}'
            ## could maybe only do the following check if the environment is among allowed_environments
            ## but it's safer to check every encountered environment
            if node_verbatim != joined_whole:
                logging.error(f"Environment node '{node_verbatim}' in markNode was malformed or parsed incorrectly")
                logging.debug(f"{verbatim_contents} != {joined_whole}")                
                sys.exit(1)
            
            if node.envname in allowed_environments:
                marked_contents = ''
                for nested_node in node.nodelist:
                    marked_contents += recMark(nested_node)
                return rf'\begin{{{node.envname}}}{marked_contents}\end{{{node.envname}}}'
            else:
                return joined_whole
        elif node.isNodeType(LatexMacroNode):
            if node.macroname in MARK_CSNAMES:
                return markStr(node_verbatim, '')
            elif node.macroname == 'item':
                return f'{node_verbatim}{{}} '
            elif node.macroname == 'footnote':
                ## well this is much too messy right now
                len_arg_spec = len(RECOGNIZED_CSNAMES[node.macroname])
                argnlist = node.nodeargd.argnlist
                joined_verbatim_macro = rf"\{node.macroname}" + ''.join([n.latex_verbatim() if n != None else '' for n in argnlist])
                
                if node_verbatim != joined_verbatim_macro:
                    logging.warning(f"""{node.macroname} verbatim, '{node_verbatim}', did not match joined verbatim,
                    '{joined_verbatim_macro}'; ignoring...""")
                    return node_verbatim
                elif len(argnlist) != len_arg_spec:
                    logging.warning(f"""{node.macroname}, {node_verbatim}, did not match argspec len:
                    {len(argnlist)} != {len_arg_spec}""")
                else:
                    return rf"\{node.macroname}" + markArgnlist(argnlist, recMark)
            else:
                return node_verbatim
        elif node.isNodeType(LatexMathNode):
            if node.displaytype == 'inline':
                return markStr(node_verbatim, MARK_IDENTIFIERS['inline math'])
            else:
                return node_verbatim
        elif node.isNodeType(LatexCharsNode):
            ## mark every span in safe envs
            marked_str, num_subs = re.subn(chars_node_match_regex, lambda m: markStr(m.group(0), ''), node_verbatim)
            ### >>>
            ### logging.debug(f"marked {num_subs} words in {node_verbatim}")
            ### <<<
            return marked_str
        elif node.isNodeType(LatexGroupNode):
            ## for the time being this means that naked group blocks are ignored---will need to revisit
            ## I have to be careful though, because if I encounter an unrecognized macro then one of 
            ## its arguments could be in a group node.
            return node_verbatim
        elif node.isNodeType(LatexCommentNode):
            return node_verbatim
        else:
            logging.warning(f"Encountered unrecognized latex node '{node.nodeType()}' during markNode().\n Writing node.latex_verbatim(): '{node_verbatim}'")
            return node_verbatim
        
    return recMark(start_node), next(counter)

def getPreambleAndDocument(nodelist):
    """Read in a list of pylatexenc.latexwalker.<Node>s and return the nodes which belong to the
       preamble and document"""
    num_document_envs = len(list(filter(lambda n: n.isNodeType(LatexEnvironmentNode) and n.envname == 'document', nodelist)))
    if num_document_envs != 1:
        logging.error(r"Found more (or less) than one `\begin{document}`s during getPreambleAndDocument(). Exiting unsuccessfully.")
        sys.exit(1)

    i = 0
    while nodelist[i].nodeType() != LatexEnvironmentNode:
        i += 1
    preamble_nodes = nodelist[:i]
    document_node = nodelist[i]
    
    if i+1 < len(nodelist):
        logging.debug(f"Discarded {len(nodelist)-(i+1)} latex nodes after `\\end{{document}}` during getPreambleAndDocument")

    return preamble_nodes, document_node

def texPointsToPDFpoints(tex_pts: float):
    return tex_pts * TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO

def scaledPointsToPDFpoints(sp: int):
    tex_pts = sp / SCALED_POINTS_PER_TEX_POINT
    return texPointsToPDFpoints(tex_pts)

def unzipHbox(hbox):
    return hbox[0], tuple(map(lambda pts: texPointsToPDFpoints(float(pts)), hbox[1:]))

def unzipPos(stend_xy):
    return stend_xy[0], tuple(map(lambda spts: scaledPointsToPDFpoints(int(spts)), stend_xy[1:-1]))

def boxinfoToPDFRectangle(key, hbox, start_xy, end_xy):
    pgA, (width, height, depth) = unzipHbox(hbox)
    pgB, (x0, sy) = unzipPos(start_xy)
    pgC, (x1, ey) = unzipPos(end_xy)

    if pgB != pgC:
        logging.debug(f"box '{key}' spanned multiple pages ({pgA} {pgB} {pgC}; ignoring")
        return None
    if sy != ey:
        logging.debug(f"box '{key}' start and end y positions were not equal: '{sy} != {ey}'; ignoring")
        return None
    if abs(x0 + width - x1) > WORD_BOX_WIDTH_TOLERANCE:
        logging.debug(f"box '{key}' abs(x0 + width - x1) = abs({x0 + width} - {x1}) = {abs(x0 + width - x1)} > {WORD_BOX_WIDTH_TOLERANCE}; ignoring")
        return None

    ## lower y values are closer to the top of the page
    ## return pageno, (x0, y0, x1, y1), where
    ## (x0, y0) is the top left corner and
    ## (x1, y1) is the bottom right corner of the rectangle
    return pgB, (x0, sy + height, x1, sy - depth)
        
def getWordBoxes(boxpositions_file_name: str, tot_num_boxes):
    word_boxes = dict()
    not_colon = r'([^:]*)'

    with open(boxpositions_file_name, 'r') as f:
        line = f.readline().strip()
        line_no = 1
        while line:
            box_info = re.match(fr"^(m?\d+):(pwhd|spxy|epxy):(\d+):{not_colon}:{not_colon}:{not_colon}$", line)
            if box_info == None:
                logging.error(f"Somehow line {line_no} of {boxpositions_file_name} '{repr(line)}' did not match the info spec. Exiting unsuccessfully.")
                sys.exit(1)
            matches = box_info.groups()
            key, label, values = matches[0], matches[1], tuple(map(lambda m: m.strip('pt'), matches[2:]))
            
            if key in word_boxes:
                if label in word_boxes[key]:
                    logging.error(f"""Somehow label '{label}' was already in '{word_boxes[key]}'.
                    There should be only three labels (and they should each appear at most once):
                    'pwhd' for page, width, height, depth; 'spxy' for start, page, x pos, y pos;
                    and 'epxy' for end, page, x pos, y pos""")
                    sys.exit(1)
                word_boxes[key][label] = values
            else:
                word_boxes[key] = {label:values}
            line = f.readline().strip()
            line_no += 1

    ## all marks should have exactly three fields, the hbox dimensions, start xy, and end xy positions
    if not all(filter(lambda x: x == 3, map(lambda d: len(d), list(word_boxes.values())))):
        logging.error(f"Information extracted from marks somehow differed from spec.")
        sys.exit(1)

    num_used_boxes = 0
    
    page_rectangles = dict()
    for key, info in word_boxes.items():
        res = boxinfoToPDFRectangle(key, info['pwhd'], info['spxy'], info['epxy'])
        if res == None:
            continue
        one_indexed_pageno, rectangle = res
        pageno = int(one_indexed_pageno) - 1
        if pageno in page_rectangles:
            page_rectangles[pageno][key] = rectangle
        else:
            page_rectangles[pageno] = {key:rectangle}
        num_used_boxes += 1

    logging.info(f"Used {num_used_boxes}/{tot_num_boxes} marked boxes.")
    return page_rectangles

def segment(tex_filename: str):
    r"""Return the TeX source that appears on outputted pages and as the arguments to certain dedicated commands or environments. Page-level partitioning is achieved with a hook to \shipout and frequent use of \mark. There's probably a better way, but this works..."""
    tex_filename = Path(tex_filename)
    
    tex_str = sourceAsString(tex_filename)
    latex_context = LatexContextDb()

    macro_specs = [std_macro(csname, args_format) for csname, args_format in RECOGNIZED_CSNAMES.items()]
    
    latex_context.add_context_category('segmentspec', macros=macro_specs)
    
    (nodelist, _, _) = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)
    
    if ''.join([node.latex_verbatim() for node in nodelist]) != tex_str:
        logging.error(f"Verbatim string tex source was not preserved after LatexWalker parsing. The parser has likely failed. Exiting unsuccessfully.")
        sys.exit(1)
           
    preamble_nodes, document_node = getPreambleAndDocument(nodelist)

    ## get metadata here >>>
    enunciation_names, enunciation_source = getEnunciations(preamble_nodes)
    metadata, metadata_source, environments = getMetadataAndSelectEnvironments(preamble_nodes, document_node)
    ## <<<

    mark_out_filename = f'boxpositions_{tex_filename.stem}.txt'
    tex_write_commands = fr"""
\newwrite\markfile
\immediate\openout\markfile={mark_out_filename}
"""
    markbox_def = r"""
\newcommand{\markbox}[2]{%
  \setbox0=\hbox{#2}%
  \immediate\write\markfile{#1:pwhd:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:spxy:\the\value{page}:\the\pdflastxpos:\the\pdflastypos:}%
  #2% 
  \pdfsavepos
  \write\markfile{#1:epxy:\the\value{page}:\the\pdflastxpos:\the\pdflastypos:}%
}

"""
    logging.info("Inserting marks...")
    ## form moving foward should be markNode(tex_str) that's it---it will find the enunciations and all

    left = r"[\t $(\[]"
    inside = r"[a-zA-Z0-9!?.,'`/;:\-()]+"
    right = r"[\t $)\]]"
    # chars_node_match_regex = rf"(?:^|(?<={left})){inside}(?:$|(?={right}))"
    chars_node_match_regex = rf"(?<={left}){inside}(?={right})"    

    ## old >>>
    # chars_node_match_regex = r"(?<=[\t $])[a-zA-Z0-9!?.,;:\-()]+(?=[\t $])"
    ## <<<
    ##
    
    marked_document, num_marks = markNode(document_node, ALLOWED_MARK_ENVIRONMENTS.union(enunciation_names), chars_node_match_regex)
    logging.info("Done.")

    preamble_str = ''.join([node.latex_verbatim() for node in preamble_nodes])    
    
    marked_tex = preamble_str + tex_write_commands + markbox_def + marked_document

    ## save at first the marked file to the same directory as the input tex_filename, then move it after pdflatex
    marked_filename = tex_filename.parent / f"{tex_filename.stem}_marked{tex_filename.suffix}"
    writeStringToFile(marked_tex, marked_filename)

    process1 = runPDFlatex(tex_filename)
    process2 = runPDFlatex(marked_filename)

    tmp_dir = Path('tmp_segmentsource')
    Path.mkdir(tmp_dir, exist_ok = True)

    transferTeXFiles(tex_filename, tmp_dir, 'cp')
    transferTeXFiles(marked_filename, tmp_dir, 'mv')
    ## move boxpositions file
    os.system(f"mv {tex_filename.parent / mark_out_filename} {tmp_dir}")

    def pdfFname(tex_fname: Path):
        return f"{tex_fname.stem}.pdf"    
    
    process3 = runDiffpdf(pdfFname(tex_filename), pdfFname(marked_filename), tmp_dir)
    
    ## temporary
    return marked_tex, tmp_dir / mark_out_filename, num_marks

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python segmentsource.py',
                                     description = r'Segments source TeX by pages and metadata like \title, \author, \address, and abstract.')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    segment(filename)
