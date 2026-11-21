# RFQ only in an unreadable attachment (voice message): ask for the details in writing (R67)
- Who: Orhun
- Branch: orhun/audio-ask
- What changed: agent/rfq_agent.py: core fields missing and every attachment unreadable (R67 voice-message.mp3) → details_question_text at once (no amount), rfq.awaiting=details; agent/main.py routes the customer's written answer to resume_after_details, which reads and quotes it in the same session. DETAILS_ASK=off.
- How verified: agent 1320 passed
