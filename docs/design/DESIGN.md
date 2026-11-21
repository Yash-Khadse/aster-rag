---
name: Atlas
description: "An editorial workspace for answers and their sources."
colors:
  ink: "#17243b"
  muted: "#546175"
  canvas: "#faf9f6"
  paper: "#ffffff"
  rail: "#efeee9"
  line: "#dcdedb"
  line-strong: "#c3c9d0"
  accent: "#2944ad"
  accent-hover: "#1b328e"
  accent-soft: "#eaf0ff"
  navy: "#14254a"
  danger: "#9a292c"
  danger-soft: "#fff0ee"
typography:
  display:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "clamp(2.45rem, 5vw, 4.8rem)"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "clamp(2rem, 3.4vw, 3.25rem)"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Aptos, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.2
  body:
    fontFamily: "Aptos, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    lineHeight: 1.55
  label:
    fontFamily: "Aptos, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 650
    lineHeight: 1.6
rounded:
  chip: "6px"
  control: "8px"
  panel: "12px"
  overlay: "14px"
spacing:
  compact: "8px"
  inline: "10px"
  inset: "12px"
  section: "16px"
  panel: "20px"
  group: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "9px 15px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-secondary-hover:
    backgroundColor: "{colors.accent-soft}"
  button-danger:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  button-text:
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "4px 0"
  button-icon:
    rounded: "{rounded.control}"
    width: "42px"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  badge:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "2px 8px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  navigation-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  citation:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "5px"
    padding: "1px 5px"
---

# Design System: Atlas

## Overview

**Creative North Star: "The Editorial Reference Desk"**

Atlas treats an answer as a passage the reader can verify. Warm paper and light rails hold the reading surface and its source index together. Numbered marks in the answer let the reader move directly to the supporting excerpt.

Serif headings give the larger reading surfaces a clear entry point. Sans-serif controls and ruled rows keep navigation, forms, and workspace records easy to scan.

**Key Characteristics:**

- Warm canvas, light rails, and fine rules.
- Source Serif 4 headings paired with compact sans-serif controls.
- Numbered citations paired with excerpts and source links.

## Colors

Warm neutrals establish the surfaces and navy carries the text. Cobalt marks interaction and selection.

### Primary

- **Cobalt** fills primary actions, colors text actions and citation numbers, and defines the default keyboard focus outline.
- **Deep Cobalt** is the hover color on solid primary actions. **Pale Cobalt** marks selected navigation, citation chips, badges, and the selected excerpt.

### Secondary

- **Deep Navy** anchors the sign-in story. The main workspace uses Navy Ink on light surfaces.

### Neutral

- **Navy Ink** sets primary text. **Slate** carries supporting copy, excerpts, labels, and metadata.
- **Warm Canvas** is the workspace background. **White Paper** holds forms, panels, tables, and dialogs. **Warm Rail** gives navigation and table headings a distinct plane.
- **Fine Rule** separates rows and regions. **Control Rule** gives inputs and outlined controls a stronger edge.

Red and pale red identify errors and destructive controls.

### Named Rules

**The Cobalt Signal Rule.** Use cobalt for actions and pale cobalt for selected, hovered, and numbered states on light surfaces.

## Typography

The regular Source Serif 4 face is self-hosted with Georgia as a fallback. Body copy and controls use Aptos, Segoe UI, and system sans-serif fallbacks.

### Hierarchy

- **Display** is the large, balanced question heading in the empty conversation. Its size contracts on narrow or short viewports.
- **Headline** is the regular serif page heading. Secondary reading surfaces use smaller serif headings, including the Sources rail and source detail dialog.
- **Title** is the compact semibold sans-serif heading for panels and records. The sticky page bar uses a compact sans-serif title.
- **Body** uses a 15px base with 1.55 line height. Answer text wraps within 72ch. The larger reading text preference increases answer and source body text to 1.125rem.
- **Label** is a compact sans-serif role for badges, counts, and supporting metadata. Controls stay in sentence case.

### Named Rules

**The Reading Hierarchy Rule.** Use serif headings to introduce a reading surface and sans-serif type for the controls, body, and records within it.

## Layout

The workspace pairs a fixed 228px navigation rail with a sticky 65px top bar. The conversation and composer share a centered column capped at 700px. The message area scrolls independently and the composer sits beneath it. A 310px Sources rail shares the desktop chat view. Record pages use wider layouts capped at 1450px.

- At 1250px and below, four-way comparisons use two columns and the upload form wraps.
- At 1050px and below, Sources moves to a right-side modal drawer with a dedicated toolbar button. Numbered citations can open it directly.
- At 720px and below, navigation moves into a left drawer, the top bar contracts to 60px, and Sources opens as a bottom sheet. Auth reorders to put the form above the example.
- At 480px and below, comparison and field layouts stack. Tables keep their columns within a horizontally scrollable container.
- At 750px viewport height and below, the welcome heading and its top spacing contract.

Inline groups commonly use 8–12px gaps. Panels and sections use 16–24px steps.

## Elevation & Depth

Warm tones and one-pixel borders establish the surface hierarchy. Panels sit flat. Modal dialogs and drawers mark their foreground with a translucent dark backdrop. Loading uses a rotating indicator and generation uses a pulsing dot, with animation suppressed for reduced-motion preferences.

### Named Rules

**The Ruled Surface Rule.** Separate persistent surfaces with tonal steps and thin rules. Use a backdrop for a modal layer.

## Shapes

Controls use gently curved corners (8px). Paper panels and tables use a 12px radius, with 14px on the composer and source detail dialog. Status chips and citation marks use tighter corners (6px and 5px). The mobile Sources sheet rounds its top corners, and avatars are circular.

## Components

### Buttons

The solid cobalt primary button carries the main action. Secondary buttons use a white fill and a stronger rule. Text actions use cobalt and underline on hover. Icon-only controls use a 42px-wide target and an accessible name. Core button variants have a 42px minimum height. Disabled buttons reduce opacity.

### Chips

Pale cobalt badges label status or show a count. A numbered citation has a smaller footprint and stays aligned with the answer text. Its interactive form turns solid cobalt on hover.

### Cards and tables

White paper panels group forms and records with one-pixel rules and a 20px inset. Tables use tinted headers, horizontal row rules, and a subtle hover tint. Evidence entries use rules in a continuous list, with pale cobalt around the selected entry.

### Inputs

Fields use white paper and a stronger border. Focus-visible adds a 2px cobalt outline with a 3px offset by default. The composer also changes its enclosing border on focus. Icon controls and visually hidden field labels retain accessible names. Errors use red text or a tinted alert with an icon and message.

### Navigation

The warm rail uses icon-and-label rows. Inactive labels use Slate, hover raises the contrast, and the current page uses pale cobalt with cobalt text. On narrow screens the same destinations appear in a modal navigation drawer. A skip link appears on keyboard focus.

### Evidence index

**The Matching Number Rule.** Pair a numbered citation in the answer with the same number on its evidence entry. Selecting the number reveals and highlights the matching excerpt.

An evidence entry includes a document title, page or excerpt label, supporting text, and a View source action. The composer accepts Enter to send and Shift+Enter for a new line. The conversation exposes polite updates and busy state during generation.

## Do's and Don'ts

### Do:

- **Do** use matching numbers in the answer and the evidence index.
- **Do** keep keyboard focus visible and give icon-only controls accessible names.
- **Do** preserve a direct path to the same excerpts when the Sources rail becomes a drawer or sheet.

### Don't:

- **Don't** add shadows to persistent paper panels or wrap every evidence entry in a separate floating card.
- **Don't** use destructive red for ordinary actions, selected navigation, or citation numbers.
