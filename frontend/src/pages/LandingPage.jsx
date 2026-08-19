import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { RobotFigure } from '../components/chat/RobotMascot'

// Public landing page -- the app's front door.
//
// Before this, `/` was the Register form itself, so the first thing a
// visitor saw was a signup box with no explanation of what they'd be
// signing up for, and there was no public URL that described the product
// at all. The conventional shape (and the one every comparable product
// uses) is: `/` is a public page that explains the thing, with Log in /
// Get started as its two calls to action; the forms live at their own
// URLs; everything else stays behind the auth gate. That's what this is.
//
// The route is public to *everyone*, signed in or not -- a landing page a
// logged-in user gets bounced off is a broken link every time they click
// their own logo. Instead the header's primary action swaps to "Open
// workspace" for an authenticated visitor, which is why this component
// reads `isAuthenticated` rather than sitting under PublicOnlyRoute.

function FeatureIcon({ children }) {
  return (
    <span
      aria-hidden="true"
      className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-[image:var(--grad-brand-soft)] text-primary"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-5 w-5"
      >
        {children}
      </svg>
    </span>
  )
}

const FEATURES = [
  {
    title: 'Upload anything',
    body: 'Drop in PDFs, docs and notes. GraphMind extracts the text, chapter by chapter, and tracks every file through ingestion.',
    icon: (
      <>
        <path d="M12 16V4" />
        <path d="M7.5 8.5 12 4l4.5 4.5" />
        <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      </>
    ),
  },
  {
    title: 'Answers with receipts',
    body: 'Every answer is grounded in your own documents and carries citation chips back to the exact chapter it came from. No evidence, no answer.',
    icon: (
      <>
        <path d="M20 14a3 3 0 0 1-3 3H8l-4 3V7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3Z" />
        <path d="M9 10.5h6M9 13.5h3.5" />
      </>
    ),
  },
  {
    title: 'See the connections',
    body: 'People, organizations, projects, products and places are pulled out into a live knowledge graph you can explore — or read as a list.',
    icon: (
      <>
        <circle cx="6" cy="7" r="2.4" />
        <circle cx="18" cy="9" r="2.4" />
        <circle cx="11" cy="18" r="2.4" />
        <path d="M8.2 8.2 15.7 9M7.2 9.2 10 15.7M16.6 11.1 12.6 16.4" />
      </>
    ),
  },
]

const STEPS = [
  { n: '01', title: 'Add your documents', body: 'Upload one file or a whole folder. Watch each one move from Uploaded to Ready.' },
  { n: '02', title: 'Ask in plain language', body: 'Narrow the scope to the documents you care about, then just ask.' },
  { n: '03', title: 'Follow the evidence', body: 'Open any citation to land on the source, or jump to the graph to see how it all connects.' },
]

export default function LandingPage() {
  const { isAuthenticated } = useAuth()

  return (
    <div className="app-aurora min-h-screen">
      {/* Sticky glass header -- logo home-link on the left, the two
          actions on the right. */}
      <header className="sticky top-0 z-10 px-4 pt-4">
        <div className="glass mx-auto flex max-w-6xl items-center justify-between gap-4 rounded-2xl px-4 py-3 shadow-card">
          <Link to="/" className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="relative block h-8 w-8 shrink-0 rounded-[11px] bg-[image:var(--grad-brand)] shadow-[var(--glow)] after:absolute after:inset-2 after:rounded-full after:border-2 after:border-white after:content-['']"
            />
            <span className="font-display text-[16px] font-bold text-text">GraphMind</span>
          </Link>

          <nav aria-label="Account" className="flex items-center gap-2">
            {isAuthenticated ? (
              <Link
                to="/documents"
                className="btn-brand rounded-full px-5 py-2.5 text-[13px] font-semibold"
              >
                Open workspace
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="rounded-full px-4 py-2.5 text-[13px] font-semibold text-text2 hover:text-primary"
                >
                  Log in
                </Link>
                <Link
                  to="/register"
                  className="btn-brand rounded-full px-5 py-2.5 text-[13px] font-semibold"
                >
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>
        {/* ---- Hero ---- */}
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-16 sm:py-24 min-[900px]:grid-cols-[1.15fr_1fr]">
          <div className="anim-rise">
            <p className="text-eyebrow uppercase text-accent">Grounded document intelligence</p>
            <h1 className="mt-3 font-display text-[clamp(34px,5vw,54px)] leading-[1.05] font-bold text-text">
              Your documents,
              <br />
              <span className="bg-[image:var(--grad-brand)] bg-clip-text text-transparent">
                finally answering back.
              </span>
            </h1>
            <p className="mt-5 max-w-[52ch] text-[16px] leading-relaxed text-text2">
              GraphMind reads everything you upload, maps who and what is connected to what, and
              answers your questions using only what your own documents actually say — with a
              citation on every claim.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to={isAuthenticated ? '/documents' : '/register'}
                className="btn-brand rounded-full px-7 py-3.5 text-[14px] font-semibold"
              >
                {isAuthenticated ? 'Open workspace' : 'Create your account'}
              </Link>
              {!isAuthenticated && (
                <Link
                  to="/login"
                  className="btn-ghost rounded-full px-7 py-3.5 text-[14px] font-semibold"
                >
                  I already have one
                </Link>
              )}
            </div>

            <p className="mt-5 text-[13px] text-text2">
              No answer without evidence — if your documents don't support it, GraphMind says so.
            </p>
          </div>

          {/* Hero figure: the product's own mascot, at size, sitting in a
              mock answer card so the hero shows the actual interaction
              rather than a stock illustration. */}
          <div className="anim-rise relative mx-auto w-full max-w-[420px]">
            <div className="rounded-2xl border border-border bg-card-bg p-6 shadow-modal">
              <div className="flex items-start gap-4">
                <RobotFigure className="w-[72px] shrink-0" />
                <div className="min-w-0 flex-1 space-y-3">
                  <p className="ml-auto w-fit max-w-full rounded-[20px_20px_6px_20px] bg-[image:var(--grad-brand)] px-4 py-2.5 text-[13.5px] text-white shadow-[var(--glow)]">
                    Who owns the migration project?
                  </p>
                  <p className="rounded-[20px_20px_20px_6px] border border-border bg-surface px-4 py-3 text-[13.5px] leading-relaxed text-text">
                    Priya Raman leads it, with Platform Engineering as the owning team.
                    <span className="ml-1.5 inline-block rounded-full bg-citation px-2 py-[3px] text-[11px] font-bold text-citation-text">
                      Q3-plan.pdf · Ch. 2
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ---- Features ---- */}
        <section className="mx-auto max-w-6xl px-6 py-10">
          <h2 className="font-display text-section-title text-text">What you get</h2>
          <ul className="mt-8 grid gap-5 min-[700px]:grid-cols-3">
            {FEATURES.map((feature) => (
              <li
                key={feature.title}
                className="card-lift rounded-2xl border border-border bg-card-bg p-6 shadow-card"
              >
                <FeatureIcon>{feature.icon}</FeatureIcon>
                <h3 className="font-display text-[17px] font-bold text-text">{feature.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-text2">{feature.body}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* ---- How it works ---- */}
        <section className="mx-auto max-w-6xl px-6 py-14">
          <h2 className="font-display text-section-title text-text">How it works</h2>
          <ol className="mt-8 grid gap-5 min-[700px]:grid-cols-3">
            {STEPS.map((step) => (
              <li key={step.n} className="rounded-2xl border border-border bg-surface2 p-6">
                <span
                  aria-hidden="true"
                  className="font-display text-[28px] font-bold bg-[image:var(--grad-brand)] bg-clip-text text-transparent"
                >
                  {step.n}
                </span>
                <h3 className="mt-2 font-display text-[16px] font-bold text-text">{step.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-text2">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ---- Closing call to action ---- */}
        <section className="mx-auto max-w-6xl px-6 pb-20">
          <div className="relative overflow-hidden rounded-2xl bg-[image:var(--grad-brand)] px-8 py-14 text-center shadow-modal">
            <h2 className="font-display text-[clamp(24px,3.2vw,34px)] font-bold text-white">
              Start asking your documents questions.
            </h2>
            <p className="mx-auto mt-3 max-w-[54ch] text-[15px] text-white/85">
              Free to set up. Your library, your answers, your evidence.
            </p>
            <Link
              to={isAuthenticated ? '/documents' : '/register'}
              className="mt-7 inline-block rounded-full bg-white px-7 py-3.5 text-[14px] font-bold text-primary shadow-card"
            >
              {isAuthenticated ? 'Open workspace' : 'Get started free'}
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border px-6 py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 text-[13px] text-text2">
          <span>© {new Date().getFullYear()} GraphMind</span>
          <span className="flex gap-4">
            <Link to="/login" className="hover:text-primary">
              Log in
            </Link>
            <Link to="/register" className="hover:text-primary">
              Create account
            </Link>
          </span>
        </div>
      </footer>
    </div>
  )
}
