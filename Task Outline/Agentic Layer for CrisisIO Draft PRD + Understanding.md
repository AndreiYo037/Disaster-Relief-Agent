Handwritten for recording purposes only. To be used for slides compilation and logic knowledge. 

In chronological order of brainstorming process for verification, checking, and reference purposes

TO ENSURE ALL OF THESE REQUIREMENTS (AS STATED IN HACKATHON DOCS) TO BE CROSSED OFF BEFORE SHIPPING)

| Requirement | Done? |
| :---- | :---- |
| Use a typed shared graph state for observations,     reviews, confidence, provenance, errors, and     outputs. | y |
| Add reducers for fields written by parallel agents;     otherwise concurrent updates can conflict or be     lost. | **Not fully thought through.**                           Your four layer loops will                           likely run in parallel, so you                           need separate result slots or                           merge rules.  |
| Bound every loop with a hard counter. LangGraph also     has a recursion/step limit. | **Not thought through yet.** Add                           limits such as max\_retries \= 2                           or max\_review\_rounds \= 3.  |
| Keep agents short and specialized. Do not pass full     documents or raw tool logs between every agent; pass     references or compact typed results. | the data                           passed between stages is not                           defined. |
| Use explicit tool allow-lists and validate all model     IDs/regions. | **Not thought through yet.** This                           matters when you deploy to AWS                           Bedrock, less so for a local                           prototype.                            permissions. |

| Include error handling, retries, and partial-failure     behavior. | Not fully thought through.                           Disaster information cannot                           simply fail the entire                           workflow because one input is                           Unavailable. (Decide what happens when one                           source fails, an agent returns                           invalid data, or two sources                           disagree.) |
| :---- | :---- |
| Preserve human approval before consequential     actions. Your existing code already enforces this     through mint\_permit(...). | Y |
| Measure schema-valid output, tool-call success,     completion rate, token cost, loop iterations, and     answer fidelity. | **Not fully thought through.** You                           need test cases and metrics                           for verification accuracy,                           unsupported claims, latency,                           and cost. |

Extra requirements to consider:

- Tool Allow Lists: Clearly define permissions per agent  
- Provenance: Y

**DATABASE ENGINEER AND FORMATTING**  
Evidence \= what a source provided  
  Claim    \= what that evidence says happened  
  Verification \= whether the claim is adequately  
  supported  
  Evaluation \= what priority or action the claim  
  Deserves

ONE database with separate  
  logical records:

  *evidence*  
    *raw source artifacts, hashes, timestamps,*  
    *provenance*

  *claims*  
    *normalized statements linked to evidence IDs*

  *verification\_runs*  
    *check results, score, verdict, verifier version*

  *evaluations*  
    *priority, action recommendation, missing*  
    *information*

What I put together is an agentic workflow featuring **15 ai agents working together in a graph engineered loop**. 

Layer 1:  
    source agent \-\> verification agent \-\> evaluation agent  
  Layer 2:  
    source agent \-\> verification agent \-\> evaluation agent  
  Layer 3:  
    source agent \-\> verification agent \-\> evaluation agent  
  Layer 4:  
    source agent \-\> verification agent \-\> evaluation agent  
                                        ↓  
                                Dispatch  
↓  
Orchestrator  
                                        ↓  
                           final summariser / UI output

Satellite agent ─────┐  
  Field-report agent ──┼──\> Shared evidence store  
  Community agent ─────┘

**Source agent**  
Logic and proposal   
Sources (Source Agent):   
Satellite  
Telemetry  
Field Reports (1st responders)  
Community Reports

They will connect directly to the relevant APIs/MCPs to scrape data.   
Then, they will send the data towards the evidence store, and straight to the UI to update the live 3d model. 

**Verifcation Agent:**   
All 4 source agent’s will send their results separately to a shared {evidence\_pool}.   
This evidence pool can be used to cross reference each loop for the verification stage. I propose the following metric. There will be 5 checks in total, refer below For Me: These tests must be proven during hackathon testing phase

\- PASS (4 or 5 checks): valid claim, reliable  
    provenance, matching time/  
    location, and sufficient  
    independent support.

  \- FAIL (0 or 1 checks) : malformed, impossible,  
    contradictory, or clearly  
    unsupported claim.

  \- UNKNOWN (2 or 3 checks): claim is  
    plausible but lacks enough  
    corroboration. This should not  
    automatically mean false.

**Check**                   **1\. Provenance**  
   **What it determines**      Whether the evidence is  
                           traceable and  
                           attributable  
   **Example pass condition**  Report has an author/  
                           source ID, timestamp, and  
                           evidence reference  
  ──────────────────────────────────────────────────  
   **Check**                   **2\. Schema/completeness**  
   **What it determines**      Whether required fields  
                           exist  
   **Example pass condition**  Claim includes what  
                           happened, where, and when  
  ──────────────────────────────────────────────────  
   **Check**                   **3\. Time/location validity**  
   **What it determines**      Whether the observation  
                           is fresh and  
                           geographically plausible  
   **Example pass condition**  Timestamp is within 6  
                           hours and coordinates are  
                           valid  
  ──────────────────────────────────────────────────  
   **Check**                   **4\. Internal consistency**  
   **What it determines**      Whether the source  
                           contradicts itself or  
                           contains impossible  
                           values  
   **Example pass condition**  Text says “road flooded,”  
                           while attached metadata  
                           says “no water detected”  
  ──────────────────────────────────────────────────  
   **Check**                   **5\. Corroboration**  
   **What it determines**      Whether independent  
                           evidence supports the  
                           same claim  
   **Example pass condition**  Satellite data or another  
                           unrelated report agrees  
                           within the configured  
                           time/distance tolerance

For a hackathon, make each check visibly \*\*\*\*\*FOR ME\*\*\*\*\*\*  
  inspectable in the UI:

  {  
   "claim": "Road X is flooded",  
   "checks": {  
     "provenance": "pass",  
     "completeness": "pass",  
     "time\_location": "pass",  
     "internal\_consistency": "pass",  
     "corroboration": "fail"  
   },  
   "verdict": "PASS",  
   "confidence": 0.72,  
   "reason": "Valid, recent report with no  
   independent confirmation."  
  }

**PROPOSAL FOR ANDREI (UNDERLINE IF APPROVED)**  
**There is currently no concrete way to verify the legitimacy of several examples of sources for example: Post disaster, If a man passing by an abandoned house hears people trapped below and makes a call \- How would the AI verify the legitimacy of this information? If the satellite imagery cannot view the area accurately, can we just ignore the report? In my opinion, we should not ignore it but create a separate tab in the visual layer that separates Verified information and Unverified information. Both tabs should be ranked based on ai determined priorities. I think we should not throw away unverified information and propose dispatching personnel/activing drones and robotics to site for analysis.** 

**Evaluation Agent:**   
We use this as a decision utility pass, not truth check again. 

The verifier answers the question to the evaluator:

  \> “Is this claim supported?”

  The evaluator answers:

  \> “Given that support, what should the system do  
  \> with it?”

**Each loop should receive only:**

  **\- Verified claim**  
  **\- Verification score and failed checks**  
  **\- Evidence references**  
  **\- Existing evidence pool**  
  **\- Current mission objective**  
  **\- Prior related claims**

**If verification \!= PASS:**  
      **decision \= HOLD (store in CLAIMS portion of db)**

+ **ADD DECISION TO MOVE TO THE UNVERIFIED PART OF VISUAL UI**

**Otherwise:**  
      **Total (10 points total) \= relevance \+ actionability \+ freshness**  
      **\+ impact \+ coverage** 

score the claim on five evaluation metrics:

   **Metric              Question**  
  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  
   Relevance (2 points)          Does this affect the current  
                       disaster-response objective?  
  ──────────────────  ──────────────────────────────  
   Actionability (2 points)     Can an agency act on it  
                       immediately?  
  ──────────────────  ──────────────────────────────  
   Freshness  (2 points)         Is the information recent  
                       enough for this event type?  
  ──────────────────  ──────────────────────────────  
   Impact  (2 points)            How many people or critical  
                       assets could be affected?  
  ──────────────────  ──────────────────────────────  
   Coverage/novelty (2 points)    Does it add new information  
                       or merely duplicate existing  
                       evidence?

We can use this grading system temporarily for the hackathon purposes, of course it will need to be refined if pushed to production level:  
7-10 \-\> REQUEST HUMAN APPROVAL IMMEDIATELY  
      3-6  \-\> MONITOR or REQUEST MORE EVIDENCE  
      0-2  \-\> Move to CLAIMS portion of DB \+ **ADD DECISION TO MOVE TO THE UNVERIFIED PART OF VISUAL UI**  
Each evaluation agent should emit something like:

  {  
   "claim\_id": "claim-1042",  
   "decision": "DISPATCH\_CANDIDATE",  
   "scores": {  
     "relevance": 2,  
     "actionability": 2,  
     "freshness": 2,  
     "impact": 2,  
     "coverage": 1  
   },  
   "priority": 90,  
   "next\_step": "Request field confirmation and  
   route alternative",  
   "missing\_information": \["estimated affected  
   population"\]  
  }  
For the four loops, specialize the rubric  
  slightly:

  \- Satellite loop: area affected, confidence in  
    detected change, coverage, persistence over  
    time.

  \- Field-report loop: operational specificity,  
    reporter proximity, urgency, missing resources.

  \- Community-report loop: geographic coverage,  
    number of independent reports, local detail,  
    duplication risk.

  \- Cross-source loop: agreement, contradiction  
    resolution, and whether sources add genuinely  
    independent evidence.

Technical note: This agent will need its own exclusive RAG insert that retrieve:  
  \- Related claims already in the evidence pool  
  \- Source reliability and verification history  
  \- Response policies and priority rules  
  \- Labeled examples of similar scenarios  
  \- Contradictory or duplicate reports

It will also need a harness, but im not making a goddamn harness for a hackathon. For the editors reading, just include this in your slides

‘We added a harness that repeatedly feeds known scenarios through the  
  real agent pipeline, compares the agent’s output  
  with expected outcomes, and produces metrics.’  
Example report:

  Scenarios: 25  
  Correct decisions: 22  
  False dispatches: 1  
  Missed urgent claims: 1  
  Correct suppressions: 5/5  
  Useful abstentions: 4/5  
  Average latency: 3.2 seconds

**DISPATCH AGENT**  
turns evaluator outputs  into coordinated work: dispatch (human approved), monitor, request evidence, or suppress duplicates.

Each evaluator sends a structured recommendation:

  {  
   "claim\_id": "field-1042",  
   "verification": "PASS",  
   "evaluation\_score": 9,  
   "decision": "DISPATCH\_CANDIDATE",  
   "location": { "lat": 37.77, "lon": \-122.42 },  
   "event\_type": "road\_blocked",  
   "priority": 90,  
   "recommended\_action": "Send road-clearance  
   assessment team",  
   "evidence\_refs": \["field-report-21", "satellite-  
   tile-88"\],  
   "missing\_information": \["road condition beyond  
   junction"\],  
   "expires\_at": "2026-09-06T14:20:00Z"  
  }  
The agents job is to  
1\. **Cluster** claims describing the same event by  
     location, event type, and time window. It  
     creates one incident rather than three  
     independent dispatches.

  2\. **Resolve priority** across incidents. A verified  
     medical emergency with an impact score of 10  
     comes before a verified blocked road scoring 7\.  
PRIORITY FORMULA: Use two separate values:

  \- priority: how harmful and time-critical the incident could be.                                                                  \- confidence: how well-supported the claim is.

  For every incident, normalize agent outputs to 0..1:

  L \= expected loss-of-life risk  
  D \= expected damage severity  
  C \= critical infrastructure/service criticality  
  T \= time criticality  
  V \= verification confidence

  Recommended hackathon formula:

  harm\_score \= 100 \* (  
      0.55 \* L \+  
      0.25 \* D \+  
      0.10 \* C \+  
      0.10 \* T  
  )

  priority \= round(harm\_score \* (0.60 \+ 0.40 \* V))

  V can come directly from the five verification checks:

  V \= passed\_checks / 5

  Use pass \= 1, unknown \= 0.5, and fail \= 0. The 0.60 floor ensures an                                                              unverified but potentially lethal report is still visible and ranked.                                                             Routing rules:

  if L \>= 0.70 and T \>= 0.70:  
      priority \= max(priority, 90\)  
      route \= "URGENT\_HUMAN\_REVIEW"

  elif contradiction or V \< 0.40:  
      route \= "REQUEST\_EVIDENCE"

  elif priority \>= 80 and V \>= 0.80:  
      route \= "DISPATCH\_CANDIDATE"

  elif priority \>= 60:  
      route \= "MONITOR"

  else:  
      route \= "UNVERIFIED"

  Example:

  L=.90, D=.60, C=.80, T=.90, V=.60  
  harm\_score \= 81.5  
  priority \= 68

  Because the life-risk and time-criticality overrides trigger, the  
  final priority becomes 90, but the route remains human review/  
  requested confirmation rather than autonomous dispatch.  
  Keep the existing evaluation score (relevance, actionability,  
  freshness, impact, coverage) separate for deciding the next  
  operational action. Adding it here would double-count impact and  
  freshness. 

3\. **Route work** using clear rules:(we can establish here that we can use BOLDED TEXT and ENLARGED TEXT in the UI to show URGENT human vet needs)

   **Condition                 Orchestrator action**  
  ━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━  
   PASS \+ score 8-10 \+ no    Create incident and  
   active duplicate          send to UI and urgent human vet   
  ────────────────────────  ────────────────────────  
   PASS \+ score 5-7          Put in monitoring  
                             queue; request the  
                             missing evidence, send to ui for human vet  
  ────────────────────────  ────────────────────────  
   REVIEW, contradiction,    Send targeted  
   or conflicting source     verification request  
   conclusions               to the relevant source  
                             Agents, send to UI for human vet  
  ────────────────────────  ────────────────────────  
   FAIL or score 0-4         Archive with an audit  
                             Record, and push to UI under unverified   
  ────────────────────────  ────────────────────────  
   Same incident receives    Upgrade its priority  
   stronger corroboration    and notify dispatch  
  ────────────────────────  ────────────────────────  
   Existing incident is      Re-open evidence  
   stale                     collection or request human vet to close it

The **feedback loop** is the important part:

  Evaluator recommendation  
          \-\>  
  Orchestrator incident state  
          \-\>  
  Dispatch / monitor / evidence-request queue  
          \-\>  
  New satellite, field, or community claims  
          \-\>  
  Verification and evaluation again

  For example, a community report of a collapsed  
  bridge may be verified but only score 6 because  
  the impact is unknown. The orchestrator should ask  
  the satellite agent for a newer image and the  
  field-report agent for route accessibility. When  
  those return, the incident is re-evaluated. It is  
  not a new unrelated claim.

Keep one shared incident record here:

  INCIDENT\_OPEN \-\> MONITORING \-\> DISPATCHED \-\>  
  RESOLVED  
                       |  
                       \-\> NEEDS\_EVIDENCE  
                       |  
                       \-\> CLOSED

4\) Resource Planning Step  
\- Match incident needs to available resources.  
  \- Consider capacity, location, capability, ETA, and  
    competing incidents.

  \- Produce candidate assignments and routes on UI.  
  \- Identify shortages and conflicts.  
  \- Attach evidence references and assumptions.  
  \- Never autonomously deploy resources.

\*WILL NEED TO FORMULATE PRIORITISATION FORMULA USING a) checks and b) damage possibility c) loss of life risk\*

**SUMMARISER AGENT**  
the communication layer between the orchestration system and humans or downstream systems. It converts the orchestrator’s incident state into a concise, traceable operational brief.

**It should:**

  1\. **Summarise the incident**  
      \- What happened  
      \- Where and when  
      \- Current status and severity  
      \- Estimated impact

  2\. **Separate certainty levels**  
      \- Confirmed facts  
      \- Reasonable inferences  
      \- Unknown or conflicting information

  3\. **Preserve provenance**  
      \- Attach evidence references to every  
        important factual statement

      \- Include source count, timestamps, and  
        verification status

  4\. **Report orchestration decisions**  
      \- Current incident state  
      \- Recommended or active actions  
      \- Assigned team or owner  
      \- Deadlines and next update time

  5\. **Expose gaps**  
      \- Missing evidence  
      \- Contradictory reports  
      \- Information that would change the decision

  6\. **Produce audience-specific views**  
      \- Responder brief: immediate actions and  
        hazards

      \- Operations dashboard: status, priority,  
        owner, SLA

      \- Executive summary: scope, impact, and major  
        Decisions

- Display Suggested routes on the UI to different areas of concern,   
- Suggest the most appropriate course of action 

  It must **not** verify evidence, invent facts,  
  reprioritize incidents, or directly dispatch  
  resources. Those decisions remain with the  
  verification, evaluation, and orchestration  
  agents.  
It is the layer that will communicate everything with the UI and update its verified incidents \+ unverified incidents checkbox. 

A minimal output contract:

  {  
   "incident\_id": "INC-1042",  
   "generated\_at": "2026-09-06T14:00:00Z",  
   "headline": "Road blockage reported near  
   Junction 8",  
   "status": "NEEDS\_EVIDENCE",  
   "priority": 72,  
   "location": {"lat": 37.77, "lon": \-122.42},  
   "known\_facts": \[  
     {  
       "statement": "A road blockage was reported  
       near Junction 8.",  
       "evidence\_refs": \["field-report-21",  
       "community-report-88"\]  
     }  
   \],  
   "uncertainties": \[  
     "Extent of blockage is unknown.",  
     "No field confirmation within the last hour."  
   \],  
   "actions": \[  
     {  
       "action": "Request field confirmation",  
       "owner": "assessment\_team",  
       "status": "QUEUED"  
     }  
   \],  
   "contradictions": \[\],  
   "next\_update\_at": "2026-09-06T14:20:00Z"  
  }

  Add a final quality gate:

  \- Every claim has evidence or an explicit  
    uncertainty label.

  \- Summary matches the orchestrator’s current  
    state.

  \- No stale evidence is presented as current.  
  \- Actions have an owner or are marked unassigned.  
  \- Contradictions are visible.  
  \- The summary is versioned and auditable.

  For the hackathon, use a fixed JSON schema plus a  
  template-driven summary. Let the language model  
  improve wording only after the structured fields  
  are validated.

\#\#\#\# CONTEXT: ENTIRE PROJECT OVERVIEW \- NOT JUST THE AGENTIC LAYER, BUT THE ENTIRE PROJECT FOR CONTEXT.

This project is an AI-assisted disaster-response coordination platform: it turns scattered early-disaster information into an operator-reviewed action plan for evacuation, resource allocation, and emergency dispatch. The current build is a hackathon proof of concept focused on showing this workflow clearly through a map, an operational dashboard, and a replayable disaster simulation.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **Project overview**

## **Working description**

**An AI command-and-coordination system for humanitarian disaster response.**

When a disaster begins, responders receive fast-moving, fragmented information from many sources—satellite imagery, sensors, field teams, and the public. The platform brings those inputs together, verifies and prioritizes them, models what is happening on the ground, and recommends coordinated actions such as:

* Where evacuation should be prioritised  
* Which areas require rescue or relief resources  
* How to route convoys or emergency services toward safe zones  
* Which secondary hazards—such as fires, flooding, or waterborne disease—need immediate attention

The system is designed to support, not replace, humanitarian coordinators. AI produces recommendations, while a human operator reviews, edits, approves, or rejects every plan before it is executed.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **The problem**

In the early hours of a major disaster, decision-makers face three challenges:

* Information is fragmented across satellite imagery, telemetry/sensors, first-responder reports, and community channels.  
* Reports can be incomplete, duplicated, unreliable, or too numerous for one team to process quickly.  
* Critical choices—such as evacuation routes, resource dispatch, and hazard prioritisation—must be made before the situation worsens.

The project addresses this by creating a single operational view of the disaster and using specialised AI agents to turn incoming signals into actionable, human-approved plans. The intended use case is early-stage humanitarian coordination during natural disasters.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **How it works**

## **Four parallel data channels**

Rather than relying on one AI agent to process everything in sequence, the project uses a graph-based multi-agent architecture. Separate agents process distinct data streams in parallel, reducing context overload and making the system easier to scale:

| Data source | What it contributes |
| ----- | ----- |
| Satellite imagery | Flood extent, damaged areas, terrain changes, visible infrastructure impact |
| Telemetry and sensors | Environmental and infrastructure signals, such as water levels or other live measurements |
| First-responder reports | Ground-level updates from emergency personnel |
| Community platforms | Reports and signals from affected residents and public channels |

These streams feed into the response system independently, allowing the platform to compare and organise a large volume of mixed information without placing all inputs into a single agent loop.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **AI decision pipeline**

The architecture can be explained in five simple stages:

1. **Perception** — Collect signals from the four data channels and identify possible incidents, hazards, needs, and changes in conditions.  
2. **Verification** — Assess whether reports are credible, corroborated, current, and relevant. This helps prevent weak or unverified reports from driving critical decisions.  
3. **World model** — Build a live operational picture of the disaster: affected zones, population movement, available resources, hazard locations, and safe routes.  
4. **Prioritisation and planning** — Determine which needs are most urgent and generate recommended actions, such as dispatching a convoy, rerouting emergency support, or prioritising an evacuation zone.  
5. **Human approval and execution logging** — Present the recommended plan to a coordinator, who can approve, edit, or reject it. The initial MVP records planned actions and operational logs rather than autonomously controlling real-world resources.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

A later learning layer is intended to store aggregated incident and response data so future disaster responses can benefit from patterns observed in past events.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **What a user sees**

The project is meant to feel like an operational command centre rather than a generic AI chatbot.

## **Main interface**

The user interacts with a map-based dashboard containing:

* A searchable map for locating places quickly.  
* Toggleable hazard layers for floods, fire, and disease.  
* Population movement and risk visualisation, potentially including heat maps.  
* A live operations panel that displays active incidents, recommended plans, and system status.  
* A human-approval interface where an operator can review or amend proposed AI actions.  
* Execution and decision logs showing what the system recommended and what the human operator approved.

## **Replay simulation**

A key feature is a simulation/replay mode that lets users revisit a historical disaster scenario—for example, a Hurricane Katrina-style evacuation and resource-allocation situation—and watch the system process incoming information and recommend responses.

The replay is important because it makes the value proposition visible: judges, investors, or humanitarian stakeholders can see how the platform identifies hazards, tracks population movement, routes support, and proposes dispatch decisions over time. The project team has prioritised a persuasive, understandable replay demonstration over building a fully complex live-disaster backend for the first version.Meeting-started-2026\_09\_05-12\_18-GMT-08\_00-Notes-by-Gemini.pdf

## **Example scenario**

Imagine severe flooding affects several neighbourhoods.

* Satellite data identifies expanding flood zones.  
* Sensors show rising water levels near critical roads.  
* First responders report that one evacuation route is blocked.  
* Community reports indicate residents stranded in a particular district.  
* The system verifies and combines these reports into a common operating picture.  
* It flags the district as high priority, highlights safe routes, and recommends sending an evacuation convoy while redirecting emergency services away from flooded roads.  
* A coordinator sees the plan in the dashboard, edits it if needed, and approves it.  
* The decision is logged, and the simulation visually shows the predicted movement of people and resources.

This demonstrates the platform’s central idea: **AI accelerates situational awareness and planning, while humans remain accountable for final emergency decisions.**

