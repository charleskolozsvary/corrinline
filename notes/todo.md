1. Checking footnotes and captions if PDF annot rectangle does not intersect any tex_word_boxes.
1.1 Improve before and after sorting of tex_word_boxes when the PDF annotation rectangle doesn't intersect any of them. Sort their centers (including the annotation rect's center) by x then y and then use those before the annotation as the before pool and those after as the after pool.
2. Limit character checks for selection text to generous region around annotation rectangle, not full page (speed up)
3. Standardize labels
4. Do autocorrections for "In the following theorem" -> "In Theorem~\ref{thmlabel}"





