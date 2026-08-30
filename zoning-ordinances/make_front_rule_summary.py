"""Regenerate front-rule-summary.pdf (the counsel-facing one-pager) from
zoning_ordinance_links.json.

Layout mirrors the 23-jurisdiction version approved via the Slack thumbs-up
flow (2026-08-30): intro, per-jurisdiction table grouped by county, San Jose
exception footnote, judgment-call notes, sign-off ask. Records whose
research_source marks them as non-Zoneomics county research are highlighted
as PENDING REVIEW until counsel thumbs them up.

Run:  python3 make_front_rule_summary.py   (from zoning-ordinances/)
"""
import json
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DB_PATH = 'zoning_ordinance_links.json'
OUT_PATH = 'front-rule-summary.pdf'

RULE_TEXT = {
  'shortest_frontage': 'Shortest frontage is the front',
  'address_street': 'Address street is the front',
  'designated': 'City designates the front (falls back to default)',
  'owner_elected': 'Owner picks the front (falls back to default)',
  'all_fronts': 'Every street side is a front',
}

PENDING = colors.HexColor('#FFF3CD')
INK = colors.HexColor('#24312B')


def _short_citation(record):
  citation = (record.get('front_rule') or {}).get('citation') or ''
  return citation.split(' - ')[0].strip()


def _grouped(jurisdictions):
  """File order, but each county's unincorporated record closes its group."""
  county_order, by_county = [], {}
  for record in jurisdictions:
    county = record['county']
    if county not in by_county:
      county_order.append(county)
      by_county[county] = []
    by_county[county].append(record)
  out = []
  for county in county_order:
    group = by_county[county]
    cities = [r for r in group if 'unincorporated' not in r['jurisdiction'].lower()]
    counties = [r for r in group if 'unincorporated' in r['jurisdiction'].lower()]
    out.extend(cities + counties)
  return out


def main():
  with open(DB_PATH, encoding='utf-8') as handle:
    db = json.load(handle)
  records = _grouped(db['jurisdictions'])
  pending = [r for r in records if 'not from Zoneomics' in (r.get('research_source') or '')]

  styles = getSampleStyleSheet()
  body = ParagraphStyle('body', parent=styles['Normal'], fontSize=8.6, leading=11.4, textColor=INK)
  cell = ParagraphStyle('cell', parent=body, fontSize=8.2, leading=10.2)
  small = ParagraphStyle('small', parent=body, fontSize=7.6, leading=9.8, textColor=colors.HexColor('#444444'))
  h1 = ParagraphStyle('h1', parent=styles['Title'], fontSize=14.5, leading=18, textColor=INK, spaceAfter=2)
  sub = ParagraphStyle('sub', parent=body, alignment=1, textColor=colors.HexColor('#555555'))
  h2 = ParagraphStyle('h2', parent=styles['Heading3'], fontSize=10, textColor=INK, spaceBefore=10, spaceAfter=3)

  story = [
    Paragraph('FormX — How we assign the front of a corner lot', ParagraphStyle('t', parent=h1, alignment=1)),
    Paragraph('One rule per jurisdiction, from each municipal or county code · %d Bay Area jurisdictions · %s · '
              '<b>%d county records pending review (highlighted)</b>'
              % (len(records), date.today().isoformat(), len(pending)), sub),
    Spacer(1, 8),
    Paragraph("Setbacks depend on which side of a lot is legally the front. For corner lots each code answers this "
              "differently, so our engine applies the rule below per jurisdiction — each verified against the cited "
              "code section. Default when a jurisdiction isn't listed: the street in the parcel's address is the "
              "front (shortest frontage if no side matches the address). The five unincorporated-county rows are new "
              "(researched 2026-08-30 directly from the county codes) and awaiting your sign-off; the 23 city rows "
              "are unchanged from the version you approved.", body),
    Spacer(1, 8),
  ]

  data = [[Paragraph('<b>Jurisdiction</b>', cell), Paragraph('<b>Rule for corner lots</b>', cell), Paragraph('<b>Citation</b>', cell)]]
  pending_rows = []
  for record in records:
    rule = (record.get('front_rule') or {}).get('rule')
    rule_text = RULE_TEXT.get(rule, rule or '?')
    if record['jurisdiction'] == 'San Jose':
      rule_text += ' *'
    name = record['jurisdiction']
    if record in pending:
      pending_rows.append(len(data))
      name += ' †'
    data.append([Paragraph(name, cell), Paragraph(rule_text, cell), Paragraph(_short_citation(record), cell)])

  table = Table(data, colWidths=[2.15 * inch, 2.75 * inch, 2.35 * inch], repeatRows=1)
  style = [
    ('LINEBELOW', (0, 0), (-1, 0), 0.7, INK),
    ('LINEBELOW', (0, 1), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 2.2),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
    ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ('RIGHTPADDING', (0, 0), (-1, -1), 3),
  ]
  for row in pending_rows:
    style.append(('BACKGROUND', (0, row), (-1, row), PENDING))
  table.setStyle(TableStyle(style))
  story.append(table)
  story.append(Spacer(1, 6))

  story += [
    Paragraph('* San Jose exceptions: a corner lot with both frontages over 120 ft (residential) / 150 ft (commercial) '
              'gets two fronts (SJMC 20.200.670(A)); in the MS-G/MS-C main-street districts every corner lot gets two '
              'fronts (20.200.670(B)).', small),
    Paragraph('† NEW — county code research 2026-08-30, pending your review. These govern unincorporated land only; '
              'every parcel resolves to exactly one row here by point-in-polygon containment (incorporated place, '
              'else the county).', small),
    Paragraph('(falls back to default) — where the city or the owner picks the front, there is nothing for us to '
              'compute from, so the engine applies the default (address street) until a designation or election is '
              'actually made.', small),

    Paragraph('Judgment calls in the five new county rows', h2),
    Paragraph('<b>Contra Costa County</b> — Ord. Code 82-12.202 applies setbacks to every street frontage of a corner '
              'lot, so we encode all_fronts; district chapters then give the "principal frontage" the full front value '
              'and the other a reduced one (e.g. R-6: 20/15 ft). "Principal frontage" is not defined anywhere in '
              'Title 8 — we read it as the address street. Both frontages are binding street setbacks either way.', body),
    Paragraph('<b>Marin County</b> — MCC 22.130.030 makes the front "the street to which the property is addressed '
              'AND the street from which access is taken." When those two streets differ on a corner lot, the code '
              'literally creates two front lot lines; we encode address_street and will flag address-vs-access '
              'mismatches rather than silently picking one. Coastal zone (Title 20) has its own definitions we have '
              'not yet reviewed.', body),
    Paragraph('<b>Napa County &amp; Santa Clara County</b> — both are shortest-frontage by code (NCC 18.08.190; SCC '
              'Zoning Ord. 1.30.030), but each carries an official escape hatch (Napa: director may designate; Santa '
              'Clara: a building-envelope tiebreak can flip to the longer line, and the zoning administrator classifies '
              'unusual lots). We apply the geometric default and surface it, since a designation is not derivable '
              'from parcel data.', body),
    Paragraph('<b>Sonoma County</b> — SCC 26-04-020 says a corner lot\'s front is "either one or the other" of the two '
              'street lot lines, naming no geometric test and no designating official; we read that as an owner '
              'election (falls back to default). Largely moot in magnitude: county residential tables set the street-'
              'side setback equal to the front setback. On through lots every street line is a front (26-88-040(a)).', body),
    Spacer(1, 6),
    Paragraph('If the five highlighted rows and the calls above look right, a &#128077; on Slack covers them — the city '
              'rows are unchanged from the version already approved. Full citations and reasoning are in '
              'zoning_ordinance_links.json and on request.', body),
  ]

  def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#888888'))
    canvas.drawString(0.75 * inch, 0.45 * inch,
                      'FormX · front-of-lot rules · from zoning_ordinance_links.json (%s)' % db.get('generated', ''))
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, 'Page %d' % doc.page)
    canvas.restoreState()

  doc = SimpleDocTemplate(OUT_PATH, pagesize=letter,
                          leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                          topMargin=0.6 * inch, bottomMargin=0.7 * inch,
                          title='FormX front-of-lot rules', author='FormX')
  doc.build(story, onFirstPage=footer, onLaterPages=footer)
  print('wrote %s: %d jurisdictions, %d pending review' % (OUT_PATH, len(records), len(pending)))


if __name__ == '__main__':
  main()
