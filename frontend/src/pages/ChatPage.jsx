import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { useChatSessions } from '../context/ChatSessionsContext'
import { ChatScopeProvider, useChatScope } from '../context/ChatScopeContext'
import { askQuestion, editMessage, getChatHistory } from '../api/chatClient'
import ChatMessage from '../components/chat/ChatMessage'
import RobotMascot, { RobotFigure } from '../components/chat/RobotMascot'
import DocumentsScopePanel from '../components/chat/DocumentsScopePanel'
import ChatSearchPanel from '../components/chat/ChatSearchPanel'
import ChatSessionsPanel from '../components/chat/ChatSessionsPanel'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'

// UX-DR29/Story 3.4: one page size for both the initial load and every
// scroll-up page after it.
const HISTORY_PAGE_LIMIT = 10

// Search-match navigation and "jump to latest" both move the scroller
// programmatically -- UX-DR28 gates every other animation in this app
// behind prefers-reduced-motion (index.css), so a smooth scrollIntoView/
// scrollTo here must be gated the same way rather than silently animating
// motion the user's OS setting asked for none of.
function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

// How long the mascot holds a post-answer beat ('idea' or 'noAnswer')
// before dropping back to idle. Both beats share the gm-idea envelope in
// index.css, so one constant covers both; it must stay >= that
// keyframes' duration, or the mascot is unmounted mid-fade and snaps out
// instead of drifting out.
const MASCOT_BEAT_HOLD_MS = 2000

// One persisted `ChatHistoryMessageResponse` row -> the same message shape
// `ChatMessage.jsx` already renders for a live turn (`askQuestion`'s
// response, shaped by ChatPage's own handleSubmit below) -- a returning
// visit must render identically to how the turn looked live, including a
// refusal's own dedicated bubble and a notice's own reason-specific copy,
// never a generic "assistant" fallback for either.
function toUiMessage(row) {
  if (row.role === 'user') {
    return { role: 'user', id: row.id, text: row.question }
  }
  if (row.empty_reason === 'refusal') {
    return { role: 'refusal' }
  }
  if (row.empty_reason) {
    return { role: 'notice', reason: row.empty_reason }
  }
  return { role: 'assistant', id: row.id, segments: row.segments ?? [], feedback: row.feedback ?? null }
}

// Every piece of user-visible text in one message, flattened for the
// chat search filter. Notice/refusal/thinking bubbles have no text of
// their own here (their copy lives in ChatMessage.jsx) -- they simply
// never match a query, which is the honest outcome: there is nothing of
// the user's to find in them.
function messageSearchText(message) {
  if (message.role === 'user') return message.text ?? ''
  if (message.role === 'assistant') {
    return (message.segments ?? [])
      .map((segment) => segment.text ?? '')
      .join(' ')
  }
  return ''
}

// Chat page (Story 3.1): a three-column grid -- fixed 260px chats panel +
// flexible chat window (1fr) + fixed 260px documents-in-scope panel, 20px
// gutter (UX-DR9). Collapses to a single column below 900px so the
// fixed-width columns (this page's two panels plus Shell's 220px sidebar)
// can't force horizontal scroll/clipping at 200% browser zoom on a typical
// laptop viewport (AC2, WCAG 1.4.4, UX-DR28) -- both side panels keep DOM
// order == visual order (no CSS `order`/`row-reverse`), mirroring Shell.jsx's
// own UX-DR18 convention: the chats panel sits first in DOM so it stacks
// above the chat column, the documents panel sits last so it stacks below.
//
// Split into this thin wrapper + ChatPageContent (Story 3.3) because
// ChatPageContent needs `useChatScope()`, which reads the context this
// component renders -- a single component can't call a hook that reads a
// provider it renders itself, that provider isn't mounted yet at the
// point its own render function runs.
//
// Multi-session chat: `sessionId` comes from the route (`/chat/:sessionId`,
// this page's own App.jsx entry) and is passed to `ChatPageContent` both
// as a prop and as its React `key`. The `key` is load-bearing, not
// decorative -- React Router does not remount this element on a
// param-only navigation (switching sessions via ChatSessionsPanel), but
// `ChatPageContent` owns close to a dozen pieces of session-scoped local
// state/refs (`messages`, `historyCursor`, `hasMoreHistory`,
// `isLoadingHistory`, `historyPrependToken`, `liveAnnouncementsEnabled`,
// `isLoadingHistoryRef`, `hasSubmittedLiveQuestionRef`,
// `pendingScrollAdjustmentRef`, `activeMatchOrdinal`) that must all reset
// to their initial values on every session switch, not carry the
// previous session's thread over. Keying on `sessionId` forces exactly
// that clean remount instead of threading a manual reset effect through
// every one of them.
export default function ChatPage() {
  const { sessionId } = useParams()
  return (
    <ChatScopeProvider>
      <ChatPageContent key={sessionId} sessionId={sessionId} />
    </ChatScopeProvider>
  )
}

function ChatPageContent({ sessionId }) {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const { refresh: refreshSessions } = useChatSessions()
  const { selectedDocumentIds, selectAll } = useChatScope()
  // DocumentDetailPage's "Ask about this document" link arrives here with
  // `{ presetDocumentId }` in navigation state -- picked up once below,
  // as soon as the scope panel's own document list confirms that id is
  // actually Ready (a Pending/Failed one can't be selected, same as the
  // scope panel's own checkboxes).
  const location = useLocation()
  const presetDocumentId = location.state?.presetDocumentId ?? null
  const hasAppliedPresetRef = useRef(false)
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  // Chat-history search (right column). Filters `messages` at render
  // time only -- the thread state itself is never narrowed, so history
  // paging, scroll restore and submit all keep working against the full
  // list while a query is active.
  const [chatSearch, setChatSearch] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  // A slow answer is normally just LLM latency, but the backend itself
  // can also be a Render cold start (see useSlowRequestHint) -- either
  // way, "Thinking…" alone reads the same as a hang past a few seconds.
  const isSlowToAnswer = useSlowRequestHint(isAsking)
  // Reported up by DocumentsScopePanel once its own fetch resolves (it
  // already owns the document list -- this mirrors it rather than
  // duplicating the fetch). `null` means "not known yet", which the
  // welcome placeholder below (and the preset-scope effect) treat the
  // same as "still loading".
  const [scopeDocuments, setScopeDocuments] = useState(null)
  const documentCount = scopeDocuments ? scopeDocuments.length : null

  // Applies the incoming preset once the scope panel's document list has
  // loaded -- not on `presetDocumentId` alone, since that's known
  // immediately but the id can't be validated (or selected -- `selectAll`
  // just overwrites `selectedDocumentIds` outright) until the real list
  // is in. `hasAppliedPresetRef` makes this a one-time thing per mount:
  // without it, a later scope-panel refetch (there isn't one today, but
  // nothing guarantees that stays true) would silently re-clobber
  // whatever the user had since selected by hand back down to just the
  // preset document.
  useEffect(() => {
    if (!presetDocumentId || hasAppliedPresetRef.current || !scopeDocuments) return
    const target = scopeDocuments.find((doc) => doc.id === presetDocumentId)
    if (target && target.status === 'Ready') {
      selectAll([presetDocumentId])
    }
    hasAppliedPresetRef.current = true
  }, [presetDocumentId, scopeDocuments, selectAll])
  // { kind: 'service' | 'other', message } -- a 503 (or client-side
  // timeout/abort) renders as a banner here, structurally separate from
  // `messages`, so it can never render as an answer or a refusal (AC12).
  const [error, setError] = useState(null)
  // Purely decorative: drives the mascot's one post-answer beat and
  // nothing else -- 'idea' for a grounded answer, 'noAnswer' for a notice
  // (no documents / empty scope / no matching content), null the rest of
  // the time. A single field rather than two booleans so the two beats
  // can never both be "on" at once fighting over the mascot. Deliberately
  // not derived from `messages` -- it is a moment in time, not a property
  // of the transcript, so re-renders (a history page loading in, say)
  // must not re-trigger it.
  const [mascotBeat, setMascotBeat] = useState(null)
  const mascotBeatTimerRef = useRef(null)
  const messageListRef = useRef(null)

  // The timer outlives the render that set it, so it has to be cancelled
  // on unmount -- otherwise navigating away mid-beat leaves a setState
  // aimed at a gone component.
  useEffect(() => () => clearTimeout(mascotBeatTimerRef.current), [])

  // Starts (or restarts) a beat and schedules its own return to idle.
  // Restarting clears whatever timer was already running, so a beat from
  // a stale, still-in-flight turn can never fire after a newer one has
  // already taken over the mascot.
  function triggerMascotBeat(beat) {
    clearTimeout(mascotBeatTimerRef.current)
    setMascotBeat(beat)
    mascotBeatTimerRef.current = setTimeout(() => setMascotBeat(null), MASCOT_BEAT_HOLD_MS)
  }

  // Story 3.4/AD-10: pagination state for revealing older history as the
  // user scrolls up. `historyCursor`/`hasMoreHistory` come straight off
  // the backend's own `next_cursor`/`has_more` -- this page never
  // computes pagination state itself, only relays what the last page
  // said. `isLoadingHistory` drives visible/`aria-busy` UI state;
  // `isLoadingHistoryRef` (below) is the actual reentrancy guard, since a
  // state setter's own update isn't visible synchronously to a second
  // overlapping call.
  const [historyCursor, setHistoryCursor] = useState(null)
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  // Set once the mount-time history fetch below settles (success or
  // failure) -- gates the empty-thread welcome placeholder so a returning
  // user with real history never sees it flash before their messages
  // arrive.
  const [isInitialHistoryLoaded, setIsInitialHistoryLoaded] = useState(false)
  // Governs the message list's own `aria-live` value -- 'polite' by
  // default (so a screen reader hears a genuinely new answer land), but
  // switched to 'off' once history has just been revealed (initial load
  // or a scroll-up page) and left there until the next question is
  // actually asked (handleSubmit flips it back). Deliberately not an
  // auto-reverting timer: the moment that matters for a screen reader is
  // "was aria-live already 'off' at the instant the DOM changed", and a
  // permanent-until-the-next-real-question value is what guarantees that
  // without racing a timeout against React's own commit/paint timing.
  const [liveAnnouncementsEnabled, setLiveAnnouncementsEnabled] = useState(true)
  // Synchronous reentrancy guard for `loadOlderHistory` -- a second
  // overlapping scroll event firing before `setIsLoadingHistory(true)`'s
  // own update has actually committed (state setters are async) would
  // otherwise start a second, duplicate fetch/prepend. Checked and set
  // synchronously, in addition to (not instead of) the `isLoadingHistory`
  // state, which still drives the visible/`aria-busy` UI below.
  const isLoadingHistoryRef = useRef(false)
  // Set once `handleSubmit` appends this page's first live turn --
  // guards the initial-mount history fetch (which can resolve *after*
  // that happens, e.g. on a slow/blip-y connection) from clobbering the
  // live conversation already on screen with whatever it fetched. Once a
  // live question has been asked this render, the mount fetch's own
  // result is stale and must be discarded, not seeded.
  const hasSubmittedLiveQuestionRef = useRef(false)
  // Incremented exactly once per successful history-prepend (never for a
  // live append) -- the dedicated scroll-restore layout effect below is
  // keyed on this value alone, not on `messages` generally, so it only
  // ever runs in the same commit as the prepend that produced it and
  // never misfires against an unrelated live-append update that happens
  // to land in the same render pass.
  const [historyPrependToken, setHistoryPrependToken] = useState(0)
  const pendingScrollAdjustmentRef = useRef(null)

  // Chat-search match navigation. The thread is never narrowed to matches
  // anymore (see `chatSearchNeedle`/`matchedIndices` below) -- instead the
  // prev/next arrows in ChatSearchPanel step `activeMatchOrdinal` through
  // `matchedIndices` and scroll the corresponding bubble into view, so a
  // match is always read with its surrounding conversation still on
  // screen. `messageRefs` holds one DOM node per message, keyed by its
  // full-thread index (the same index `messages.map` below keys on), so a
  // given ordinal can be turned into an element to scroll to.
  const [activeMatchOrdinal, setActiveMatchOrdinal] = useState(0)
  const messageRefs = useRef(new Map())

  // Tracks whether the message list is scrolled to (near) its own bottom,
  // purely to decide whether the floating "jump to latest" button below is
  // shown -- jumping to a match earlier in the thread is exactly the
  // moment a quick way back to the live edge of the conversation matters.
  const [isNearBottom, setIsNearBottom] = useState(true)

  // Initial load (UX-DR29): fetch only the most recent page, not the full
  // thread -- `getChatHistory` returns them newest-first, so `.reverse()`
  // restores the chronological (oldest-first) order this page renders
  // messages in. A failed fetch surfaces through the same `error` banner
  // `handleSubmit` already uses (not swallowed silently) -- a network blip
  // on load must look like a network blip, not an account with an empty
  // conversation. The Ask flow itself still isn't blocked either way:
  // `messages` simply stays `[]` until the user asks something new.
  useEffect(() => {
    let cancelled = false
    getChatHistory(authFetch, sessionId, { limit: HISTORY_PAGE_LIMIT })
      .then((page) => {
        if (cancelled) return
        const seeded = page.messages.slice().reverse().map(toUiMessage)
        if (seeded.length > 0) {
          // This is a history reveal, not a new incoming answer -- must
          // not announce (Story 3.4's own aria-live requirement applies
          // to the initial load exactly as it does to a scroll-up page).
          setLiveAnnouncementsEnabled(false)
          // Prepended, not assigned. The user may have already asked (and
          // gotten an answer to) a live question while this fetch was in
          // flight, in which case `previous` already holds that turn; a
          // bare `setMessages(seeded)` would silently drop it. The
          // functional prepend makes clobbering impossible by
          // construction, which is strictly stronger than the
          // `hasSubmittedLiveQuestionRef` bail-out it replaces -- and
          // that bail-out also skipped the two setters below, leaving
          // `hasMoreHistory` false for the rest of the session, i.e.
          // silently killing history reveal entirely for exactly the
          // users who had history to reveal. On the ordinary path
          // `previous` is `[]`, so this is identical to an assignment.
          setMessages((previous) => [...seeded, ...previous])
        }
        // Recorded unconditionally: this is the anchor for every older
        // page, and losing it is unrecoverable without a reload.
        setHistoryCursor(page.next_cursor)
        setHasMoreHistory(page.has_more)
      })
      .catch((err) => {
        // Still guarded: a failed *background* fetch must not throw an
        // error banner over a conversation the user is actively using and
        // that is plainly working. Only the messages path needed the
        // stronger structural fix above.
        if (cancelled || hasSubmittedLiveQuestionRef.current) return
        setError({ kind: err.isServiceError ? 'service' : 'other', message: err.message })
      })
      .finally(() => {
        if (!cancelled) setIsInitialHistoryLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch, sessionId])

  // Keeps the newest message (or the transient "Thinking…" bubble) in
  // view without requiring the user to scroll manually -- a real question
  // during review: a 20-40s wait is already disorienting, and without
  // this the answer (or even "Thinking…" itself) can land below the fold
  // and look like nothing happened. `useLayoutEffect`, not `useEffect`,
  // so this and the dedicated prepend-restore effect below both run
  // (synchronously, in declaration order) before the browser paints --
  // see that effect's own comment for why the ordering between the two
  // matters.
  useLayoutEffect(() => {
    const el = messageListRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, isAsking])

  // Corrects the scroll position after a history-prepend, undoing the
  // scroll-to-newest effect above (which always fires too, since
  // `messages` changed in the same update) by restoring exactly the
  // visual position the user was already at, relative to the content
  // that was already on screen -- prepending older turns above the
  // viewport must never yank the user down to the bottom, which would
  // defeat the entire point of scrolling up to read them.
  //
  // Keyed *only* on `historyPrependToken`, not on `messages` generally:
  // `loadOlderHistory` below sets both in the same synchronous batch, so
  // this effect only ever fires in the exact commit a real prepend
  // produced. A live-append (`handleSubmit`) never touches
  // `historyPrependToken`, so it can never accidentally re-trigger this
  // effect and apply prepend-restore math to an unrelated update -- the
  // race a shared boolean ref flag was vulnerable to (a flag says
  // "the last prepend happened" but not "in *this* commit").
  // Declared after the scroll-to-newest effect above so that when both
  // fire in the same commit, this one's assignment runs second and wins.
  useLayoutEffect(() => {
    if (historyPrependToken === 0) return
    const el = messageListRef.current
    const adjustment = pendingScrollAdjustmentRef.current
    if (el && adjustment) {
      el.scrollTop = el.scrollHeight - adjustment.previousScrollHeight + adjustment.previousScrollTop
    }
    pendingScrollAdjustmentRef.current = null
  }, [historyPrependToken])

  async function loadOlderHistory() {
    if (isLoadingHistoryRef.current || !hasMoreHistory) return
    isLoadingHistoryRef.current = true
    setIsLoadingHistory(true)
    setError(null)
    try {
      const page = await getChatHistory(authFetch, sessionId, { cursor: historyCursor, limit: HISTORY_PAGE_LIMIT })
      const older = page.messages.slice().reverse().map(toUiMessage)
      const el = messageListRef.current
      if (el) {
        // Exact because the "Loading earlier messages…" indicator lives in
        // the header strip *outside* this scroller, not inside it. When it
        // was rendered inside, this measurement ran while it was still
        // mounted but the restore below ran in the commit that removed it,
        // so the restored `scrollTop` was short by the indicator's own
        // height -- a visible jump, which is precisely what this effect
        // exists to prevent.
        pendingScrollAdjustmentRef.current = {
          previousScrollHeight: el.scrollHeight,
          previousScrollTop: el.scrollTop,
        }
      }
      setLiveAnnouncementsEnabled(false)
      setMessages((previous) => [...older, ...previous])
      setHistoryPrependToken((token) => token + 1)
      setHistoryCursor(page.next_cursor)
      setHasMoreHistory(page.has_more)
    } catch (err) {
      // Surfaced through the same banner `handleSubmit` uses -- a failed
      // scroll-triggered page must look like a failure, not silently
      // indistinguishable from "no more history" (has_more: false).
      setError({ kind: err.isServiceError ? 'service' : 'other', message: err.message })
    } finally {
      isLoadingHistoryRef.current = false
      setIsLoadingHistory(false)
    }
  }

  function handleMessageListScroll(event) {
    const { scrollTop, scrollHeight, clientHeight } = event.currentTarget
    // 48px slop: close enough to the bottom edge that "jump to latest"
    // would be redundant, without demanding pixel-perfect alignment (a
    // smooth-scroll animation's last frame or two otherwise flickers the
    // button in and out right before it actually settles).
    setIsNearBottom(scrollHeight - scrollTop - clientHeight < 48)
    if (scrollTop <= 0) {
      loadOlderHistory()
    }
  }

  // Keeps scrolling up a *possible* gesture in the first place. Scroll is
  // now the only trigger for the next older page, and a scroll event can
  // only ever fire on a scroller that actually overflows -- so a returning
  // user whose 3-message initial page (UX-DR29) doesn't fill this
  // 520px-minimum container had no way at all to reach their own history:
  // nothing to scroll, therefore nothing to trigger the fetch. This pulls
  // pages in until the thread is tall enough to scroll (or the backend says
  // there is nothing older left), at which point `handleMessageListScroll`
  // above takes over as the sole trigger.
  //
  // Re-runs on `messages` so each prepended page is re-measured: one page
  // of short turns can still leave the scroller un-overflowed, and this
  // must then fetch again rather than stopping one page short. The
  // `hasMoreHistory`/`isLoadingHistoryRef` guards inside `loadOlderHistory`
  // are what make that self-terminating -- the last page flips
  // `hasMoreHistory` false and the loop ends there.
  // `clientHeight > 0` is a real guard, not a jsdom accommodation: a
  // scroller that hasn't been laid out yet (or isn't currently displayed)
  // reports 0 for both measurements, which would read as "doesn't
  // overflow" and pull the entire conversation in one page at a time
  // against a container that was never actually too short.
  useEffect(() => {
    if (!hasMoreHistory || isLoadingHistoryRef.current) return
    const el = messageListRef.current
    if (el && el.clientHeight > 0 && el.scrollHeight <= el.clientHeight) {
      loadOlderHistory()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, hasMoreHistory])

  // Scrolls a single message bubble into view without disturbing the rest
  // of the thread around it -- 'center' rather than 'start'/'end' so a
  // short bubble near either edge of the scroller still gets some
  // surrounding context visible above and below it.
  function scrollToMessageIndex(index) {
    messageRefs.current
      .get(index)
      ?.scrollIntoView({ behavior: prefersReducedMotion() ? 'instant' : 'smooth', block: 'center' })
  }

  // Steps the active match forward (+1) or backward (-1) through
  // `matchedIndices`, wrapping around at either end so the arrows never
  // dead-end -- mirrors the wraparound behavior of a browser's own
  // find-in-page next/previous.
  function stepMatch(offset) {
    if (matchedIndices.length === 0) return
    setActiveMatchOrdinal((previous) => {
      const next = (previous + offset + matchedIndices.length) % matchedIndices.length
      scrollToMessageIndex(matchedIndices[next])
      return next
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    await submitQuestion(question)
  }

  async function submitQuestion(text) {
    const trimmed = text.trim()
    if (!trimmed || isAsking) return

    // Session titling (chat/service.py::_persist_turn) sets the backend
    // session's title from the first question it ever sees, then never
    // again -- so the sessions list only needs a refetch to pick up the
    // new title on that first turn. `messages.length === 0` here (before
    // this turn's own optimistic append below) is exactly that "first
    // turn" signal.
    const isFirstTurn = messages.length === 0

    // A newly-asked question is exactly the "genuinely new incoming
    // answer" case the live region is reserved for -- re-enable it here,
    // since an earlier history reveal (initial load or scroll-up) may
    // have left it switched off. Also marks that a live turn now exists,
    // so a still-in-flight initial history fetch (if any) knows not to
    // overwrite it once that fetch finally resolves.
    hasSubmittedLiveQuestionRef.current = true
    setLiveAnnouncementsEnabled(true)
    // `id: null` until the response comes back -- AskResponse only learns
    // the persisted row's own id once `chat/service.py::_finish` has
    // actually written it (AskResponse.user_message_id's own docstring).
    // Kept as the exact object reference `applyTurnResult` below patches
    // by identity, not by array index: `loadOlderHistory` can prepend
    // older pages onto `messages` while this request is still in flight,
    // which would silently invalidate an index captured now.
    const userMessage = { role: 'user', id: null, text: trimmed }
    setMessages((previous) => [...previous, userMessage])
    setQuestion('')
    setIsAsking(true)
    setError(null)

    try {
      const result = await askQuestion(authFetch, sessionId, trimmed, selectedDocumentIds)
      if (isFirstTurn) {
        // Fire-and-forget: the sessions panel's title lagging by a beat
        // is fine, but blocking this turn's own answer on it is not.
        refreshSessions()
      }
      applyTurnResult(userMessage, result)
    } catch (err) {
      setError({ kind: err.isServiceError ? 'service' : 'other', message: err.message })
    } finally {
      setIsAsking(false)
    }
  }

  // Shared by submitQuestion and handleEditMessage above/below: patches
  // `userMessage`'s id (by object identity -- see submitQuestion's own
  // comment on why not an index) once the backend has actually persisted
  // it, appends the turn's outcome message, and fires the matching
  // mascot beat. `chat/service.py::edit_message` returns the exact same
  // `AskResponse` shape `ask_question` does, so one function covers both
  // callers without duplicating this branching.
  function applyTurnResult(userMessage, result) {
    setMessages((previous) => {
      const patched = previous.map((m) =>
        m === userMessage ? { ...m, id: result.user_message_id } : m,
      )
      if (result.empty_reason === 'refusal') {
        // FR-10/UX-DR15: a designed refusal, not an empty-state notice --
        // its own message role so ChatMessage renders a real bubble,
        // never the plain notice paragraph the other two reasons use.
        return [...patched, { role: 'refusal' }]
      }
      if (result.empty_reason) {
        return [...patched, { role: 'notice', reason: result.empty_reason }]
      }
      return [
        ...patched,
        {
          role: 'assistant',
          id: result.message_id,
          segments: result.segments,
          feedback: null,
          followupQuestions: result.followup_questions ?? [],
        },
      ]
    })
    // No mascot beat either: AD-6/UX-DR15 already settled that a refusal
    // is correct behavior, not a failure, so it gets none of the danger-
    // adjacent treatment the 'noAnswer' beat below uses -- only an actual
    // empty-state notice does.
    if (result.empty_reason === 'refusal') return
    // The mascot's "nothing to show" cue: no documents, an empty scope,
    // or no matching content -- not a refusal, just the signal that
    // there was no information to find. Otherwise, only a grounded
    // answer earns the idea beat.
    triggerMascotBeat(result.empty_reason ? 'noAnswer' : 'idea')
  }

  // Edits one of this account's own past questions in place: drops it and
  // every message after it from the local thread (mirrors the backend's
  // own "discard this question and everything after it" --
  // chat/service.py::edit_message), then asks the edited text fresh via
  // the same applyTurnResult tail submitQuestion uses. `messageId == null`
  // guards the same "request for this message hasn't resolved an id yet"
  // window MessageActions' feedback buttons already guard against.
  async function handleEditMessage(messageId, text) {
    const trimmed = text.trim()
    if (!trimmed || isAsking || messageId == null) return
    const index = messages.findIndex((m) => m.role === 'user' && m.id === messageId)
    if (index === -1) return

    hasSubmittedLiveQuestionRef.current = true
    setLiveAnnouncementsEnabled(true)
    const userMessage = { role: 'user', id: null, text: trimmed }
    setMessages((previous) => [...previous.slice(0, index), userMessage])
    setIsAsking(true)
    setError(null)

    try {
      const result = await editMessage(authFetch, sessionId, messageId, trimmed, selectedDocumentIds)
      applyTurnResult(userMessage, result)
    } catch (err) {
      setError({ kind: err.isServiceError ? 'service' : 'other', message: err.message })
    } finally {
      setIsAsking(false)
    }
  }

  const chatSearchNeedle = chatSearch.trim().toLowerCase()
  // Full-thread indices of every message matching the active search --
  // the thread itself is always rendered in full (see the message-list
  // map below); this only drives the "N of M" count and the prev/next
  // match navigation, never what's actually in the DOM.
  const matchedIndices =
    chatSearchNeedle === ''
      ? []
      : messages
          .map((message, index) => ({ message, index }))
          .filter(({ message }) => messageSearchText(message).toLowerCase().includes(chatSearchNeedle))
          .map(({ index }) => index)

  // A fresh query (including clearing it) starts over at the first match
  // rather than carrying over whatever ordinal the previous query had
  // reached -- an ordinal from the old result set has no meaningful
  // relationship to the new one. Runs after render, so `matchedIndices`
  // above already reflects the new `chatSearchNeedle` by the time this
  // fires; deliberately keyed on the needle alone (not `matchedIndices`,
  // which is a new array every render) so a new message arriving mid-search
  // doesn't yank the user back to the first match.
  useEffect(() => {
    if (chatSearchNeedle === '') return
    setActiveMatchOrdinal(0)
    scrollToMessageIndex(matchedIndices[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatSearchNeedle])

  return (
    <>
      <header className="mb-5">
        <p className="text-eyebrow uppercase text-accent">{t('chat.eyebrow')}</p>
        <h1 className="text-page-title text-text">{t('chat.title')}</h1>
      </header>

      <div className="grid grid-cols-[260px_1fr_260px] gap-[20px] max-[900px]:grid-cols-1">
        <ChatSessionsPanel />

        <div
          className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card-bg shadow-card"
          style={{ minHeight: '520px', height: 'calc(100vh - 140px)' }}
        >
          {/* aria-atomic="false": only the newly-appended message is
              announced, not a full re-read of the thread every turn
              (UX-DR24). Notice messages persist in the thread after a
              later question is asked -- an honest record of the
              conversation, same as a user message or a real answer never
              being removed either; only the transient "Thinking…" bubble
              below is removed once its request settles.
              role="log" + tabIndex={0}: Chrome 127+ makes an overflow
              scroller keyboard-focusable on its own, but Firefox/Safari
              don't -- without this, a keyboard-only user on a long thread
              can't scroll back up at all. role="log" also documents the
              live-region semantics already implied by aria-live above.
              aria-live toggles to "off" while history is being revealed
              (initial load or scroll-up) -- see `liveAnnouncementsEnabled`'s
              own comment above for why this is the one place Story 3.4's
              "don't re-trigger the live region for paged-in history"
              requirement is actually enforced. onScroll triggers the next
              older page once the user scrolls to the very top.
              aria-busy reflects a history fetch actually in flight --
              paired with the visible "Loading earlier messages…" text in
              the header strip above rather than standing in alone,
              mirroring how the "Thinking…" bubble is both a visible cue
              and (via this same live region) an audible one. That strip
              sits outside this scroller on purpose: content mounting and
              unmounting inside it would shift the `scrollHeight` the
              prepend-restore effect measures against. */}
          {/* Scroll-to-top is the only trigger for the next older page --
              no button, so it never sits in front of/pushes down the
              search panel's own affordances. Purely informational, not
              interactive: the loading indicator's own aria-live handles
              the screen-reader case the removed button used to cover.
              Rendered outside the scroller so it doesn't perturb the
              prepend scroll-restore's `scrollHeight` math. */}
          {isLoadingHistory && (
            <div className="flex justify-center border-b border-border px-5 py-2">
              <p className="text-[11px] text-text2">{t('chat.loadingEarlier')}</p>
            </div>
          )}

          {/* relative wrapper, not the scroller itself: the "jump to
              latest" button below is positioned against this so it floats
              over the messages on scroll instead of scrolling away with
              them. */}
          <div className="relative min-h-0 flex-1">
            <div
              ref={messageListRef}
              role="log"
              tabIndex={0}
              aria-label={t('chat.conversation')}
              aria-live={liveAnnouncementsEnabled ? 'polite' : 'off'}
              aria-atomic="false"
              aria-busy={isLoadingHistory}
              onScroll={handleMessageListScroll}
              className="flex h-full flex-col gap-3 overflow-y-auto p-5"
            >
              {/* Empty-thread welcome (in place of a blank scroller): gated
                  on `isInitialHistoryLoaded` so a returning user with real
                  history never sees this flash before their messages
                  arrive, and on `documentCount !== null` so it doesn't
                  guess which of its two variants applies before
                  DocumentsScopePanel's own fetch (which owns that count)
                  has resolved. `m-auto` centers it in the flex-column
                  scroller since it's the only child whenever it renders. */}
              {messages.length === 0 && isInitialHistoryLoaded && documentCount !== null && (
                <div className="m-auto flex max-w-[380px] flex-col items-center gap-3 py-8 text-center">
                  <RobotFigure state="idle" className="w-16" />
                  {documentCount === 0 ? (
                    <>
                      <h2 className="font-display text-[16px] font-bold text-text">
                        {t('chat.welcome.noDocumentsTitle')}
                      </h2>
                      <p className="text-[13.5px] leading-relaxed text-text2">
                        {t('chat.welcome.noDocumentsBody')}
                      </p>
                      <Link to="/documents" className="btn-brand mt-1 rounded-full px-5 py-2.5 text-[13px] font-semibold">
                        {t('chat.welcome.noDocumentsCta')}
                      </Link>
                    </>
                  ) : (
                    <>
                      <h2 className="font-display text-[16px] font-bold text-text">{t('chat.welcome.readyTitle')}</h2>
                      <p className="text-[13.5px] leading-relaxed text-text2">{t('chat.welcome.readyBody')}</p>
                      <div className="mt-1 flex flex-col items-center gap-1.5">
                        <p className="text-[11.5px] font-semibold text-text2">{t('chat.welcome.tryLabel')}</p>
                        <div className="flex flex-wrap justify-center gap-2">
                          {[t('chat.welcome.sample1'), t('chat.welcome.sample2'), t('chat.welcome.sample3')].map(
                            (sample) => (
                              <button
                                key={sample}
                                type="button"
                                onClick={() => submitQuestion(sample)}
                                className="rounded-full border border-border bg-surface2 px-3.5 py-1.5 text-[12.5px] text-text hover:border-accent hover:text-accent"
                              >
                                {sample}
                              </button>
                            ),
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {messages.map((message, index) => (
                <ChatMessage
                  key={index}
                  ref={(node) => {
                    if (node) messageRefs.current.set(index, node)
                    else messageRefs.current.delete(index)
                  }}
                  message={message}
                  highlight={chatSearchNeedle}
                  isActiveMatch={chatSearchNeedle !== '' && matchedIndices[activeMatchOrdinal] === index}
                  authFetch={authFetch}
                  onFollowupClick={submitQuestion}
                  onEditMessage={handleEditMessage}
                />
              ))}
              {isAsking && <ChatMessage message={{ role: 'thinking' }} />}
              {isAsking && isSlowToAnswer && (
                <p role="status" className="mr-auto max-w-[78%] px-1 text-xs text-text2">
                  {t('common.slowServerHint')}
                </p>
              )}
            </div>

            {!isNearBottom && (
              <button
                type="button"
                onClick={() => {
                  const el = messageListRef.current
                  if (el) {
                    el.scrollTo({ top: el.scrollHeight, behavior: prefersReducedMotion() ? 'instant' : 'smooth' })
                  }
                }}
                aria-label={t('chat.jumpToLatest')}
                className="absolute bottom-4 left-1/2 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-card-bg text-text2 shadow-card transition hover:text-accent"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-4 w-4"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M8.5 11l3.5 3.5 3.5-3.5" />
                </svg>
              </button>
            )}
          </div>

          {error && (
            <p role="alert" className="mx-5 mb-2 text-xs text-danger">
              {error.kind === 'service'
                ? t('chat.serviceError')
                : error.message}
            </p>
          )}

          <form onSubmit={handleSubmit} className="border-t border-border bg-surface2/60 p-4">
            <div className="relative mt-9 w-full">
              {/* Otherwise a narrowed scope is only visible in the
                  right-hand panel -- easy to select 3 of 12 documents,
                  scroll down to ask, and have no reminder anywhere near
                  the question that the answer will only ever be grounded
                  in those 3. Shares the mascot's own reserved band above
                  the input (`bottom-full`) rather than adding a new row
                  of its own, so a narrowed scope doesn't make the
                  composer any taller than it already is. Only appears
                  once something's actually selected (UX-DR9's own
                  "all-unchecked reads as ask-everything" default needs no
                  chip -- there's nothing narrowed to call out). The ×
                  clears back to that default via the same `selectAll`
                  the scope panel's own "Select all" uses, just empty. */}
              {selectedDocumentIds.length > 0 && (
                <span className="absolute bottom-full right-0 mb-2.5 inline-flex items-center gap-1.5 rounded-full bg-accent/10 py-1 pl-3 pr-1.5 text-[12.5px] font-semibold text-accent">
                  {t('chat.scopeChip.label', { count: selectedDocumentIds.length })}
                  <button
                    type="button"
                    onClick={() => selectAll([])}
                    aria-label={t('chat.scopeChip.clearAria')}
                    className="flex h-4 w-4 items-center justify-center rounded-full hover:bg-accent/20"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="h-3 w-3">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </span>
              )}
              {/* The mascot mirrors the request state -- decorative
                  reinforcement of the "Thinking…" bubble, never the only
                  signal that something is in flight. */}
              <RobotMascot state={isAsking ? 'thinking' : mascotBeat ?? 'idle'} />
              <div className="flex w-full items-stretch gap-2">
                <label htmlFor="chat-question" className="sr-only">
                  {t('chat.askLabel')}
                </label>
                <input
                  id="chat-question"
                  type="text"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  // Mirrors AskRequest.max_length (chat/schemas.py) -- without
                  // this a pasted over-length question sails past the browser
                  // and only fails as a raw Pydantic 422 message, not the
                  // notice-style copy UX-DR19 expects for user-facing errors.
                  maxLength={2000}
                  // readOnly, not disabled: a disabled input drops keyboard
                  // focus to <body> and there's no reliable moment to
                  // restore it once re-enabled. readOnly keeps focus in
                  // place through the wait, still blocks editing, and
                  // still lets Enter re-submit -- but that re-submit is a
                  // no-op, since handleSubmit's own `isAsking` guard above
                  // already covers double-submit protection regardless of
                  // which of the two attributes is used here.
                  readOnly={isAsking}
                  placeholder={t('chat.askPlaceholder')}
                  className={`min-w-0 flex-1 rounded-full border border-border px-5 py-3 text-[14px] shadow-card ${isAsking ? 'opacity-60' : ''}`}
                />
                <button
                  type="submit"
                  // aria-disabled, not disabled: same reasoning as the
                  // input's readOnly above -- a disabled button that
                  // currently holds focus (a keyboard user who activated
                  // Ask, rather than pressing Enter from the input) drops
                  // focus to <body> with no reliable moment to restore it.
                  // Still functionally blocked: handleSubmit's own
                  // `isAsking` guard makes a click/Enter/Space while
                  // asking a no-op, exactly as it already does for the
                  // input's readOnly re-submit case.
                  aria-disabled={isAsking}
                  className={`btn-brand inline-flex shrink-0 items-center gap-1.5 rounded-full px-5 py-3 text-[13px] font-semibold ${isAsking ? 'cursor-not-allowed opacity-60' : ''}`}
                >
                  {t('chat.ask')}
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-4 w-4"
                  >
                    <path d="M5 12h13" />
                    <path d="M13 6l6 6-6 6" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
        </div>

        {/* Right column: search above the scope panel, same 20px gutter
            as the grid's own so the two panels read as one stack. */}
        <div className="flex min-w-0 flex-col gap-[20px] self-start">
          <ChatSearchPanel
            value={chatSearch}
            onChange={setChatSearch}
            resultCount={matchedIndices.length}
            totalCount={messages.length}
            activeMatchNumber={matchedIndices.length === 0 ? 0 : activeMatchOrdinal + 1}
            onPrevMatch={() => stepMatch(-1)}
            onNextMatch={() => stepMatch(1)}
          />
          <DocumentsScopePanel authFetch={authFetch} onDocumentsLoaded={setScopeDocuments} />
        </div>
      </div>
    </>
  )
}
