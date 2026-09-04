# Frontend style

This contributor guide applies to changes under `src/webapp/templates/` and
`src/webapp/static/`. Read it before introducing or modifying a shared visual pattern.

Django Probe's interface is utilitarian, technical, and content-first. It should feel
like a precise companion to a CI tool rather than a marketing site or an
application dashboard. A small satellite (`🛰️`) is the Probe brand motif; always
pair it with the Django Probe name and never make the emoji carry the identity alone.

The implementation lives in `src/webapp/static/css/probe.css`. Prefer its existing
tokens and components over template-local styles. Add a token only when a value is
reused or has semantic meaning.

Staff users can review the living component catalog at `/style-guide/`. Keep that page
in sync when a shared token or component changes; examples should use production
classes rather than recreating their appearance.

## Foundations

- **Typography:** Use the system sans-serif stack for interface and prose. Use the
  system monospace stack for commands, tokens, identifiers, version numbers, and
  compact technical labels. Keep body text at the browser default and line height at
  `1.6`; hierarchy comes from weight, spacing, and a small type scale.
- **Color:** The canvas is warm off-white, text is near-black green, and one restrained
  green family handles links, actions, focus, and active navigation. Neutral green-gray
  surfaces and borders separate content. Error and warning colors are reserved for
  their meanings. Text and controls must meet WCAG AA contrast; do not communicate
  state by color alone.
- **Spacing:** Use the `--space-1` through `--space-7` scale. Default component spacing
  is `--space-4`; section spacing is `--space-6` or `--space-7`. Avoid one-off pixel
  values.
- **Shape:** Use the single `--radius` token. Borders, not shadows, establish structure.
  The content column is capped at `--content-width` to keep prose and forms readable.

## Components

- **Layout and navigation:** Every page extends `base.html`, uses the shared container,
  and has one `h1`. Navigation stays shallow, shows the current page in text plus an
  underline, and wraps on narrow screens. Keep primary content before secondary links.
- **Forms:** Put labels above controls and leave Django's help and error text visible.
  Inputs use the shared full-width style but retain a readable maximum width. Every
  form has an explicit submit button; do not rely on placeholders as labels.
- **Buttons:** Solid green is the primary action. Use `.button--secondary` for a
  lower-priority link rendered as a control. Prefer ordinary links for navigation.
  Limit each section to one visually primary action.
- **Panels and empty states:** `.panel` groups a short, meaningful unit. Add
  `.panel--subtle` for neutral support content and `.panel--caution` for a genuine
  warning. Empty states explain what is absent and give one practical next step.
- **Messages:** Django messages use `.message` and a semantic modifier. Keep them brief
  and actionable. Errors and warnings have both color and a stronger border.
- **Lists:** `.item-list` is for repeated records; each item has a clear title and
  quieter `.item-list__meta`. Do not turn short lists into grids or dashboard cards.
- **Code:** Inline code identifies exact values. Fenced command blocks use the dark
  code surface and must scroll horizontally rather than shrink or wrap commands.

## Responsive and accessible behavior

Build narrow-screen behavior into the base component: the header stacks, navigation
wraps, and grouped actions become full-width below `40rem`. Do not hide content or
actions by viewport size. Preserve semantic HTML, keyboard-visible focus, the skip
link, minimum 44px control height, and reduced-motion preferences. Emoji used as the
brand motif is decorative and must be hidden from assistive technology.

Before introducing a new visual pattern, check whether plain prose, a link, a panel,
or an item list already expresses the content. Reports, charts, and dashboard layouts
are outside this interface unless the product itself gains that requirement.

## Contributor checklist

Before opening a pull request that changes the frontend:

1. Reuse tokens and components from `probe.css` before adding a new pattern.
2. Extend `base.html`, preserve one page-level `h1`, and use semantic elements before
   adding classes or JavaScript behavior.
3. Check the page at narrow and wide viewport sizes, using both keyboard and pointer
   input. Verify that focus remains visible and no content or action disappears.
4. Update `/style-guide/` when a shared token or component changes.
5. Run the webapp tests and lint checks:

   ```console
   $ just test -m webapp
   $ just lint
   ```

Keep changes small enough that reviewers can compare them against these conventions.
If a product requirement needs a new pattern, explain that requirement in the pull
request rather than generalizing the interface preemptively.
