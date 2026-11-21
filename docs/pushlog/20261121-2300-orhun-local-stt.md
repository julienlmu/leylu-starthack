# Voice-message RFQs transcribed locally (mlx-whisper) before extraction (R67/R71)
- Who: Orhun
- Branch: orhun/deploy-next6
- What changed: agent/local_stt.py + rfq_agent._attachment_texts: an audio attachment with no text is transcribed on this Mac with mlx-whisper (~/.leylu-stt, model mlx-community/whisper-large-v3-turbo, 25 s timeout); empty or failed → the written-details ask (#170). LOCAL_STT=off switches it off. 5U allows local speech-to-text (Orhun).
- How verified: agent 1403 passed; R67's mp3 transcribed in 7.4 s ("textile samples, 11 pieces … 1,804 kilos … 17.18 cubic meters … postcode 51943 … Lima Airport, LIM … ready on the 24th of November … cheapest")
