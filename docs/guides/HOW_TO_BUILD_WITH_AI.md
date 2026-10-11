# How to build your part with an AI assistant

Read this once before opening your personal guide:
[Frontend](FRONTEND_GUIDE.md) · [Backend](BACKEND_GUIDE.md) · [AI agent](AI_GUIDE.md)

## The loop (repeat for every part)

1. **Read** the part in your guide: *what you're building* and *concepts*. Don't skip the
   concepts — judges will ask you to explain your code.
2. **Paste** the part's prompt into your AI assistant.
3. **Read** the code it gives you before running it. Ask *"explain this line"* for anything unclear.
4. **Run** it and do the **Check**. If it fails, paste the full error message back (see below).
5. **Commit** with the suggested message and `git push`.

Small steps win. If the AI writes 300 lines at once, ask it to split the work.

## Which tool?

| Tool | Can it see our repo? | What to do |
|---|---|---|
| Claude Code, Cursor, Copilot Chat in VS Code | Yes | Prompts say "read docs/API.md" — it will open the file itself |
| ChatGPT / Claude in the browser | No | When a prompt mentions a file, **paste that file's contents** under the prompt |

## Start every new chat with the Context Prompt

Each guide begins with a **Context Prompt**. Paste it once at the start of every new chat
session — it tells the AI the project, your role, the rules, and which files you may touch.
Without it, the AI will guess, rename fields, and break the contract.

## When something breaks — the debugging prompt

```
This doesn't work.
What I did: <command you ran / button you clicked>
What I expected: <...>
What happened: <full error message, copied exactly, including the stack trace>
Relevant file: <paste the file or name it>
Explain the cause in simple words first, then give the smallest fix. Don't rewrite unrelated code.
```

## Rules for working with AI (all three of us)

- **Never paste your Groq key** (or `.env`) into any AI chat.
- **Never accept a change to field names or endpoints** that differs from `docs/API.md`.
  If the AI suggests one, say: *"No — the contract in docs/API.md is fixed. Adapt the code to it."*
- **Don't let it edit files outside your folder.** If it needs something from a teammate, ask the teammate.
- **Don't add libraries** without a reason. Ask: *"Can we do this without a new dependency?"*
- **You must be able to explain every file you commit.** If you can't, ask the AI:
  *"Explain this file to me as if I'm a beginner, then quiz me with 3 questions."*
- Commit after each part. If a step goes badly wrong: `git restore <file>` returns it to the last commit.

## Before your demo — understanding check prompt

```
Here is my code for <part>. Ask me 5 questions a hackathon judge might ask about it,
one at a time. After each answer, tell me what I got right and what I missed.
```
