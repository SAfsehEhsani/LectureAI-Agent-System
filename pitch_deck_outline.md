# LectureLens AI — 5-slide pitch deck
## 1. Problem
Students spend hours manually making chapters, revision notes, quizzes and short clips from long lectures.

## 2. Solution
LectureLens AI transforms a 60+ minute lecture into a shareable learning pack.

## 3. Architecture
YouTube captions / uploaded video → local Whisper if needed → 5-minute transcript chunks → Grok via xAI API → chapters, notes, evidence-backed quiz, clip suggestions → Markdown/PDF/JSON and optional FFmpeg clips.

## 4. Evaluation
Report only measured results: test lecture duration, success/failure, wall-clock time, timestamp validity, quiz evidence review, clip success, and xAI usage cost.

## 5. Next steps
Stronger multi-stage synthesis, more rigorous quiz grounding, polished captions, Hindi/Hinglish benchmark, deployed demo.
