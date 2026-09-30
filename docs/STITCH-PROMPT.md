# Google Stitch prompt: Shabetz UI redesign

Paste the prompt below into Google Stitch. Generate the screens one at a time
(Stitch does best with one screen per request), starting with "Schedule".
Then bring the exported HTML/Tailwind or screenshots back and we map the tokens
into `frontend/src/index.css` and `tailwind.config.ts`.

---

## Prompt

Design a modern, polished web app UI for **Shabetz**, a shift-scheduling tool
for organisations that staff jobs around the clock (security posts, hospital
wards, army units, call centres). An administrator defines divisions, people,
skills, shift windows and jobs; the app generates a schedule and lets an
administrator or manager adjust it by hand afterwards.

**Users:** administrators and managers (desktop-first, dense data, long
sessions) and staff (phone-first, only want to see their own shifts and request
time off).

**Look and feel:** calm, trustworthy, professional, not corporate-grey. Think
Linear or Notion Calendar crossed with a clean Google Material 3 feel.
Generous whitespace, soft rounded corners (10-12px), subtle shadows, thin
borders. One confident accent colour (deep indigo or teal) used for primary
actions, selected states and focus rings. Neutral slate greys for everything
else. Friendly but restrained: no gradients on surfaces, no stock illustrations
beyond simple line-icon empty states.

**Hard requirements**
- Full **right-to-left Hebrew** layout as a first-class variant, mirrored
  properly, plus English LTR. Show both for the main screen.
- **Light and dark** themes, both fully designed (not an inverted afterthought).
- **Accessible:** WCAG AA contrast, visible focus rings, status never conveyed by
  colour alone (always an icon plus text), 44px touch targets on mobile.
- Responsive: desktop (1440), tablet, and mobile (390).
- Font: Inter for Latin, Heebo for Hebrew. Tabular numerals for times and counts.

**Colour roles:** accent (primary), success/covered (green), caution/borrowed
staff (amber), error/understaffed (red), info (slate-blue). Each division gets
a distinct, soft pastel tag colour (sky, violet, teal, orange, fuchsia, lime),
readable in dark mode.

**Screen 1: Schedule (the main screen)**
- Top bar: project switcher, navigation tabs (Schedule, Time off,
  Configuration), language toggle (עברית / English), theme toggle, user menu.
- A card with a date-range picker (from / to), a prominent primary "Generate
  schedule" button, and an export menu (CSV, Excel, PDF, calendar).
- A row of 5 stat cards: Shifts assigned, Staff used (with utilisation %),
  Understaffed (red when above zero), Borrowed staff (amber), Warnings.
- A "Division on duty" strip: one small chip per day showing the date and the
  division currently on rotation.
- A segmented control switching between **Table** and **Timeline** views.
  - Table: search box, filters (division, job, date), sortable columns
    (Date, Window, Time, Job, Person, Division). Person cells can carry small
    badges: "role", "borrowed", and a blue **"edited"** badge for shifts changed
    by hand. Each row has a pencil icon button to edit it. Sticky header,
    zebra-free, hover highlight.
  - Timeline: a Gantt-style grid with one row per person, days across, coloured
    blocks per shift, amber outline for borrowed staff, a visible "now" line.
- A "Warnings" panel below with severity badges (error, warning, info), filter
  chips, and a one-line explanation per item that links to the shift.
- Floating or toolbar button: "Add person to a shift".

**Screen 2: Edit shift dialog (modal, very important)**
Opens from the pencil icon. Title: "Change who works this shift".
- Read-only summary: job, date, window with time range, and who is currently
  assigned.
- A searchable person picker ("Assign to") showing avatar initials, name,
  division tag, and each person's shifts that week.
- **Live rule check** under the picker: either a green "No rule is broken by
  this change", or an amber box "This change breaks some rules" listing each
  conflict with an icon (on time off, double-booked, not enough rest, missing
  skill) and a checkbox "Assign anyway, I know about these". Save stays disabled
  until that box is ticked.
- Footer: primary "Save change", secondary "Cancel", and on the far side a
  destructive text button "Remove from shift" that turns into an inline
  "Remove Ana from this shift? Yes, remove" confirmation.
- Also design the variant for "Add someone to a shift" with job, window and date
  selectors above the person picker.

**Screen 3: Sign-in.** Centred card, email + password, a "Continue with Google"
button, forgot-password link, language toggle. Friendly logo mark (a simple
rotating-calendar glyph) and one line of product copy.

**Screen 4: Setup wizard.** Stepper across the top (Divisions, Proficiency,
Skills, Shift windows, Jobs, People, Rules, Review), a form card per step, and a
"feasibility" side panel with a verdict badge (OK / Tight / Infeasible) and
plain-language tips on what to fix.

**Screen 5: Staff home (mobile).** Bottom tab bar (My shifts, Time off). A
vertical list of upcoming shifts grouped by day with large time ranges, job
name, and a "next shift in 3h" highlight card at the top. A floating
"Request time off" button.

**Screen 6: Time off.** A list of requests with status chips (pending, approved,
denied), approve/deny buttons for managers with an optional note, and a
mini-calendar for choosing dates.

**Components to include in the design system:** buttons (primary, ghost,
destructive), inputs and selects, badges, stat cards, data table, segmented
control, modal, toast, empty states, skeleton loaders, stepper, avatar
initials, tooltip.

Deliver the screens in light and dark, LTR and RTL where noted, and list the
design tokens (colours, radii, spacing, type scale) so they can be mapped to
Tailwind CSS.
