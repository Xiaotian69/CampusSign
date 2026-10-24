# Course engine provenance and adaptations

Source: https://github.com/Mortal004/Xuexitong_shuake
Baseline: 563bf27c5cb7a3eb659ed7b27b855d5e5c131c7c (master).
Copyright 2025 Mortal004. The full upstream noncommercial license is in LICENSE.
This subtree is separately licensed; the root MIT license does not override it.

Whitelist: navigation extracted from main.py; task do_work, finish_dicussion,
play_audio, quiz_ai, reading, watch_live, watch_ppt, watch_vido; tool common,
color, file, no_secret, DeepSeekAsk and font_dict.txt. Other Python files here
are local adapters/replacements. No upstream GUI, sign/xxt, account data,
cookies, face bypass, monitoring bypass, binary or browser extensions copied.

Adaptations: namespaced imports; stdin worker and isolated working directory;
Selenium Manager or explicit driver; official browser login and manual face
verification wait; standard media playbackRate; no seeking to completion;
AI only through a user-configured DeepSeek key/model, no public answer services,
embedded tokens, pickle or public cache; literal_eval instead of eval; AI off
by default and video questions wait for the user unless answering is enabled.
Discussion AI writes its own answer instead of copying another student's reply.
Homework keeps upstream save-only behavior, regardless of quiz submit setting.

Offline tests cover the worker contract and cleanup, not current website behavior.
The upstream DOM selectors are version-sensitive. School-specific credentials,
captchas and QR/face checks may require manual browser interaction. Course name
must match the page. A queue ending means traversal ended, not a guarantee of
credit: skipped quizzes/discussions and website-side checks may leave tasks open.
Browser windows close in finally. AI may be wrong; saved homework needs review.
