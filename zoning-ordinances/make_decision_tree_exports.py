"""Export the ADU Setback Decision Tree (the high-level PRD diagram) to PDF + PNG.

The tree lives as one HTML page (adu-setback-decision-tree.html, also published
as a Claude artifact). It is still changing — Phase B onward is being worked
out — so the exports are regenerated from the page rather than hand-drawn:

  python3 make_decision_tree_exports.py        (from zoning-ordinances/)

Produces, next to this script:
  adu-setback-decision-tree.pdf           both views (lean, extended) + the decision panels
  adu-setback-decision-tree-lean.png      page 1 of the PDF
  adu-setback-decision-tree-extended.png  page 2 of the PDF

Needs Google Chrome (headless print) and poppler's pdftoppm (brew install poppler).
The page's '#all' mode stacks both diagrams one per page; the panels follow.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, 'adu-setback-decision-tree.html')
PDF = os.path.join(HERE, 'adu-setback-decision-tree.pdf')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def main() -> int:
  if not os.path.exists(PAGE):
    print('missing %s' % PAGE, file=sys.stderr)
    return 1
  if not os.path.exists(CHROME):
    print('Google Chrome not found at %s' % CHROME, file=sys.stderr)
    return 1
  url = 'file://%s#all' % PAGE
  # virtual-time-budget lets the web fonts and the JS-drawn SVG settle before printing.
  cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
         '--virtual-time-budget=8000', '--print-to-pdf=%s' % PDF, url]
  subprocess.run(cmd, check=True, capture_output=True, timeout=120)
  for _ in range(20):
    if os.path.exists(PDF) and os.path.getsize(PDF) > 0:
      break
    time.sleep(0.25)
  print('wrote %s (%d bytes)' % (PDF, os.path.getsize(PDF)))

  prefix = os.path.join(HERE, 'adu-setback-decision-tree')
  subprocess.run(['pdftoppm', '-r', '150', '-png', '-f', '1', '-l', '2', PDF, prefix], check=True)
  for page, name in ((1, 'lean'), (2, 'extended')):
    for candidate in ('%s-%d.png' % (prefix, page), '%s-0%d.png' % (prefix, page)):
      if os.path.exists(candidate):
        os.replace(candidate, '%s-%s.png' % (prefix, name))
        print('wrote %s-%s.png' % (prefix, name))
  return 0


if __name__ == '__main__':
  sys.exit(main())
