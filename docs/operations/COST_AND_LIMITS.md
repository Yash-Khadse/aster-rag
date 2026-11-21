# Cost and provider limits

Checked against official provider documentation on 2026-10-29. These are current allowances, not promises of perpetual free hosting. No paid inference is enabled by default. Local inference has hardware/electricity costs but no mandatory API bill.

| Provider | Published free constraints | Operational consequence |
|---|---|---|
| Render Free | 750 instance hours per workspace/month, idle spin-down after 15 minutes, ephemeral filesystem | Cold starts and restarts lose local files. Use external SQL, objects and vectors. No permanent worker assumption. |
| Supabase Free | 500 MB database, 1 GB file storage, 5 GB egress plus 5 GB cached egress; 2 active projects; pause after a week of inactivity | Small fictional corpus only; monitor storage and resume paused projects. |
| Vercel Hobby | Personal, non-commercial use; capped plan allowances | Appropriate only if the deployment meets Hobby terms. Do not use this template as a commercial enterprise hosting entitlement. |
| Pinecone Starter | Account/region and index quotas must be checked in the current console | Pre-create a compatible dense index; do not assume a paid region or capacity. The app does not provision paid infrastructure. |
| Groq / Gemini | Model-specific rate and token limits vary by account and model | Confirm available model and free access in your account. Quota exhaustion must surface as unavailable, never a fabricated answer. |
| Ollama | Runs on owned CPU/RAM/storage | Download weights once; inference speed is hardware-dependent. |

Sources: [Render Free](https://render.com/docs/free), [Supabase pricing](https://supabase.com/pricing), [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Pinecone cost](https://docs.pinecone.io/guides/manage-cost/understanding-cost), [Groq rate limits](https://console.groq.com/docs/rate-limits), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Application query quotas bound request counts, not a provider's invoice. Token price configuration is needed before any USD estimate is meaningful; unknown cost must remain unknown. Keep OpenAI paid use disabled unless explicitly chosen. The application never automatically upgrades a plan. Do not enter billing details merely to make a test pass.

Free Render memory may be insufficient for simultaneous embedding, reranking and API concurrency. The ONNX model path reduces dependencies but still needs actual memory profiling. Start with a small corpus and one process, cache models during image build if necessary, and measure before announcing a live demo. If the hosted resource cannot execute the pipeline, use an honest unavailable state or clearly labeled recorded walkthrough. No public URL has been verified in this repository.
