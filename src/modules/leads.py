"""Lead generation hub for mortgage protection life insurance."""


def mortgage_protection_lead_hub(target_leads: int = 30) -> str:
    """Return a practical lead-generation hub blueprint."""
    if target_leads < 1:
        target_leads = 1

    return f"""\
=== Mortgage Protection Lead Hub ===
Primary Goal: Generate {target_leads} qualified mortgage protection leads per month.

1) CORE OFFER
- Free "Family Mortgage Protection Review" (15 minutes)
- Outcome: right-sized term or whole-life options to protect the home payment

2) LEAD SOURCES (WEEKLY)
- Referral partners (realtors, loan officers): 10 introductions
- Client referrals: 5 introductions
- Community outreach (church, local events, social groups): 10 conversations
- Social content + CTA: 3 posts, 1 short video, 1 live Q&A

3) CAPTURE SYSTEM
- Single intake form with:
  * Name / phone / email
  * Homeowner status and mortgage balance range
  * Preferred call time
- Every lead enters one pipeline: New -> Contacted -> Booked -> Quoted -> Closed

4) FOLLOW-UP CADENCE
- Day 0: Text + call + voicemail
- Day 1: Follow-up text with scheduling link
- Day 3: Educational message (why mortgage protection matters)
- Day 7: "Still interested?" close-loop message

5) WEEKLY SCOREBOARD
- New leads collected
- Contacts made
- Appointments booked
- Quotes presented
- Policies written
- Placement rate and 13-month persistency trend

6) SCRIPT (SHORT OPENING)
"Hi [Name], this is [Advisor] with GIA Legacy Planning. You were referred for a
quick mortgage protection review so your family can keep the home if anything
unexpected happens. Would morning or afternoon be better for a 15-minute call?"

7) DAILY POWER HOUR (NON-NEGOTIABLE)
- 20 outbound calls
- 20 follow-up texts
- 5 referral asks
- 1 educational post with a clear call-to-action
"""
