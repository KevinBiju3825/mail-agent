"""Demo / sample email seed data so the app is fully explorable without Gmail."""
import random
from datetime import datetime, timedelta

SAMPLE_EMAILS = [
    {
        "subject": "Q4 Product Roadmap Review - Action Items",
        "sender": "Sarah Chen",
        "sender_email": "sarah.chen@innovatecorp.com",
        "body_text": """Hi team,

Following our roadmap sync yesterday, I wanted to circulate the key action items and decisions.

Priorities for Q4:
1. Launch the new dashboard analytics module by November 15
2. Complete migration to the new authentication service
3. Begin beta testing of the AI features with 50 selected users

Action items:
- Alex: Prepare technical spec for analytics module by Friday
- Priya: Coordinate with security team on auth migration timeline
- Marcus: Draft the beta program communication plan

Blockers to address:
- We need budget approval for the additional AWS capacity
- Legal review of the AI features data processing agreement

Let's discuss any concerns in Slack. Next sync is Thursday at 10am PT.

Best,
Sarah
VP of Product""",
        "category": "work",
        "priority": 9,
    },
    {
        "subject": "Invoice #INV-2024-1129 - Payment Due",
        "sender": "Billing Department",
        "sender_email": "billing@cloudservices.io",
        "body_text": """Dear Customer,

This is a reminder that Invoice #INV-2024-1129 in the amount of $2,847.50 is due on December 5, 2024.

Invoice Details:
- Service: Cloud Infrastructure - Enterprise Plan
- Period: November 2024
- Amount: $2,847.50
- Payment Terms: Net 30

Please arrange payment through your usual channel or contact us if you have any questions.

Thank you for your continued business.

Cloud Services Billing Team""",
        "category": "finance",
        "priority": 7,
    },
    {
        "subject": "Your flight to San Francisco - Booking Confirmed",
        "sender": "SkyLine Airlines",
        "sender_email": "reservations@skylineair.com",
        "body_text": """Booking Confirmation

Passenger: [Your name]
Confirmation Code: SKY7B2Q

Outbound Flight SL-408
Departure: JFK - December 12, 2024, 08:30 AM
Arrival: SFO - December 12, 2024, 11:45 AM
Seat: 14A (Window)

Return Flight SL-411
Departure: SFO - December 15, 2024, 06:15 PM
Arrival: JFK - December 16, 2024, 02:30 AM
Seat: 22C (Aisle)

Please arrive at the airport at least 2 hours before departure. Manage your booking online.

Safe travels!""",
        "category": "travel",
        "priority": 6,
    },
    {
        "subject": "Weekly Team Standup - Week 48 Notes",
        "sender": "Marcus Wong",
        "sender_email": "marcus.wong@innovatecorp.com",
        "body_text": """Team,

Notes from today's standup:

Wins this week:
- Shipped v2.4.1 with 3 major bug fixes
- Onboarded two new engineers to the platform team
- Customer satisfaction score jumped to 4.7/5

In progress:
- Analytics module (Alex) - 60% complete, on track
- Auth migration (Priya) - waiting on security review
- Documentation refresh (Diana) - 85% done

Upcoming:
- Design review for onboarding flow, Wednesday 2pm
- Quarterly all-hands next Friday
- Holiday party planning committee needs volunteers

Have a great week!
Marcus""",
        "category": "work",
        "priority": 5,
    },
    {
        "subject": "50% off Black Friday sale - Ends tonight!",
        "sender": "MegaStore Deals",
        "sender_email": "deals@megastore.com",
        "body_text": """BLACK FRIDAY SALE - LAST CHANCE

Don't miss out on our biggest sale of the year!

- 50% off electronics
- 40% off home goods
- 30% off apparel
- Free shipping on orders over $50

Use code: BLKFRI50

Sale ends at 11:59 PM tonight. Shop now before your favorites sell out!

Unsubscribe""",
        "category": "promotional",
        "priority": 2,
    },
    {
        "subject": "Re: Proposal for Strategic Partnership",
        "sender": "David Kim",
        "sender_email": "david.kim@synergypartners.com",
        "body_text": """Hi,

Thank you for sending over the partnership proposal. I've reviewed it with our leadership team and we're very interested in moving forward.

A few points to discuss:
1. The revenue split of 60/40 works for us, but we'd like to include performance-based incentives
2. Can we schedule a call to discuss the technical integration timeline?
3. Our legal team will need 2-3 weeks to complete their review

I'm available next Tuesday or Wednesday afternoon PT for a call. Please let me know what works.

Looking forward to building something great together.

Best regards,
David Kim
Director of Business Development
Synergy Partners""",
        "category": "work",
        "priority": 8,
    },
    {
        "subject": "Security Alert: New sign-in from Windows",
        "sender": "Account Security",
        "sender_email": "security-noreply@accounts.google.com",
        "body_text": """We noticed a new sign-in to your account on a Windows device.

If this was you, you don't need to do anything.

If this wasn't you, secure your account immediately:
1. Check your recent activity
2. Change your password
3. Enable 2-factor authentication

Device: Windows 11, Chrome browser
Location: New York, NY, United States
Time: December 1, 2024 at 09:23 AM EST

Google Account Security Team""",
        "category": "security",
        "priority": 7,
    },
    {
        "subject": "Coffee this week?",
        "sender": "Jamie Torres",
        "sender_email": "jamie.t@gmail.com",
        "body_text": """Hey!

It's been ages since we caught up. Are you free for coffee sometime this week? I have some exciting news to share and would love to hear how the new job is going.

Blue Bottle on 3rd or that cute place near your office - your call. Any afternoon after 2pm works for me.

Miss you!
Jamie""",
        "category": "personal",
        "priority": 4,
    },
    {
        "subject": "GitHub PR #847 - Needs your review",
        "sender": "GitHub Notifications",
        "sender_email": "notifications@github.com",
        "body_text": """@you was requested for review on PR #847 in innovatecorp/backend

Title: Add rate limiting middleware
Author: @alexdev
Changes: +342 -18 across 7 files

Description:
Implements token bucket rate limiting for public API endpoints. Configurable per-endpoint limits with Redis backend for distributed rate tracking. Includes tests and documentation.

View the pull request on GitHub.""",
        "category": "work",
        "priority": 6,
    },
    {
        "subject": "Your Amazon order has shipped",
        "sender": "Amazon.com",
        "sender_email": "shipment-tracking@amazon.com",
        "body_text": """Hello,

Great news! Your order has shipped.

Order #113-4738291-1029384
Estimated delivery: December 3-4, 2024

Items:
- Wireless Mechanical Keyboard (1)
- USB-C Hub (1)
- Notebook, Dot Grid, A5 (2-pack)

Track your package to see real-time updates.

Thanks for shopping with us!""",
        "category": "shopping",
        "priority": 3,
    },
    {
        "subject": "Meeting: Design Review - Onboarding Flow v3",
        "sender": "Priya Sharma",
        "sender_email": "priya.sharma@innovatecorp.com",
        "body_text": """Hi all,

I've uploaded the v3 mockups for the onboarding flow to Figma. Key changes based on last week's feedback:

- Reduced from 7 steps to 4
- Added progress indicator
- Simplified the account setup screen
- New microinteractions on hover states

Please review before Wednesday's design review at 2pm. I'd especially appreciate input from:
- Product: does the new flow meet the activation goals?
- Engineering: any concerns about implementation complexity?
- Data: what events should we instrument for the new flow?

Figma link in Slack. See you Wednesday!

Priya""",
        "category": "work",
        "priority": 7,
    },
    {
        "subject": "Congratulations! You've reached a new milestone",
        "sender": "LinkedIn",
        "sender_email": "notifications@linkedin.com",
        "body_text": """Congratulations!

Your post about AI in email management has reached 10,000 impressions and gathered 250 reactions.

Top engagers include:
- Sarah Chen and 12 others from your network
- 3 people started following you after seeing this post

Keep sharing your insights - your network wants to hear from you!

The LinkedIn Team""",
        "category": "social",
        "priority": 2,
    },
    {
        "subject": "URGENT: Server incident - post-mortem meeting",
        "sender": "Alex Novak",
        "sender_email": "alex.novak@innovatecorp.com",
        "body_text": """Team,

As you know, we had a 47-minute production outage last night affecting checkout for approximately 3,200 customers. The root cause was a Redis connection pool exhaustion following our deploy.

I'm scheduling a blameless post-mortem for tomorrow at 3pm PT. Please attend if you were involved in the incident response or if the affected systems are in your area.

Preliminary timeline and impact assessment is in the incident doc. Please add any additional context before the meeting.

Priorities for the discussion:
1. Confirm root cause and full impact
2. Immediate mitigations (already deployed)
3. Longer-term improvements to prevent recurrence
4. Communication to affected customers

This is not about assigning blame - it's about learning and improving.

Alex""",
        "category": "work",
        "priority": 10,
    },
    {
        "subject": "Your monthly bank statement is ready",
        "sender": "First National Bank",
        "sender_email": "estatements@firstnational.com",
        "body_text": """Your November 2024 statement is now available.

Account: Checking ****4829
Statement period: November 1 - November 30, 2024
Ending balance: $12,483.71

View your statement online through secure banking. For questions, contact our support team.

First National Bank""",
        "category": "finance",
        "priority": 4,
    },
    {
        "subject": "Newsletter: The Weekly Tech Roundup",
        "sender": "TechDigest",
        "sender_email": "newsletter@techdigest.io",
        "body_text": """This week in tech:

1. OpenAI announces new model with improved reasoning capabilities
2. GitHub Copilot rolls out enterprise features
3. Apple's Vision Pro sees pricing update in EU markets
4. Rust adoption grows 40% year-over-year in embedded systems
5. New research on efficient transformer architectures

Featured deep dive: How large language models are changing developer productivity

Read the full newsletter online.""",
        "category": "newsletter",
        "priority": 3,
    },
]


def seed_demo_emails(account_email: str = "demo@example.com") -> list[dict]:
    """Return sample emails ready for insertion (add gmail_id, thread_id, date)."""
    now = datetime.utcnow()
    # Group emails into meaningful demo threads:
    #   Roadmap thread: 0, 3, 10, 12 (Sarah, Marcus, Priya, Alex — same team, roadmap topic)
    #   Partnership thread: 5 (solo, but replies would go here)
    #   Everything else solo
    thread_assignments = {
        0: "demo_thread_roadmap",   # Sarah Chen - Q4 Roadmap
        3: "demo_thread_roadmap",   # Marcus - Weekly Standup
        10: "demo_thread_roadmap",  # Priya - Design Review
        12: "demo_thread_roadmap",  # Alex - URGENT Server incident
        5: "demo_thread_partnership",  # David Kim - Partnership
    }
    prepared = []
    for i, template in enumerate(SAMPLE_EMAILS):
        days_ago = i * 0.4 + random.random()
        dt = now - timedelta(days=days_ago, hours=random.randint(0, 23))
        thread_id = thread_assignments.get(i, f"demo_thread_solo_{i}")
        email = {
            "gmail_id": f"demo_msg_{i:04d}",
            "thread_id": thread_id,
            "account_email": account_email,
            "subject": template["subject"],
            "sender": template["sender"],
            "sender_email": template["sender_email"],
            "recipient": account_email,
            "cc": "",
            "date": dt.isoformat(),
            "snippet": template["body_text"][:200].replace("\n", " "),
            "body_text": template["body_text"],
            "body_html": "",
            "labels": ["INBOX"] + (["UNREAD"] if random.random() > 0.6 else []),
            "is_read": random.random() > 0.4,
            "is_starred": random.random() > 0.85,
            "attachments": [],
            "category": template["category"],
            "priority": template["priority"],
        }
        prepared.append(email)
    return prepared
