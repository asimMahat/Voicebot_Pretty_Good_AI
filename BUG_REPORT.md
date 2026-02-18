# Bug Report — Pretty Good AI Voice Agent

> Findings from automated and manual testing against the Pretty Good AI test line (`805-439-8008`).

---

## Bug #1: Agent Exposes "Demo Patient" Terminology to Callers

| Field         | Detail |
|---------------|--------|
| **Severity**  | Medium |
| **Scenario**  | New Patient Scheduling |
| **Reproduce** | Call the test line and say "I'm a new patient and I'd like to schedule an appointment for a general checkup." |

**What happened:**
When a caller requests to schedule a general checkup, the agent responds with:

> "Help you schedule a general checkup, would you like to create a demo patient"

**Why this is a problem:**
- The phrase "create a demo patient" is internal system terminology that should never be exposed to a real caller.
- A genuine patient would not understand what "demo patient" means and would likely be confused or concerned.
- It breaks the natural scheduling flow — when the caller says "No" (as any real patient would), the conversation stalls and effectively ends.

**Expected behavior:**
The agent should proceed with the scheduling flow directly — collecting patient name, date of birth, insurance, preferred times, etc. — without asking the caller to "create a demo patient."

**Transcript evidence:**

```
[AI AGENT   ]: Help you schedule a general checkup, would you like to create a demo patient
[PATIENT BOT]: No, I'm looking to schedule my appointment as a new patient. What days do you have open?
(call ended shortly after — agent did not continue)
```

---

*More findings will be added as additional test calls are completed.*


