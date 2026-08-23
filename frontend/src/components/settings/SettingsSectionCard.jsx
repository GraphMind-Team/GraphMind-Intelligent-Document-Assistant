import Icon from '../Icon'

// Shared chrome for every Settings row (Profile, Change Password,
// Appearance, Language, Delete Account): an icon badge + title + one-line
// description on top, with each card's own control/form below. Pulled out
// because all five cards would otherwise duplicate the exact same header
// markup with only the icon and danger-tint differing -- genuine
// repetition, not just incidental similarity between unrelated code.
//
// `danger` swaps the whole card to the danger-tinted treatment (Delete
// Account only) -- the same `border-danger/30 bg-danger/5` pairing this
// app already uses for inline error banners (DocumentsPage.jsx,
// GraphPage.jsx), so a destructive section reads as visually distinct
// without inventing a new color pairing just for it.
export default function SettingsSectionCard({ icon, title, description, danger = false, className = '', children }) {
  return (
    <section
      className={[
        'rounded-2xl border p-6 shadow-card',
        danger ? 'border-danger/30 bg-danger/5' : 'border-border bg-card-bg',
        className,
      ].join(' ')}
    >
      <div className="flex items-start gap-3.5">
        <span
          aria-hidden="true"
          className={[
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
            danger ? 'bg-danger/10 text-danger' : 'bg-[image:var(--grad-brand-soft)] text-accent',
          ].join(' ')}
        >
          <Icon className="h-5 w-5">{icon}</Icon>
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <h2 className="text-base font-bold text-text">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-text2">{description}</p>}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}
