# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

My initial design focuses on three core user actions to ensure the app is functional and user-centric:
1. **Profile Setup:** Allowing the user to input pet details and define the owner's specific time "budget" for the day.
2. **Task Management:** Enabling the addition and editing of care tasks with specific durations and priority rankings (1-5).
3. **Smart Scheduling:** Generating a daily plan that fits within the time budget and provides a natural language explanation for why certain tasks were prioritized.

To support these actions, I have structured the system into four decoupled classes using Python `dataclasses`:
* **User**: Stores the owner's profile and the primary time constraint (`available_time_mins`).
* **Pet**: Acts as a container for animal-specific data and manages the collection of `Task` objects.
* **Task**: A lightweight object representing a single activity (e.g., "Meds," "Walk"), carrying the data needed for the scheduling algorithm.
* **CarePlanner**: The "Engine" class. It references the `User` and `Pet` to perform the scheduling logic and store the generated `reasoning` for the user.


**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
