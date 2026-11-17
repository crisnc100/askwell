---
name: Askwell
description: Ask your database a question; every answer comes with its carbon copy and its stamp.
colors:
  paper: "#e2ebe4"
  paper-deep: "#d3e0d6"
  field: "#f1f5f1"
  carbon-paper: "#e3e6ef"
  ink: "#15181d"
  ink-soft: "#3c4149"
  carbon: "#2b2f80"
  carbon-soft: "#5a5ea6"
  red: "#a3261d"
  blue: "#2c5291"
typography:
  display:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(2.25rem, 1.1rem + 3.4vw, 3.875rem)"
    fontWeight: 780
    lineHeight: 1.02
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 104"
  page-title:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(1.75rem, 1.4rem + 1.2vw, 2.375rem)"
    fontWeight: 780
    lineHeight: 1.1
    letterSpacing: "-0.015em"
    fontVariation: "'wdth' 104"
  headline:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(1.5rem, 1.2rem + 1vw, 2rem)"
    fontWeight: 760
    lineHeight: 1.15
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 104"
  title:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 740
    lineHeight: 1.25
  lead:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.45
  body:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  body-ledger:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.45
  note:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.09em"
    fontVariation: "'wdth' 115"
  nav:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 650
    letterSpacing: "0.08em"
    fontVariation: "'wdth' 115"
  button:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 750
    letterSpacing: "0.08em"
    fontVariation: "'wdth' 112"
  figure:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 820
    fontFeature: "'tnum' 1, 'zero' 1"
  stamp-value:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "2.625rem"
    fontWeight: 880
    lineHeight: 0.95
    letterSpacing: "0.01em"
    fontVariation: "'wdth' 78"
    fontFeature: "'tnum' 1, 'zero' 1"
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
    lineHeight: 1.55
rounded:
  none: "0px"
spacing:
  gutter: "clamp(16px, 4.4vw, 64px)"
  slip-inset: "28px"
  slip-inset-narrow: "18px"
  section: "72px"
  section-narrow: "56px"
  page-end: "96px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.field}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "10px 22px"
  button-primary-hover:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
  button-primary-disabled:
    backgroundColor: "{colors.paper-deep}"
    textColor: "{colors.ink-soft}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.red}"
    rounded: "{rounded.none}"
    padding: "9px 18px"
  button-danger-hover:
    backgroundColor: "{colors.red}"
    textColor: "{colors.field}"
  input-text:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "7px 9px"
  step-tab:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "10px 14px"
  step-tab-current:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.field}"
  slip-original:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    padding: "0 28px 28px"
  slip-carbon:
    backgroundColor: "{colors.carbon-paper}"
    textColor: "{colors.carbon}"
    padding: "0 28px 24px 30px"
  stamp:
    backgroundColor: "transparent"
    textColor: "{colors.red}"
    typography: "{typography.stamp-value}"
    rounded: "{rounded.none}"
    padding: "4px 16px 2px"
  statement:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "22px 28px"
  statement-figure:
    textColor: "{colors.red}"
    typography: "{typography.figure}"
  fold-summary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    padding: "18px 2px"
---

# Design System: Askwell

## Overview

**Creative North Star: "The Audited Ledger"**

Every answer is a cheque with its carbon copy. The original slip, on pale cheque paper over a fine guilloche security pattern, carries what the visitor asked, the form the AI filled in, the check, the SQL and the rows. The carbon copy, torn off down a line of punched holes and printed in indigo, carries only what the AI was shown: table and column names over empty cells, and the count of rows sent to it, always zero. A red rubber stamp lands on the result. The page is a business document, not an app screen: hard ink rules, square corners, no shadows, no cards floating on a canvas.

Rank comes from one variable grotesk pushed through weight, width and case, not from a second family or a parade of sizes. Color is semantic before it is decorative: indigo means "the AI saw this", red means "audited, refused, hidden or measured", blue means "a line you write on". Depth is the change of paper (sage page, near-white slip, lavender-grey carbon) and the weight of the rule between them.

Scope: the front page (`/`), the ask flow (`/try/`) and Results (`/results/`) are built in this world and share `web/src/tokens.css`. Value (`/value/`) still loads the older `style.css` and is not yet in this world; it is not described here and is not a source for new work.

**Key Characteristics:**
- Sage cheque paper with a guilloche security pattern, densest on the slip, faint on the page head, never behind long-read paragraphs.
- One family, Archivo variable, ranked by weight (400 to 880), width (78% to 115%) and uppercase tracking.
- 2px ink frames, 1px subdivisions, square corners everywhere.
- Indigo carbon reserved for what the AI was shown; absence drawn as empty dashed cells.
- A red rotated rubber stamp with uneven ink as the single mark of a checked result.
- Flat: no box shadows, no gradients, no glow.

## Colors

Cheque-stock greens under near-black ink, with three working inks that each carry one meaning.

### Primary
- **Carbon Indigo** (#2b2f80): the carbon copy. Text, rules and the "Rows sent to the AI" count on the carbon half of the slip; in `/try/`, the preview of the prompt the model receives. Also the text-selection highlight.
- **Carbon Indigo Soft** (#5a5ea6): the dashed outlines of empty carbon cells for columns the form did not use.

### Secondary
- **Ledger Red** (#a3261d): audit marks. The CHECKED / NOT ANSWERED and MEASURED stamps, the slip number, the figures and rules of the Results statement and comparison, a failed release check, the double rule under "Measured results" and the measured figures, the column rule of the how-it-works ledger, hidden columns ("Never shown"), errors, the danger button, the caret.

### Tertiary
- **Form Blue** (#2c5291): lines you write on. The underline of the question field, the rules between form lines and answer rows, the border of SQL blocks, starter-question underlines, the "More questions" link, the passed badge, the focus ring and native control accents.

### Neutral
- **Cheque Sage** (#e2ebe4): the page ground.
- **Deep Sage** (#d3e0d6): hover fill for step tabs, disabled button fill, scrollbar track.
- **Slip White** (#f1f5f1): the original slip, input fields, tables, SQL blocks, notices; the text color on ink buttons.
- **Carbon Paper** (#e3e6ef, `--carbon-paper`): the carbon half of the slip and anything else printed as carbon: in `/try/`, the prompt preview and the notice about which values go to the model. Nothing the AI was not shown is printed on it.
- **Ink** (#15181d): body text, 2px frames, primary button fill.
- **Soft Ink** (#3c4149): notes under steps, form-line keys, muted copy, disabled text.

### Named Rules
**The Carbon Rule.** Indigo on carbon paper means "this is what the AI was shown". Nothing the AI did not see is printed in carbon.

**The Three Inks Rule.** Red audits, blue lines the form, indigo is the carbon. A color that carries no one of those meanings stays ink.

## Typography

**Display Font:** Archivo variable (with Helvetica Neue, Arial, sans-serif), self-hosted at `/fonts/archivo-latin-var.woff2`, weight 100–900, width 62–125%, preloaded.
**Body Font:** Archivo, same file.
**Label/Mono Font:** system monospace (ui-monospace, SF Mono, Menlo, Consolas) for column names, form values and SQL only.

**Character:** a printed-form grotesk: heavy and slightly widened for the headline, widened and tracked uppercase for captions, condensed and heavy for the stamp. Numbers in tables and outputs use tabular figures with a slashed zero.

### Hierarchy
- **Display** (780, clamp 2.25–3.875rem, 1.02): the one-line promise on the front page; balanced wrap.
- **Page title** (780, clamp 1.75–2.375rem, 1.1): the step title in `/try/`.
- **Headline** (760, clamp 1.5–2rem, 1.15): section heads below the slip.
- **Title** (740, 1.1875rem, 1.25): sub-heads inside `/try/` steps.
- **Lead** (400, 1.125rem, 1.45, max 40ch): the two sentences beside the promise.
- **Body** (400, 1rem, 1.5; 1.0625rem in ledgers and closing copy; max 60–72ch).
- **Note** (400, 0.875rem, Soft Ink): the line under a step caption.
- **Label** (700, 0.75rem, width 115%, 0.09em, uppercase): captions on the slip and the form: "You asked", each step, table heads, the carbon title.
- **Nav** (650, 0.8125rem, width 115%, 0.08em, uppercase) and **Button** (750, 0.9375rem, width 112%, 0.08em, uppercase).
- **Figure** (820, 1.0625rem, red): a measured number inside a ledger line. The rows-sent count runs larger (820, 2.25rem).
- **Stamp** (word 820 at 0.9375rem, width 90%, 0.16em; value 880 at 2.625rem, width 78%).

### Named Rules
**The Weight-and-Width Rule.** Rank is set by weight, width and case within one family. Don't add a second display face or a new size where a weight or width step does the job.

**The Caption Rule.** Uppercase labels caption a field, a step, a table column or a block of the slip, as printed captions do on a cheque. They never sit above a headline as a kicker.

## Layout

Full-bleed bands with a fluid side gutter (16–64px). The front page head is a two-column grid (7fr / 4fr, bottom-aligned): the promise left, the lead right. The slip spans the gutter-to-gutter width as a 7fr / 5fr grid: original left, carbon right, framed in a 2px ink rule. Inside the slip, a full-bleed caption strip with a 1px rule opens each half; steps stack, each opened by a 1px ink rule. Sections below the slip open with 72px of space and the page closes with 96px. `/try/` is a single 920px reading column with the same gutter.

At 860px and below everything stacks to one column: the carbon drops beneath the original, the perforation turns horizontal, the slip insets shrink to 18px, the Ask button wraps under the field, and the stamp moves from the carbon onto the rows. At 600px the top nav becomes a single scrolling row.

## Elevation & Depth

Flat. There are no box shadows anywhere. Depth is paper against paper: sage ground, near-white slip, lavender-grey carbon, separated by rules whose weight states their rank (2px ink for frames and table heads, 1px for subdivisions). The guilloche pattern adds texture, not height.

### Named Rules
**The Flat Paper Rule.** Surfaces never lift. If something needs separating, change the paper or draw a rule.

## Shapes

Every box, button, field and badge has square corners (0px). Frames are 2px solid ink; subdivisions 1px. Dashed lines belong to the carbon: empty cells, the fold above "other tables", carbon notices. The only circles are the punched holes of the perforation between original and carbon, drawn as small ink-outlined rings on page paper (vertical on wide screens, horizontal when stacked). The stamp is a rectangle with a 3px border and a 1px outline 3px outside it, rotated −6°, its ink broken by a noise mask.

## Components

### Buttons
Plain, inked and square.
- **Shape:** square (0px), 2px ink border.
- **Primary:** ink fill, slip-white text, uppercase widened button type, 10px 22px ("Ask", "Try your data"; 9px 18px in `/try/`).
- **Hover / Focus:** fill and text swap (slip white, ink) over 160ms; focus is a 3px Form Blue outline at 3px offset. No transition under reduced motion.
- **Disabled:** Deep Sage fill, Soft Ink border and text, progress cursor.
- **Danger:** transparent with red border and text; fills red on hover.
- **Text link button:** no box; ink text on a Form Blue underline that thickens on hover (starter questions, small actions in `/try/`).

### Inputs / Fields
- **The question field:** borderless, transparent, on a 2px Form Blue underline, the Ask button inline at its right; text 560 at up to 1.625rem.
- **Form fields in `/try/`:** slip-white fill, 1px ink border, square, 7px 9px. File picker button is a slip-white square with a 2px ink border.
- **Focus:** the global Form Blue ring; the question field offsets it 6px.

### Navigation
Top rule: the Askwell wordmark (800, width 112%) left, three uppercase nav links right, over the faint guilloche, closed by a 2px ink rule. Hover and the current page take a 2px underline.

### Step tabs (`/try/`)
A row of uppercase label cells inside a 2px ink frame, split by 1px ink rules. Current step inverts to ink with slip-white text; hover deepens to Deep Sage; unreached steps fade.

### Notices and tables
Notices are square boxes on slip white: 1px ink by default, 2px Form Blue for success, 2px red with red text for errors, dashed indigo on carbon paper for what the model will be sent, and 2px ink with the reason in ledger red for a refused answer, which is the visitor's result and so never carbon. Tables are slip white with a 2px ink rule under uppercase label heads and 1px Form Blue rules between rows.

### The Cheque Slip (signature)
The original (slip white over dense guilloche) and the carbon (carbon paper, indigo) side by side in one 2px ink frame, torn apart by the perforation. The original fills step by step: question, form lines (key in Soft Ink, value in mono on Form Blue rules), the check, the SQL (mono on slip white in a 1px blue box), the rows. Empty steps show a single blue write-on line. The carbon lists used tables as rows of column names over empty dashed cells, used columns bold and underlined; hidden columns struck through over red "hidden" cells; the rest folded behind a dashed rule. A 2px indigo rule sets off "Rows sent to the AI: 0", and a red-ruled ledger of the measured figures closes the carbon.

### The Stamp (signature)
"Checked" over the value, or "Not answered" over "Said so", in red, rotated −6°, with uneven ink. It drops in once (scale 1.5 to 1 over 300ms) after the slip has filled, then stays down.

### The Statement (Results)
The three plain answers on `/results/` as an audited statement: one 2px ink frame on slip white, a caption strip over the security pattern ("Statement of measured results" left, the version in red right) closed by a 2px red rule, then one ruled line per answer split by 1px red rules. Each line is three columns (3fr / 5fr / 5fr): the question as a label, the measured figure in red (820, width 92%, clamp 1.75–2.5rem, tabular) over a one-sentence detail, and one sentence on what it means for someone relying on the numbers. The foot states the provenance in Soft Ink with a link to the sources fold, and carries a MEASURED stamp over the number of runs, which drops in once when the figures load. Every figure is computed from the committed reports, never typed. At 860px the columns stack and the insets shrink to 18px.

A comparison follows as a red-ruled ledger table (the how-it-works ledger's rules): a row label, then one column per system, figures in red.

### Folds (Results)
The technical record lives behind native `<details>` folds, so nothing technical sits in a headline. Each fold is a ledger line: 2px ink rule above (and below the last), a summary in Title type with a drawn plus that turns to a minus when open, focusable and toggled by Enter or Space. The body opens with one bold line defining the fold's terms in plain words, under a 1px Form Blue rule, then the tables (slip white, 2px ink under uppercase heads, 1px blue between rows; wide ones scroll inside their own box). A failed check is red text; the override sits in a 2px red notice. Notices inside follow the Notices rules above.

### Motion
One orchestrated sequence per answer: each step feeds in from above (clip reveal plus 8px drop, 560ms, `cubic-bezier(0.16, 1, 0.3, 1)`), then the stamp comes down. Everything else is a 160ms color swap. Reduced motion removes the feed, the stamp drop and the transitions.

## Do's and Don'ts

### Do:
- **Do** take every color from `tokens.css`; Ink, Slip White and the three working inks cover the build.
- **Do** print anything the model receives on carbon paper in indigo, and nothing else.
- **Do** draw absence: an empty dashed cell, a struck-through hidden column, "Rows sent to the AI: 0".
- **Do** separate with rules: 2px ink for frames and table heads, 1px for rows and steps, red rules for ledgers of audited facts, blue rules for lines you write on.
- **Do** set numbers in tables and outputs with tabular figures and a slashed zero.
- **Do** keep the guilloche off long-read copy; it belongs on the page head and the slip.

### Don't:
- **Don't** round a corner or add a box shadow, gradient or glow.
- **Don't** add a second type family for display; reach for Archivo's weight and width instead.
- **Don't** use the red stamp for anything but the checked or refused result, and the MEASURED stamp on the Results statement.
- **Don't** put an uppercase label above a headline as a kicker; labels caption fields, steps and tables.
- **Don't** build the AI-landing layout of a headline beside a chat screenshot or a row of feature cards.
