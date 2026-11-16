# Automation: Agent Growth Sync (Jotform → Microsoft Lists → Tracker + Client Files)

**Goal:** One record per agent showing onboarding progress, weekly activity, and their client book, so you can see each agent's growth without chasing anyone.
**Triggers:** (1) An agent submits the Friday Weekly Activity Check-In. (2) An agent submits App Submitted for a new client. (3) Every Monday at 6am (scheduled roll-up).
**Tools used:** Jotform (input), Microsoft Lists (source of truth), Power Automate, SharePoint (client folders), Excel (reports), Slack, Outlook.

---

## 0. The rule that makes this work
**Agent Email is the key.** Every form, list and file matches on email. If an email is missing or mistyped, that agent's data won't connect.

Fix these roster rows before you build. They have **no email** on `Agent_Onboarding_Tracker.xlsx` → AGENT ROSTER:
- Matt Selph · Dolores Vargas · Sue Mahdi · Ronald G · Tiara Willams

---

## 1. Jotform inputs (already created)
| Form | Who | When | Feeds |
|---|---|---|---|
| **GIA Weekly Activity Check-In** — https://form.jotform.com/262838513781061 | Every licensed agent | Fridays by 6pm | `Weekly Activity` list |
| **GIA App Submitted – Client Log** — https://form.jotform.com/262838462934064 | Every agent | Same day as each app | `Client Book` list + the agent's client folder |

Jotform setup (5 min, in the form builder):
- Settings → Form Fields → set **Agent Email** as unique-per-submission off, required on.
- Use a prefilled link per agent (`?agentEmail=their@email.com&agentFullName=First%20Last`) so they never mistype their email. Save each agent's link in the `Agents` list (column below).

---

## 2. Microsoft Lists (SharePoint site: GIA Agency)

### List: `Agents` (one row per agent; it replaces the AGENT ROSTER tab as the master)
| Column | Type | Notes |
|---|---|---|
| Agent Name | Title | |
| Agent Email | Single line, **enforce unique** | KEY |
| Phone | Single line | |
| Upline / Recruiter | Person or Single line | |
| Start Date | Date | |
| License Date | Date | |
| License # | Single line | |
| Status | Choice | Recruiting, Pre-Licensed, In Licensing, Licensed, Active-Producing, Building, On Hold, Inactive. Same values as the tracker. |
| Onboarding Phase | Choice | Phase 1–5 (Stage↔Phase map) |
| Days 1-30 % / 31-60 % / 61-90 % | Number | Synced from the Excel tracker (Flow D) |
| First App Date | Date | Set by Flow B |
| Last Check-In Date | Date | Set by Flow A |
| Apps – Last 4 Wks | Number | Flow C |
| APV – Last 30 Days | Currency | Flow C |
| Lifetime Apps | Number | Flow B |
| Lifetime APV | Currency | Flow B |
| Growth Stage | Choice | Set by Flow C, see rules below |
| At-Risk Flag | Choice | None, No Check-In, Licensing >45d, No App 30d, Below Standard |
| Client Folder | Hyperlink | Set by Flow B |
| Check-In Link / App Log Link | Hyperlink | Prefilled Jotform links |

### List: `Weekly Activity` (one row per agent per week)
Agent Email (key), Agent (lookup → Agents), Week Ending, Leads Purchased, Dials, Contacts, Appts Booked, Appts Sat, No Shows, Apps Submitted, APV Submitted, Policies Issued, Lead Spend, Biggest Win, Needs Help With, Mentor Notes.
Calculated: **Contact Rate** = Contacts/Dials · **Book Rate** = Booked/Contacts · **Show Rate** = Sat/Booked · **Close Rate** = Apps/Sat · **Hit Standard** = `IF(Apps>=2,"Yes","No")`

### List: `Client Book` (one row per application)
Agent Email (key), Agent (lookup), Client First/Last, Client Phone, Client Email, State, Date Submitted, Product, Carrier, Policy #, APV, Lead Type, Status, Referrals Asked, Notes, Days Since Submitted (calc).
**No SSNs, health, or bank info, anywhere.**

---

## 3. Growth Stage rules (Flow C writes these)
| Stage | Rule |
|---|---|
| 1 · Recruit | Status = Recruiting |
| 2 · Licensing | Status = Pre-Licensed / In Licensing. **Red flag at 45 days** from Start Date |
| 3 · Licensed – No App | Licensed, Lifetime Apps = 0. **Flag at 30 days** from License Date |
| 4 · First App | Lifetime Apps ≥ 1 |
| 5 · Active Producer | Apps last 4 wks ≥ 8 (2/wk) **and** APV last 30 days ≥ $3,000 |
| 6 · Consistent Producer | Active Producer 3 months in a row |
| 7 · Leader | Consistent, plus ≥ 1 direct recruit at stage 4+ |

---

## 4. Power Automate flows

### Flow A: Weekly Check-In → Weekly Activity
1. Trigger: **Jotform → "When a response is submitted"** to *GIA Weekly Activity Check-In*.
   - If the Jotform connector is unavailable on your license, use the fallback: Jotform → Settings → Emails → send each submission to `activity@yourdomain`. Then trigger on **Outlook "When a new email arrives (V3)"** in that folder and parse the fields with "Html to text" + "Compose". Tell me and I'll write that version.
2. **SharePoint → Get items** from `Agents`, filter `AgentEmail eq '[Agent Email]'` (convert to lowercase first with `toLower()`).
3. Condition: no match → **Outlook: send email** to Joe/VA: "Unmatched check-in from [email]: fix email on roster." Stop.
4. **SharePoint → Create item** in `Weekly Activity` with every field, and set Agent lookup = matched ID.
5. **SharePoint → Update item** in `Agents`: Last Check-In Date = Week Ending.
6. Condition: Apps Submitted ≥ 2 → **Slack post** to `#team-wins`. Otherwise, if Needs Help ≠ "Nothing", **Slack DM** the Upline.

### Flow B: App Submitted → Client Book + Client Folder
1. Trigger: Jotform response on *GIA App Submitted – Client Log*.
2. Get the matching agent from `Agents` (same as A2–A3).
3. **Create item** in `Client Book`.
4. **SharePoint → Create new folder**: `Client Files/[Agent Name]/[Client Last], [Client First]` (it skips if the folder exists). Write the folder URL to `Agents.Client Folder` if it's blank.
5. **Update `Agents`**: Lifetime Apps +1, Lifetime APV + APV. If First App Date is blank → set it to today **and** post to `#team-wins`: "🎉 FIRST APP: [Agent] just wrote [Product] with [Carrier]!"
6. **Teams/Slack** to the upline: "[Agent] logged an app: [Product], $[APV]."

### Flow C: Monday Roll-Up (Recurrence: Mon 6:00am CT)
1. Get all `Agents` where Status not in (Inactive, Recruiting).
2. For each agent:
   - Get `Weekly Activity` rows from the last 28 days → sum Apps → `Apps – Last 4 Wks`.
   - Get `Client Book` rows from the last 30 days → sum APV → `APV – Last 30 Days`.
   - Apply the Growth Stage rules in §3 → update `Growth Stage`.
   - Set the At-Risk Flag: Last Check-In more than 7 days ago → **No Check-In**; In Licensing more than 45 days → **Licensing >45d**; Licensed more than 30 days with 0 apps → **No App 30d**; Licensed and Apps last 4 wks < 8 → **Below Standard**.
3. Email Joe + Sarah a table of every agent where At-Risk ≠ None, grouped by upline. This feeds **Run Weekly Agency Review**.

### Flow D: Keep the Excel tracker in sync (optional, during transition)
Recurrence daily → **Excel Online → List rows present in a table** on `Agent_Onboarding_Tracker.xlsx` (format the AGENT ROSTER as a table named `Roster` first) → for each row, match on Email → update `Agents` Days 1-30/31-60/61-90 %.
Keep checking off onboarding tasks in Excel as you do today; the % flows into Lists.

---

## 5. The "complete picture" view
- **Lists view `Agent Growth Board`** on `Agents`: board grouped by Growth Stage, card shows Apps-4wk, APV-30d, At-Risk Flag.
- **Agent profile:** open an agent row → `Weekly Activity` and `Client Book` show up as related lists (Lookup columns let you add these as linked list web parts on a SharePoint page).
- **Excel report:** Data → Get Data → SharePoint List (all 3 lists) → one pivot per agent showing weekly dials → appts → apps → APV trend.

---

## 6. Messages

**Friday 3pm reminder (Team Taylor SMS, recurring):**
> Hey [First]! Friday check-in time. 90 seconds, your numbers = your coaching 💪 [Check-In Link]

**No check-in (Flow C, Monday, Team Taylor SMS):**
> [First], didn't see your numbers last week. All good? Drop them here and let's plan this week: [Check-In Link]

**Unmatched email alert (Outlook to VA):**
> Subject: Unmatched Jotform submission. [Email] doesn't match any agent. Fix it on the Agents list, then re-run the flow.

---

## 7. Manual fallback (VA runs this until the flows are live)
**Every Friday 3pm:** send the reminder text to every Licensed+ agent.
**Every Monday 9am (30 min):**
1. Jotform → each form → Submissions → Download as Excel (last 7 days).
2. Paste the check-ins into the `Weekly Activity` list (Lists → Edit in grid view → paste).
3. Paste the apps into `Client Book`. Create the client folder for any new client.
4. Update the agents' Last Check-In and Lifetime Apps/APV.
5. Filter `Agents`: Last Check-In more than 7 days ago → send the "no check-in" text. Then email Joe + Sarah the list of at-risk agents.

**Done when:** every Licensed agent has a row for the week, or a no-check-in text has gone out.

---

## 8. Test it
1. Add yourself to `Agents` with your email.
2. Submit the Check-In with Apps = 2 → a row appears in `Weekly Activity`, Last Check-In updates, and a `#team-wins` post fires.
3. Submit App Submitted → a `Client Book` row appears, the folder `Client Files/Joe Gutierrez/Test, Client` exists, and Lifetime Apps = 1.
4. Submit with a fake email → the unmatched alert email arrives.
5. Run Flow C manually → your Growth Stage and flags update.
6. Delete the test rows.
