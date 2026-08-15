// Generic two-state pill switch (Story 5.2, UX-DR13): 40x22px track, border
// colour off / primary colour on, white thumb. Not theme-specific -- takes
// checked/onChange/label like any controlled switch, so a later story can
// reuse it for another account toggle.
//
// Uses `aria-disabled` + an early return in the click handler rather than
// the native `disabled` attribute: `disabled` would pull focus away
// mid-interaction (e.g. while AppearanceCard is saving after a click), which
// is disruptive for someone driving this by keyboard. aria-disabled keeps
// the button focusable and just no-ops the action.
export default function ToggleSwitch({ checked, onChange, disabled = false, busy = false, label, labelledBy }) {
  const handleClick = () => {
    if (disabled) return
    onChange(!checked)
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-disabled={disabled}
      aria-busy={busy}
      aria-label={labelledBy ? undefined : label}
      aria-labelledby={labelledBy}
      onClick={handleClick}
      className={`relative h-[22px] w-[40px] shrink-0 rounded-full motion-safe:transition-colors motion-safe:duration-150 ${
        checked ? 'bg-primary' : 'bg-border'
      } ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
    >
      {/* The white fill alone only clears ~1.5:1 against the light theme's
          off-state track (--border #C7D2E6) -- well under WCAG 1.4.11's
          3:1 for non-text UI boundaries. The ring adds a fixed-contrast
          edge (measured ~3.6:1 against that track) independent of theme,
          so the thumb stays legible without touching the track/on colors
          DESIGN.md prescribes. */}
      <span
        className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.5)] motion-safe:transition-[left] motion-safe:duration-150 ${
          checked ? 'left-[20px]' : 'left-[2px]'
        }`}
      />
    </button>
  )
}
