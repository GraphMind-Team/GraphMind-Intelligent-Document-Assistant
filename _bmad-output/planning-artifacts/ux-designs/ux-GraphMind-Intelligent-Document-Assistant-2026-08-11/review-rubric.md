# Spine Pair Review — GraphMind

## Overall verdict
The spine pair is largely source-extractable and unusually well-annotated (Open Gaps, ASSUMPTION tags, Do's/Don'ts) for a 20-day project. Two mechanical defects would trip up an automated or careless downstream consumer: a persona-name mismatch on Flow 1 (Elena vs. Maria) and four broken token references (`{color.X}` vs. the defined `{colors.X}` namespace). Component coverage is also thinner than it looks — several EXPERIENCE.md components (table rows, search bar, composer row, graph canvas, settings card) have no matching visual-spec row in DESIGN.md.Components, and the two files use different names for the same component ("Status pill" vs. "Status badge"). None of this blocks a human reader, but all of it would silently propagate into architecture/story-dev if copy-pasted or grepped verbatim. Given the compact 20-day/2-dev scope, the doc is otherwise appropriately lean rather than under-specified.

## 1. Flow coverage — thin
Sources (`prd.md`) define UJ-1 (Elena, batch upload + relational question) and UJ-2 (Marcus, deletes outdated document). Both have a Key Flow in EXPERIENCE.md, each with numbered steps, a climax beat, and a failure/edge path.
### Findings
- **critical** Flow 1's protagonist is named "Maria" throughout (title and all 9 steps), but the PRD's UJ-1 names the persona "Elena" (`prd.md` §2.3, line 40-46). This isn't a stylistic variant — it reads as a different persona and breaks verbatim inheritance. (EXPERIENCE.md § Key Flows, "Flow 1 — First trustworthy answer (Maria...)"). *Fix:* rename to Elena throughout Flow 1, or add an explicit note if the rename was intentional.
- **medium** UJ-1's climax is specifically about graph-traversal synthesis across multiple documents ("something a single-document search couldn't produce" — the relational-question payoff that motivates the Knowledge Graph). Flow 1's climax beat (step 9) only cites chapter/document-level citations and doesn't call out the cross-document graph-traversal aspect that makes UJ-1 distinct from a plain single-doc RAG answer. (EXPERIENCE.md, Flow 1 step 9). *Fix:* tie the climax language back to the relational/multi-document synthesis UJ-1 is testing for.

## 2. Token completeness — strong
Every color in the YAML frontmatter has a hex value, and every semantic color that needs one has a light/dark pair (bg, surface, border, text, text2, primary, accent, success, warning, danger, citation, robot-a/b are explicitly single-namespace by design). Typography, rounded, spacing, and component tokens are all defined with concrete values or valid `{path.to.token}` references within DESIGN.md itself. Contrast ratios are stated for load-bearing dark-mode text/primary combinations.
### Findings
- None within DESIGN.md itself.

## 3. Component coverage — thin
DESIGN.md.Components lists: Sidebar nav, Robot mascot, Citation chip, Chat bubbles, Status pill, Buttons, Modal, Dropzone, Toggle switch. EXPERIENCE.md.Component Patterns lists 14 rows, several of which have no counterpart visual spec in DESIGN.md.
### Findings
- **high** No visual spec exists in DESIGN.md.Components for: Document table row (no table styling at all, despite Documents being a full-width-table core surface), Document Detail panel, Document search bar, Documents-in-scope panel, Chat composer row, Graph canvas (only an incidental shadow note in Elevation & Depth, no color/size/label spec), Settings card. Downstream implementers have behavior but not appearance for these. (DESIGN.md § Components; cf. EXPERIENCE.md § Component Patterns). *Fix:* add DESIGN.md rows for at least the table, composer row, and graph canvas — the three most build-critical surfaces lacking visual specs.
- **medium** Naming mismatch: DESIGN.md calls the ingestion-state component `{components.status-pill}` / "Status pill"; EXPERIENCE.md calls the identical component "Status badge" throughout (Component Patterns and State Patterns tables). (DESIGN.md § Components vs. EXPERIENCE.md § Component Patterns). *Fix:* align on one name, e.g. "Status pill," in both files.

## 4. State coverage — adequate
IA surfaces are walked in EXPERIENCE.md § State Patterns: empty library, Uploaded/Extracting/Graphing, Ready, Failed, delete confirmation, grounded answer, refusal, upload-in-progress, modal-open, page-level loading. Gaps are honestly flagged rather than invented: Failed, refusal, and empty-library states are explicitly marked [ASSUMPTION]/"Open gap" with no mock, consolidated in an "Open Gaps" section at the end.
### Findings
- **low** Focus/keyboard states and hover states for interactive elements (row hover, trash-icon hover, checkbox focus) are not itemized as their own state-pattern rows, though the Accessibility Floor section partially compensates (focus-ring visibility requirement). Given the 20-day scope this is a reasonable omission, not flagged higher.

## 5. Visual reference coverage — strong
`mockups/` contains exactly three files: `key-screens-light.html`, `key-screens-dark.html`, `color-theme-options.html`. All three are linked inline — the two key-screens files from both DESIGN.md (Brand & Style) and EXPERIENCE.md (Foundation/IA), and `color-theme-options.html` from DESIGN.md as an explicitly-labeled "exploration record" (i.e., correctly scoped as non-authoritative history, not a live source). `imports/` is empty; no `wireframes/` directory exists. Both files state "spine wins on conflict" near their mock links. No orphans found.
### Findings
- None.

## 6. Bloat & overspecification — adequate
DESIGN.md carries editorial voice appropriately (palette-iteration narrative, robot-mascot backstory) which the rubric explicitly permits. EXPERIENCE.md is largely behavioral and table-driven, as required, though a few spots drift into DESIGN.md's territory.
### Findings
- **low** EXPERIENCE.md § Component Patterns restates visual details already owned by DESIGN.md in a few rows (e.g. Chat message bubble row describes fill colors and corner-radius direction that duplicate DESIGN.md § Components' Chat bubbles entry almost verbatim). Not harmful since both agree, but it's restatement rather than new behavioral information. *Fix:* trim to the behavioral delta (alignment, sender cue) and point to DESIGN.md for fill/radius.
- **low** DESIGN.md's robot-mascot paragraph (§ Components) is long relative to its downstream importance (a decorative, aria-hidden element) — includes iteration history (baby-pink experiment, full-body-shifted-right) that a story-dev consumer doesn't need to action. Acceptable as brand-voice color given DESIGN.md's stated allowance for editorial prose, but borderline.

## 7. Inheritance discipline — thin
`sources` frontmatter in EXPERIENCE.md resolves to real files (`prd.md`, `addendum.md`, verified to exist). Glossary terms (Uploaded/Extracting/Graphing/Ready/Failed) are used verbatim from FR-4 in both Voice and Tone and State Patterns. However token-reference resolution and one persona name break here.
### Findings
- **critical** Four token references in EXPERIENCE.md use the singular `{color.X}` namespace instead of DESIGN.md's actual `{colors.X}` (plural) namespace: `{color.primary}` and `{color.surface}` (Chat message bubble row), `{color.citation}` (Citation chip row), `{color.danger}` (Settings card row). None of these resolve to a token DESIGN.md actually defines — DESIGN.md's frontmatter key is `colors:` and all its own prose consistently uses `{colors.*}`. (EXPERIENCE.md § Component Patterns, lines ~61-67). *Fix:* rename all four to `{colors.primary}`, `{colors.surface}`, `{colors.citation}`, `{colors.danger}`.
- **critical** See Flow coverage finding #1 — UJ-1's persona is "Elena" in the PRD source but "Maria" throughout EXPERIENCE.md Flow 1, breaking verbatim UJ inheritance.

## 8. Shape fit — strong
DESIGN.md sections appear in canonical order: Brand & Style → Colors → Typography → Layout & Spacing → Elevation & Depth → Shapes → Components → Do's and Don'ts. EXPERIENCE.md carries all required defaults (Foundation, IA, Voice and Tone, Component Patterns, State Patterns, Interaction Primitives, Accessibility Floor, Key Flows) plus an extra "Open Gaps" section, which earns its place — it's the honest, load-bearing summary of the three flagged-but-undesigned states and is genuinely useful to a downstream consumer deciding what still needs a design pass. Inspiration/Responsive sections are correctly omitted (no reference-product citations beyond the NotebookLM structural nod already covered in Brand & Style; product is explicitly web-only/desktop-first with no breakpoints per Layout & Spacing).
### Findings
- None.

## Mechanical notes
- Broken token references (namespace typo `{color.*}` vs `{colors.*}`): EXPERIENCE.md § Component Patterns, 4 occurrences (see Inheritance discipline).
- Name inconsistency: "Status pill" (DESIGN.md) vs. "Status badge" (EXPERIENCE.md) for the same component.
- Persona-name inconsistency: "Maria" (EXPERIENCE.md Flow 1) vs. "Elena" (PRD UJ-1).
- No Mermaid diagrams present in either file — nothing to validate there.
- Frontmatter: DESIGN.md's YAML frontmatter is complete and well-formed; EXPERIENCE.md's frontmatter (title/status/created/updated/sources) resolves correctly, both source paths exist on disk.
