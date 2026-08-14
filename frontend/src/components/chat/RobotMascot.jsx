// Robot mascot (Story 3.1, UX-DR5): pure CSS shapes, no SVG/image. Small,
// left-aligned, overlaps the composer's top edge by 5px via `bottom-full
// -mb-[5px]` inside a `relative`-wrapped composer row. `aria-hidden` on the
// outer wrapper -- decorative and non-interactive.
export default function RobotMascot() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute left-3.5 bottom-full -mb-[5px] z-[2] w-[26px]"
    >
      <div
        className="relative mx-auto h-[5px] w-[2px] rounded-[1px] bg-robot-a
                   before:absolute before:-top-[5px] before:-left-[2px] before:h-1.5 before:w-1.5
                   before:rounded-full before:bg-robot-a before:content-['']"
      />
      <div
        className="relative mx-auto mt-px h-[18px] w-[22px] rounded-[8px_8px_6px_6px]
                   bg-[linear-gradient(160deg,var(--robot-a),var(--robot-b))]
                   shadow-[var(--robot-shadow-head)]"
      />
      <div
        className="relative mx-auto -mt-0.5 h-[13px] w-[18px] rounded-[6px_6px_8px_8px]
                   bg-[linear-gradient(160deg,var(--robot-b),var(--robot-a))]
                   shadow-[var(--robot-shadow-body)]"
      />
    </div>
  )
}
