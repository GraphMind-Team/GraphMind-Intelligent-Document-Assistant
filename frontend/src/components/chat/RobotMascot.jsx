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
//                 beacon. Purely decorative reinforcement: the request's
//                 real status is the visible "Thinking…" bubble and its
//                 aria-live announcement in ChatPage, never this.
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
// The character itself, decoupled from where it sits. `RobotMascot`
// below anchors it to the chat composer; the landing page's hero renders
// the same figure much larger, so there is exactly one robot in the
// codebase rather than a marketing copy that drifts from the product one.
export function RobotFigure({ state = 'idle', className = 'w-[46px]' }) {
  const isThinking = state === 'thinking'

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
