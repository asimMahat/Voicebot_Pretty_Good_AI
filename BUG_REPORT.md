# Bug Report — Pretty Good AI Voice Agent

> Findings from automated and manual testing against the Pretty Good AI test line (`805-439-8008`).

---

## Bug #1: Agent Exposes "Demo Patient" Terminology to Callers
### Scenario: New Patient Scheduling

| Field            | Detail |
|------------------|--------|
| **Severity**     | Medium |
| **Transcript**   | `20260218_130155_new_patient_scheduling` |
| **Reproduce**    | Call the test line and say "I'm a new patient and I'd like to schedule an appointment for a general checkup." |

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
[AI Agent (PrettyGoodAI)  ]: Help you schedule a general checkup, would you like to create a demo patient
[Patient Bot (GPT-4o-mini)]: No, I'm looking to schedule my appointment as a new patient. What days do you have open?
(call ended shortly after — agent did not continue)
```

---

## Bug #2: Agent Misclassifies Scheduling Request as Billing
### Scenario: New Patient Scheduling

| Field            | Detail |
|------------------|--------|
| **Severity**     | High |
| **Transcript**   | `20260218_141347_new_patient_scheduling` |
| **Reproduce**    | Call the test line and say "Hi, I'm a new patient and I'd like to schedule an appointment." |

**What happened:**
The patient clearly requested to **schedule an appointment**, but the agent classified the intent as a **billing question** and routed the conversation down the wrong path:

> "Got it. I can help with billing or insurance questions."
> "Thanks, Sarah. To help with your billing question, can you please tell me your date of birth?"

The patient had to explicitly correct the agent: *"Actually, I just want to schedule a new patient appointment for a general checkup."*

**Why this is a problem:**
- Core intent recognition failure — "schedule an appointment" should never be classified as a billing question.
- Forces the patient to repeat themselves and correct the agent, creating a frustrating experience.
- Wastes call time going down the wrong conversational path.

**Expected behavior:**
The agent should correctly identify "schedule an appointment" as a scheduling request and proceed with collecting scheduling details (preferred times, provider, etc.).

**Transcript evidence:**

```
[Patient Bot (GPT-4o-mini)]: Hi, I'm a new patient and I'd like to schedule an appointment.
[AI Agent (PrettyGoodAI)  ]: Thanks for calling Pivot Point Orthopaedics. Part of Pretty Good AI. Am I speaking with Sarah?
[Patient Bot (GPT-4o-mini)]: Yes, that's me.
[AI Agent (PrettyGoodAI)  ]: Got it. I can help with billing or insurance questions.
[AI Agent (PrettyGoodAI)  ]: Thanks, Sarah. To help with your billing question, can you please tell me your date of birth?
[Patient Bot (GPT-4o-mini)]: Actually, I just want to schedule a new patient appointment for a general checkup.
```

---

## Bug #3: Agent Misgenders Patient
### Scenario: New Patient Scheduling

| Field            | Detail |
|------------------|--------|
| **Severity**     | Medium |
| **Transcript**   | `20260218_141347_new_patient_scheduling` |
| **Reproduce**    | Call as a female patient named "Sarah" and request to schedule. |

**What happened:**
The agent addressed Sarah (a female name) as **"sir"**:

> "Got it, sir. For a general checkup, we can book a new patient consultation."

**Why this is a problem:**
- Addressing a patient with the wrong gender is disrespectful and unprofessional.
- In a medical office context, getting the patient's gender wrong raises concerns about record accuracy.
- If the patient's name is clearly gendered (Sarah), the agent should use the correct honorific or avoid gendered terms altogether.

**Expected behavior:**
The agent should either use "ma'am" for clearly female names, or avoid gendered terms entirely (e.g., just say "Got it, Sarah").

**Transcript evidence:**

```
[Patient Bot (GPT-4o-mini)]: Actually, I just want to schedule a new patient appointment for a general checkup.
[AI Agent (PrettyGoodAI)  ]: Got it, sir. For a general checkup, we can book a new patient consultation.
```

---

## Bug #4: DOB Mismatch Accepted Without Verification
### Scenario: New Patient Scheduling

| Field            | Detail |
|------------------|--------|
| **Severity**     | Low |
| **Transcript**   | `20260218_141347_new_patient_scheduling` |
| **Reproduce**    | Provide any date of birth during the demo patient flow. |

**What happened:**
The agent acknowledged the birthday doesn't match records but accepted it anyway:

> "The birthday you gave doesn't match our records, but for demo purposes, I'll accept it."

**Why this is a problem:**
- In a production environment, accepting a mismatched DOB is a security/identity verification failure.
- The phrase "for demo purposes" should not be exposed to callers (same class of issue as Bug #1).

**Transcript evidence:**

```
[Patient Bot (GPT-4o-mini)]: Sure, it's March 15, 1991.
[AI Agent (PrettyGoodAI)  ]: The birthday you gave doesn't match our records, but for demo purposes, I'll accept it.
```

---

## Bug #5: Agent Assumes Caller Is Previous Demo Patient
### Scenario: Reschedule Appointment

| Field            | Detail |
|------------------|--------|
| **Severity**     | Medium |
| **Transcript**   | `20260218_143056_reschedule_appointment` |
| **Reproduce**    | Call the test line after a previous call created a demo patient. Say "I need to move my appointment." |

**What happened:**
The agent assumed the caller was "Sarah" (the demo patient from a previous session):

> "Thanks for calling PivotPoint Orthopedics. Part of Pretty Good AI. Am I speaking with Sarah?"

The actual caller was David Thompson.

**Why this is a problem:**
- The agent should not carry over state from previous calls and assume all callers are the same person.
- A real patient would be confused or concerned that the system has the wrong name.

**Expected behavior:**
The agent should ask "Who am I speaking with?" or "May I have your name?" instead of guessing.

**Transcript evidence:**

```
[AI Agent (PrettyGoodAI)  ]: Thanks for calling PivotPoint Orthopedics. Part of Pretty Good AI. Am I speaking with Sarah?
[Patient Bot (GPT-4o-mini)]: No, this is David Thompson. I'd like to reschedule my appointment.
```

---

## Bug #6: Agent Asks Patient to Spell Name Twice
### Scenario: Reschedule Appointment

| Field            | Detail |
|------------------|--------|
| **Severity**     | Low |
| **Transcript**   | `20260218_143056_reschedule_appointment` |
| **Reproduce**    | Provide name and spell it when asked, then wait for agent response. |

**What happened:**
The patient spelled their full name (D-A-V-I-D T-H-O-M-P-S-O-N), but the agent asked them to spell it again:

> "Please spell your first and last name for me one more time."

**Why this is a problem:**
- Asking a patient to repeat information they already provided is frustrating and wastes time.
- The agent should acknowledge it couldn't find a match after the first attempt rather than silently asking again.

**Transcript evidence:**

```
[Patient Bot (GPT-4o-mini)]: Yes, that's correct. My first name is spelled D-A-V-I-D and my last name is T-H-O-M-P-S-O-N.
[AI Agent (PrettyGoodAI)  ]: Would you like me to look up your record using the phone number you have on file with us?
[Patient Bot (GPT-4o-mini)]: I'm not sure of the phone number on file. Can we just confirm my name and date of birth again?
[AI Agent (PrettyGoodAI)  ]: No problem. Please spell your first and last name for me one more time.
```

---

## Bug #7: Agent Fails to Complete Task — Gives Up on Rescheduling
### Scenario: Reschedule Appointment

| Field            | Detail |
|------------------|--------|
| **Severity**     | High |
| **Transcript**   | `20260218_143056_reschedule_appointment` |
| **Reproduce**    | Call to reschedule an appointment as a patient not in the system. |

**What happened:**
After the patient provided their name (twice), date of birth, and spelled their name (twice), the agent could not find the record and gave up entirely:

> "I can't proceed further right now, but I can make sure our clinic support team follows up with you. Please hold on while I document your request for rescheduling your appointment."

The rescheduling was **never completed**. The patient was left on hold with no resolution.

**Why this is a problem:**
- The patient called for a specific task (reschedule) and the task was never accomplished.
- The agent offered no alternatives: transfer to a human, create a new record, search by different criteria, or provide a callback number.
- Telling a patient "I can't proceed" with no actionable next step is a dead-end experience.

**Expected behavior:**
The agent should offer alternatives when a record lookup fails — transfer to a live person, offer to take a message, or provide a direct number the patient can call back.

**Transcript evidence:**

```
[Patient Bot (GPT-4o-mini)]: Sure! My name is David Thompson, spelled D-A-V-I-D T-H-O-M-P-S-O-N. My date of birth is February 3, 1980.
[AI Agent (PrettyGoodAI)  ]: I can't proceed further right now, but I can make sure our clinic support team follows up with you. Please hold on while I document your request for rescheduling your appointment.
[Patient Bot (GPT-4o-mini)]: Okay, thanks for your help. I'll hold on.
(call ended — task never completed)
```

---

## Bug #8: Agent Never Answers Direct Insurance Question
### Scenario: Insurance Coverage Question

| Field            | Detail |
|------------------|--------|
| **Severity**     | High |
| **Transcript**   | `20260219_120136_insurance_question` |
| **Reproduce**    | Call and ask "Do you accept Aetna PPO?" repeatedly. |

**What happened:**
The patient asked **"Do you accept Aetna PPO?"** **7 times** throughout the 146-second call, and the agent **never answered the question**. Instead, the agent:
- Asked for the patient's name (even though they already said "Priya Patel")
- Asked for date of birth
- Asked to spell the name multiple times
- Asked for phone number
- Repeatedly asked to confirm name/DOB

The call ended without ever answering whether Aetna PPO is accepted.

**Why this is a problem:**
- The patient called with a **specific, simple question** that should be answerable without any patient information.
- Insurance acceptance is typically public information that doesn't require patient verification.
- The agent treated it as a patient lookup task instead of an informational question.
- This is a complete failure to fulfill the caller's intent — the entire call was wasted.

**Expected behavior:**
The agent should answer the insurance question directly: "Yes, we accept Aetna PPO" or "No, we don't accept Aetna PPO" or "Let me check our accepted plans." Patient verification should only be needed if the caller wants to check their specific coverage or benefits.

**Transcript evidence:**

```
[Patient Bot]: Hi, I had a quick question about what insurance you accept. Do you accept Aetna PPO?
[AI Agent]: Thanks for calling... Am I speaking with Sarah?
[Patient Bot]: No, this is Priya Patel. I'm just checking about insurance acceptance. Do you accept Aetna PPO?
[AI Agent]: Got it, Priya. Can help with your insurance question. May I have your date of birth to look up your information?
[Patient Bot]: I'm just inquiring about the insurance. My date of birth is June 15, 1984. Do you accept Aetna PPO?
[... 4 more times asking the same question ...]
[Patient Bot]: That's okay. I'm just interested in knowing if you accept Aetna PPO. Could you let me know?
(call ended — question never answered)
```

---

## Bug #9: Agent Misnames Patient as "Bria" Instead of "Priya"
### Scenario: Insurance Coverage Question

| Field            | Detail |
|------------------|--------|
| **Severity**     | Medium |
| **Transcript**   | `20260219_120136_insurance_question` |
| **Reproduce**    | Call as "Priya Patel" and provide name multiple times. |

**What happened:**
The patient clearly stated their name is **"Priya Patel"** multiple times, but the agent addressed them as **"Bria"**:

> "Thanks, Bria. Just to confirm, your"

**Why this is a problem:**
- Getting a patient's name wrong is unprofessional and shows the system isn't listening properly.
- The patient had to correct the agent: *"I think there's a mix-up with my name; it's Priya."*
- This erodes trust in the system's accuracy.

**Expected behavior:**
The agent should correctly capture and use the name the patient provides. If there's any uncertainty, the agent should ask for clarification rather than guessing a different name.

**Transcript evidence:**

```
[Patient Bot]: No, this is Priya Patel. I'm just checking about insurance acceptance.
[AI Agent]: Got it, Priya. Can help with your insurance question...
[Patient Bot]: I'm just inquiring about the insurance. My date of birth is June 15, 1984.
[AI Agent]: Thanks, Bria. Just to confirm, your
[Patient Bot]: I think there's a mix-up with my name; it's Priya.
```

---

## Bug #10: Agent Mishears Spelled Name Despite Correct Spelling
### Scenario: Insurance Coverage Question

| Field            | Detail |
|------------------|--------|
| **Severity**     | Low |
| **Transcript**   | `20260219_120136_insurance_question` |
| **Reproduce**    | Spell your last name clearly as "P-A-T-E-L" when asked. |

**What happened:**
The patient spelled their last name clearly: **"P-A-T-E-L"**, but the agent heard it as **"p a t l"** (missing the E) and asked for confirmation:

> "Just to confirm, your last name is spelled p a t l Is that correct, or should it be p a t e l?"

**Why this is a problem:**
- The patient spelled it correctly, but the agent's speech recognition failed to capture the "E".
- This forces the patient to repeat information unnecessarily.
- In a medical context, name accuracy is critical for record matching.

**Expected behavior:**
The agent should correctly capture spelled letters, especially common names like "Patel". If uncertain, the agent should ask the patient to repeat the spelling rather than guessing incorrectly.

**Transcript evidence:**

```
[AI Agent]: Could you please spell out your first and last name for me just to make sure I have it right?
[Patient Bot]: Sure! It's P-R-I-Y-A P-A-T-E-L. Do you accept Aetna PPO?
[AI Agent]: Thanks for spelling that out, Priya. Just to confirm, your last name is spelled p a t l Is that correct, or should it be p a t e l?
[Patient Bot]: It's P-A-T-E-L.
```

---

## Bug #11: Agent Assumes Caller Is "Sarah" in Insurance Scenario
### Scenario: Insurance Coverage Question

| Field            | Detail |
|------------------|--------|
| **Severity**     | Medium |
| **Transcript**   | `20260219_120136_insurance_question` |
| **Reproduce**    | Call the test line and ask an insurance question without identifying yourself first. |

**What happened:**
The patient called and immediately asked about insurance acceptance, but the agent assumed they were "Sarah":

> "Thanks for calling PivotPoint Orthopaedics. Part of Pretty Good AI. Am I speaking with Sarah?"

The actual caller was Priya Patel.

**Why this is a problem:**
- Same issue as Bug #5 — the agent carries over state from previous calls.
- The agent should not assume all callers are the same person.
- This creates confusion and requires the patient to correct the agent.

**Expected behavior:**
The agent should ask "Who am I speaking with?" or "May I have your name?" instead of assuming the caller's identity.

**Transcript evidence:**

```
[Patient Bot]: Hi, I had a quick question about what insurance you accept. Do you accept Aetna PPO?
[AI Agent]: Thanks for calling PivotPoint Orthopaedics. Part of Pretty Good AI. Am I speaking with Sarah?
[Patient Bot]: No, this is Priya Patel. I'm just checking about insurance acceptance.
```

---


*More findings will be added as additional test scenarios are completed.*
