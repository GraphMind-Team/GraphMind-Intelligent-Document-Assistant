// Robot mascot (Story 3.1, UX-DR5) -- the app's one piece of character,
// redrawn for design system v2.
//
// v1 was three stacked CSS boxes. v2 is a single inline SVG so the shapes
// can actually be a *character*: antenna with a pulsing beacon, a domed
// head with a dark visor and two blinking eyes, headphone ears, a chest
// core, and an arm that waves. Inline SVG (not an asset file) keeps it
// theme-aware -- every fill below resolves from the locked `--robot-*`
// token namespace, so it re-colors with the theme instead of shipping two
// PNGs.
//
// `state`:
//   'idle'     -- slow bob, occasional blink, a wave on the arm.
//   'thinking' -- faster bob, a scan line sweeping the visor, faster
//                 beacon, and a thought bubble beside the head whose
//                 three dots ripple. Purely decorative reinforcement: the request's
//                 real status is the visible "Thinking…" bubble and its
//                 aria-live announcement in ChatPage, never this.
//   'idea'     -- the payoff beat, held for one moment after a grounded
//                 answer lands: the dot cloud is replaced by a bulb that
//                 flickers on over the same two tail puffs, then fades
//                 out. ChatPage owns the timing and drops back to 'idle';
//                 IDEA_HOLD_MS there must stay >= gm-idea's duration in
//                 index.css, or the bulb is cut off mid-fade.
//
// Every animation class is defined inside index.css's
// `prefers-reduced-motion: no-preference` block, so a user who asked for
// reduced motion gets the same robot, standing still (UX-DR28).
//
// `aria-hidden` on the outer wrapper -- decorative and non-interactive,
// contributing nothing to the accessibility tree.
//
// Shadows use drop-shadow (a filter), not box-shadow: box-shadow has
// no effect on SVG shapes. They must stay on the `--robot-shadow-head`/`--robot-shadow-body`
// tokens rather than literal rgba: those are the only two values in this
// namespace with a dark-theme override (a blue-tinted shadow reads as a
// color cast on a dark surface), and RobotMascot.test.jsx enforces it.

// The bulb's rays, as [x1, y1, x2, y2] on a circle centred at the glass
// (12, 11.4) in the bulb's own 24x24 space: inner radius 8.2 clears the
// glass's 6.2 with a visible gap, outer 10.8 keeps them inside the box.
// Listed rather than hand-drawn so the fan stays even.
const IDEA_RAYS = [
  [12, 3.2, 12, 0.6],
  [7.3, 4.7, 5.8, 2.6],
  [16.7, 4.7, 18.2, 2.6],
  [4.3, 8.6, 1.9, 7.7],
  [19.7, 8.6, 22.1, 7.7],
]

// The character itself, decoupled from where it sits. `RobotMascot`
// below anchors it to the chat composer; the landing page's hero renders
// the same figure much larger, so there is exactly one robot in the
// codebase rather than a marketing copy that drifts from the product one.
export function RobotFigure({ state = 'idle', className = 'w-[46px]' }) {
  const isThinking = state === 'thinking'
  const isIdea = state === 'idea'

  return (
    <div
      aria-hidden="true"
      className={[className, isThinking ? 'robot-thinking' : ''].join(' ')}
    >
      <div className="anim-float">
        <svg viewBox="0 0 46 52" className="w-full overflow-visible">
          <defs>
            {/* The mascot is lit by the same brand gradient as the logo
                mark and the primary button -- one identity, three places. */}
            <linearGradient id="gm-robot-head" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--robot-b)" />
              <stop offset="100%" stopColor="var(--robot-a)" />
            </linearGradient>
            <linearGradient id="gm-robot-body" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--robot-a)" />
              <stop offset="100%" stopColor="var(--robot-b)" />
            </linearGradient>
            {/* Clips the thinking-state scan line to the visor's own
                rounded rect, so the sweep can run edge to edge without
                bleeding over the head shell. */}
            <clipPath id="gm-robot-visor-clip">
              <rect x="12" y="17" width="22" height="12" rx="6" />
            </clipPath>
          </defs>

          {/* --- Thinking bubble --- */}
          {/* A little "thought cloud" that pops in beside the head while a
              request is in flight, with three dots rising in sequence --
              the same three-dot idiom as the "Thinking…" bubble in the
              transcript, so the two read as one state. Drawn outside the
              viewBox (the svg is `overflow-visible`) so adding it costs the
              mascot's layout box nothing. Decorative only: the wrapper is
              `aria-hidden`, and the real status stays the aria-live
              announcement in ChatPage. */}
          {isThinking && (
            <g className="anim-rise">
              {/* Tail: two puffs stepping up from the shoulder. */}
              <circle cx="38.5" cy="14" r="1.6" fill="var(--robot-b)" stroke="var(--robot-a)" strokeWidth="0.7" />
              <circle cx="42" cy="9.5" r="2.2" fill="var(--robot-b)" stroke="var(--robot-a)" strokeWidth="0.7" />
              {/* Cloud body. */}
              <rect x="41" y="-8" width="22" height="14" rx="7" fill="var(--robot-b)" stroke="var(--robot-a)" strokeWidth="0.9" />
              {/* Dots -- staggered so they ripple left to right. */}
              {[47, 52, 57].map((cx, i) => (
                <circle
                  key={cx}
                  cx={cx}
                  cy="-1"
                  r="1.7"
                  fill="var(--robot-visor)"
                  className="anim-dot"
                  style={{ transformOrigin: `${cx}px -1px`, animationDelay: `${i * 0.16}s` }}
                />
              ))}
            </g>
          )}

          {/* --- Idea bulb --- */}
          {/* The same two tail puffs the thought cloud uses, so the beat
              reads as the thought *becoming* an idea rather than as a
              second, unrelated bubble. The bulb itself is drawn in its own
              24x24 space and placed by one transform: scale .9 with the
              glass centre landing on (52, -1), exactly where the dot
              cloud's centre was.

              `currentColor` on every stroke is the whole trick -- gm-bulb-on
              animates `color` on the group, so one property flickers the
              glass, filament, cap and rays together. */}
          {isIdea && (
            <g className="anim-idea">
              <circle cx="38.5" cy="14" r="1.6" fill="var(--robot-b)" stroke="var(--robot-a)" strokeWidth="0.7" />
              <circle cx="42" cy="9.5" r="2.2" fill="var(--robot-b)" stroke="var(--robot-a)" strokeWidth="0.7" />

              <g transform="translate(41.2 -11.3) scale(.9)" className="anim-bulb text-accent">
                {/* Glow -- a filled disc behind the glass that blooms on
                    the flick and settles to a low haze. Filled, not
                    stroked, so it reads as light, not another outline. */}
                <circle cx="12" cy="11.4" r="6.4" fill="currentColor" opacity=".14" className="anim-bulb-glow" />

                <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <g className="anim-bulb-rays">
                    {IDEA_RAYS.map(([x1, y1, x2, y2]) => (
                      <line key={`${x1}-${y1}`} x1={x1} y1={y1} x2={x2} y2={y2} />
                    ))}
                  </g>
                  {/* Glass + shoulders: a 6.2 arc closed by two short
                      curves stepping down to the cap. */}
                  <path d="M8.4 16.5a6.2 6.2 0 1 1 7.2 0c-.7.5-1.1 1.1-1.2 1.9h-4.8c-.1-.8-.5-1.4-1.2-1.9Z" />
                  {/* Highlight -- the one detail that stops the glass
                      reading as a flat ring. */}
                  <path d="M9.1 10.9a3.4 3.4 0 0 1 1.5-2.5" strokeWidth="1.3" opacity=".75" />
                  <path d="M10.7 18.4c0-1.8.5-2.7 1.3-2.7s1.3.9 1.3 2.7" strokeWidth="1.3" />
                  {/* Screw cap, two bands. */}
                  <path d="M9.7 20.4h4.6M10.7 22.3h2.6" />
                </g>
              </g>
            </g>
          )}

          {/* --- Antenna + beacon --- */}
          <path d="M23 12V7" stroke="var(--robot-a)" strokeWidth="2" strokeLinecap="round" />
          <circle cx="23" cy="5" r="3" fill="var(--robot-a)" className="anim-pulse" style={{ transformOrigin: '23px 5px' }} />
          <circle cx="23" cy="5" r="1.6" fill="var(--robot-eye)" />

          {/* --- Headphone ears --- */}
          <rect x="4" y="19" width="5" height="9" rx="2.5" fill="var(--robot-a)" />
          <rect x="37" y="19" width="5" height="9" rx="2.5" fill="var(--robot-a)" />

          {/* --- Head shell + visor --- */}
          <g className="drop-shadow-[var(--robot-shadow-head)]">
            <rect x="8" y="11" width="30" height="24" rx="11" fill="url(#gm-robot-head)" />
            <rect x="12" y="17" width="22" height="12" rx="6" fill="var(--robot-visor)" />

            {/* Eyes. `anim-blink` squashes them on Y around their own
                centers -- transform-origin has to be stated per element
                because SVG's default origin is the viewport, not the
                shape's box. */}
            <g clipPath="url(#gm-robot-visor-clip)">
              <ellipse
                cx="18.5"
                cy="23"
                rx="2.2"
                ry="2.6"
                fill="var(--robot-eye)"
                className="anim-blink"
                style={{ transformOrigin: '18.5px 23px' }}
              />
              <ellipse
                cx="27.5"
                cy="23"
                rx="2.2"
                ry="2.6"
                fill="var(--robot-eye)"
                className="anim-blink"
                style={{ transformOrigin: '27.5px 23px' }}
              />

              {/* Thinking: a soft light sweeps across the visor. Only
                  mounted in that state, so the idle robot has no
                  perpetual motion competing with the conversation. */}
              {isThinking && (
                <rect
                  x="10"
                  y="17"
                  width="7"
                  height="12"
                  fill="var(--robot-eye)"
                  opacity="0.28"
                  className="anim-scan"
                />
              )}
            </g>

            {/* Cheek lights -- two small warm-side accents that keep the
                face from reading as a plain rectangle. */}
            <circle cx="11.5" cy="30.5" r="1.3" fill="var(--robot-b)" opacity="0.9" />
            <circle cx="34.5" cy="30.5" r="1.3" fill="var(--robot-b)" opacity="0.9" />
          </g>

          {/* --- Body --- */}
          <g className="drop-shadow-[var(--robot-shadow-body)]">
            <rect x="12" y="36" width="22" height="14" rx="7" fill="url(#gm-robot-body)" />
            {/* Chest core -- pulses in both states, the mascot's
                "powered on" tell. */}
            <circle
              cx="23"
              cy="43"
              r="3"
              fill="var(--robot-visor)"
              opacity="0.85"
            />
            <circle
              cx="23"
              cy="43"
              r="1.5"
              fill="var(--robot-eye)"
              className="anim-pulse"
              style={{ transformOrigin: '23px 43px' }}
            />

            {/* Arms. The left one hangs; the right one waves, rotated
                about its own shoulder joint. */}
            <rect x="7" y="38" width="4" height="9" rx="2" fill="var(--robot-a)" />
            <rect
              x="35"
              y="38"
              width="4"
              height="9"
              rx="2"
              fill="var(--robot-a)"
              className="anim-wave"
              style={{ transformOrigin: '37px 39px' }}
            />
          </g>
        </svg>
      </div>
    </div>
  )
}

// Chat-composer placement: small, left-aligned, overlapping the
// composer's top edge inside a `relative`-wrapped composer row.
export default function RobotMascot({ state = 'idle' }) {
  return (
    <RobotFigure
      state={state}
      className="pointer-events-none absolute left-4 bottom-full -mb-[6px] z-[2] w-[46px]"
    />
  )
}
