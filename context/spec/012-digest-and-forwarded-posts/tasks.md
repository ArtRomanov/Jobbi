# Tasks: Digest Posts and Forwarded Posts

Conventions for every slice:
- Tests ship in the slice that adds the behaviour: pytest (backend), Vitest + MSW (frontend).
- Frontend tools run through `corepack pnpm`; `schema.d.ts` is regenerated after every API change.
- Standard SQLAlchemy only. Slices go in order; each adds at most one Alembic migration, so the chain stays linear.
- Library APIs (python-telegram-bot `reply_to_message_id`, Groq JSON mode) are checked against current docs, not memory.
- **Parallel work:** at the start of each slice, independent sub-tasks (and independent parts of later slices) run with extra agents in separate worktrees, then are integrated in order.

---

- [ ] **Slice 1: Exclude words are switched off**
  - [ ] Remove the pre-filter call from `_store_posts`; drop `posts_excluded` from the run report. Update tests. **[Agent: python-backend]**
  - [ ] Remove the exclude-words block from the search settings form (`features/manage-sources`), send only the description; update the slice `CLAUDE.md`. Vitest. **[Agent: typescript-frontend]**
  - [ ] Verify: a user with saved exclude words gets a post containing one rated by the AI; the Sources panel has no exclude-words block (Chrome MCP). **[Agent: qa-tester]**

- [ ] **Slice 2: Long posts — 3,000-character window and the ✂️ alert**
  - [ ] Migration: `vacancy_seen_keys.cut_for_ai` (Boolean, default false). **[Agent: database-expert]**
  - [ ] Evaluator: `MAX_POST_CHARS = 3000`; size-based batches (`BATCH_CHAR_BUDGET = 7500`, ≤ 5 posts, one post always allowed). Service: `cut_for_ai`, WARNING log, `posts_cut` in the run report. Tests. **[Agent: python-backend]**
  - [ ] Daily summary: the ✂️ line when N > 0 in the last 24 h. Tests. **[Agent: python-backend]**
  - [ ] Verify: run the worker on a post longer than 3,000 characters; check the flag, the log line and the summary line. **[Agent: qa-tester]**

- [ ] **Slice 3: Digests from watched channels become separate cards**
  - [ ] Migration: `vacancies.links` (JSON, nullable). **[Agent: database-expert]**
  - [ ] `RawPost.links` (`PostLink(line, url)`); `fetchers/telegram.py` records each link's line; `_store_posts` writes `links`. Tests incl. a parser fixture with links on different lines. **[Agent: python-backend]**
  - [ ] Evaluator: numbered lines; answer variant B (`vacancy_count`, `vacancies[]` with `lines`, ≤ 20); validation (ranges, invalid items, all invalid → attempt); DIGESTS prompt section. Unit tests. **[Agent: python-backend]**
  - [ ] Service: split into `<key>#n` cards (fragment, job link by line, copied fields, card sources); merge by job link; delete the pending row; alerts count cards. FakeGroq answers digests. Tests. **[Agent: python-backend]**
  - [ ] Behavioural AI check: add the functional reference digests and the real "100% remote jobs 18 Nov" post to `scripts/smoke_evaluator.py`; run live on `gpt-oss-20b`; on `finish_reason=length` raise `MAX_COMPLETION_TOKENS` to 6000. **[Agent: python-backend]**
  - [ ] Code review: prompt injection (fence, line validation), no network inside transactions, the 20-card cap. **[Agent: general-purpose]**
  - [ ] Verify: a real digest from a watched channel after a first scan; each card has its own fragment and link (Chrome MCP + DB). **[Agent: qa-tester]**

- [ ] **Slice 4: Forwarded posts — same rules and a reply with the result**
  - [ ] Migration: `forwarded_posts` table; daily cleanup after 30 days. **[Agent: database-expert]**
  - [ ] Remove PR #35 leftovers (`_keep_forwarded`, `NOT_*_REASON`, `_PendingRow.forwarded`, store-time merge, `MERGED_MESSAGE`); `store_forwarded_post` writes `links` from entities and a `forwarded_posts` row; new reply texts. Tests. **[Agent: python-backend]**
  - [ ] Worker: outcomes per forwarded post (`matched` / `merged` / `none` / `not_vacancy` / `unratable`); after the run, reply with `reply_to_message_id` outside any transaction, then set `reported_at` (also on `TelegramError`). FakeBot tests for every text incl. "… is already in your Inbox.". **[Agent: python-backend]**
  - [ ] Verify live: forward a new digest and a single post from a private channel; check the cards and the second bot message (bot and worker restarted). **[Agent: qa-tester]**

- [ ] **Slice 5: Gates and finish**
  - [ ] `/pre-merge` (incl. the behavioural AI check) and `/security-review` over the branch; fixes with tests. **[Agent: general-purpose]**
  - [ ] PR, merge after approval; `/awos:verify` → criteria checked, 012 Completed. **[Agent: general-purpose]**
