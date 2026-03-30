from datetime import date

import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

# ---------------------------------------------------------------------------
# Session State — initialize exactly once per browser session
# ---------------------------------------------------------------------------
if "owner_data" not in st.session_state:
    default_pet = Pet(name="Mochi", species="dog", age=3)
    default_owner = Owner(name="Jordan", available_time_mins=60)
    default_owner.pets.append(default_pet)
    st.session_state.owner_data = default_owner

if "owner_name" not in st.session_state:
    st.session_state.owner_name = st.session_state.owner_data.name

if "available_time" not in st.session_state:
    st.session_state.available_time = st.session_state.owner_data.available_time_mins

if "schedule_result" not in st.session_state:
    st.session_state.schedule_result = None

# Stores (pet_name, task_name) of a task the user just clicked "Mark Complete" on.
if "pending_complete" not in st.session_state:
    st.session_state.pending_complete = None

# Stores the name of the most recently completed task for the success toast.
if "last_completed" not in st.session_state:
    st.session_state.last_completed = None

# ---------------------------------------------------------------------------
# Process any pending task completion *before* rendering
# ---------------------------------------------------------------------------
if st.session_state.pending_complete is not None:
    pet_name, task_name = st.session_state.pending_complete
    for pet in st.session_state.owner_data.pets:
        if pet.name == pet_name:
            for task in pet.tasks:
                if task.name == task_name and not task.is_completed:
                    pet.complete_task(task)
                    st.session_state.last_completed = task_name
                    break
    st.session_state.pending_complete = None
    st.session_state.schedule_result = None  # invalidate cached schedule

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🐾 PawPal+")
st.caption("Smart pet care scheduling — tiered optimization, conflict detection, recurring tasks.")

PRIORITY_MAP = {"low": 1, "medium": 3, "high": 5}


def _priority_badge(p: int) -> str:
    if p >= 5:
        return "🔴 High"
    if p >= 3:
        return "🟡 Medium"
    return "🟢 Low"


# ---------------------------------------------------------------------------
# Two-column layout: inputs on the left, results on the right
# ---------------------------------------------------------------------------
col_left, col_right = st.columns([2, 3], gap="large")

# ── LEFT COLUMN: all input forms ──────────────────────────────────────────
with col_left:
    st.subheader("Owner Settings")
    owner_name = st.text_input("Owner name", key="owner_name")
    available_time = st.number_input(
        "Available time (minutes)", min_value=0, max_value=480, key="available_time"
    )
    st.session_state.owner_data.name = owner_name
    st.session_state.owner_data.available_time_mins = int(available_time)

    st.divider()

    # Add Pet form
    st.subheader("Add a Pet")
    with st.form("add_pet_form", clear_on_submit=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            new_pet_name = st.text_input("Pet name")
        with p2:
            new_pet_species = st.selectbox("Species", ["dog", "cat", "other"])
        with p3:
            new_pet_age = st.number_input("Age (years)", min_value=0, max_value=30, value=1)
        submitted_pet = st.form_submit_button("Add Pet", use_container_width=True)

    if submitted_pet:
        if new_pet_name.strip():
            new_pet = Pet(
                name=new_pet_name.strip(),
                species=new_pet_species,
                age=int(new_pet_age),
            )
            st.session_state.owner_data.pets.append(new_pet)
            st.session_state.schedule_result = None
            st.success(f"Pet '{new_pet.name}' added!")
        else:
            st.warning("Please enter a pet name.")

    st.divider()

    # Add Task form
    st.subheader("Add a Task")
    owner = st.session_state.owner_data
    if not owner.pets:
        st.info("Add a pet first before adding tasks.")
    else:
        with st.form("add_task_form", clear_on_submit=True):
            pet_names = [p.name for p in owner.pets]
            selected_pet_name = st.selectbox("Assign to pet", pet_names)

            t1, t2, t3 = st.columns(3)
            with t1:
                task_title = st.text_input("Task title", value="Morning walk")
            with t2:
                duration = st.number_input(
                    "Duration (min)", min_value=1, max_value=240, value=20
                )
            with t3:
                priority_label = st.selectbox("Priority", ["low", "medium", "high"], index=2)

            t4, t5 = st.columns(2)
            with t4:
                frequency = st.selectbox("Frequency", ["one-off", "daily", "weekly"])
            with t5:
                is_required = st.checkbox("Mark as required")

            submitted_task = st.form_submit_button("Add Task", use_container_width=True)

        if submitted_task:
            if task_title.strip():
                new_task = Task(
                    name=task_title.strip(),
                    duration=int(duration),
                    priority=PRIORITY_MAP[priority_label],
                    is_required=is_required,
                    frequency=frequency,
                )
                target_pet = next(
                    p for p in owner.pets if p.name == selected_pet_name
                )
                target_pet.tasks.append(new_task)
                st.session_state.schedule_result = None
                st.success(f"Task '{new_task.name}' added to {target_pet.name}.")
            else:
                st.warning("Please enter a task title.")

# ── RIGHT COLUMN: summary + schedule results ───────────────────────────────
with col_right:
    owner = st.session_state.owner_data

    # Current Summary
    st.subheader("Current Summary")
    st.write(
        f"**Owner:** {owner.name} \u2002|\u2002 "
        f"**Time budget:** {owner.available_time_mins} min"
    )

    if not owner.pets:
        st.info("No pets yet. Add one on the left.")
    else:
        today = date.today()
        for pet in owner.pets:
            due_tasks = [
                t for t in pet.tasks if t.due_date <= today and not t.is_completed
            ]
            label = f"{pet.get_summary()} — {len(due_tasks)} task(s) due today"
            with st.expander(label, expanded=False):
                if not due_tasks:
                    st.caption("No tasks due today or earlier for this pet.")
                else:
                    st.table(
                        [
                            {
                                "Task": t.name,
                                "Duration (min)": t.duration,
                                "Priority": _priority_badge(t.priority),
                                "Frequency": t.frequency,
                                "Required": "✓" if t.is_required else "",
                            }
                            for t in due_tasks
                        ]
                    )

    st.divider()

    # Generate Schedule button
    st.subheader("Daily Plan")
    st.caption(
        "Runs the two-phase tiered scheduler across all pets and tasks."
    )

    if st.button("Generate Schedule", type="primary", use_container_width=True):
        if not owner.pets or not owner.get_all_tasks():
            st.warning("Add at least one pet with at least one task first.")
        else:
            scheduler = Scheduler(owner)
            st.session_state.schedule_result = scheduler.generate_schedule()

    # Success toast for completed tasks
    if st.session_state.last_completed:
        st.success(f"✓ '{st.session_state.last_completed}' marked complete!")
        st.session_state.last_completed = None

    result = st.session_state.schedule_result
    if result is not None:

        # ── Executive Summary ──────────────────────────────────────────────
        if "Time Deficit" in result.reasoning:
            st.error(f"⚠️ {result.reasoning}")
        else:
            st.info(result.reasoning)

        # ── Visual Time Budget ─────────────────────────────────────────────
        budget = owner.available_time_mins
        time_used = result.total_time_used
        if budget > 0:
            progress_val = min(time_used / budget, 1.0)
            over = f" (+{time_used - budget} over budget)" if time_used > budget else ""
            st.progress(
                progress_val,
                text=f"Time used: {time_used} / {budget} min{over}",
            )
        else:
            st.progress(0.0, text="No time budget set.")

        # ── Actionable Conflict Warnings ───────────────────────────────────
        conflicts = Scheduler(owner).detect_conflicts(result.scheduled_tasks)
        for task_a, task_b in conflicts:
            st.warning(
                f"**Overlap Detected:** _{task_a.name}_ ends at **{task_a.end_time}** "
                f"but _{task_b.name}_ starts at **{task_b.start_time}**."
            )

        # ── Professional Schedule Table + Mark Complete ────────────────────
        if result.scheduled_tasks:
            st.markdown("#### Scheduled Tasks")

            # Build a task-id → pet lookup so we can call pet.complete_task()
            task_pet_map: dict[int, Pet] = {}
            for pet in owner.pets:
                for task in pet.tasks:
                    task_pet_map[id(task)] = pet

            # Column header row
            h_name, h_dur, h_pri, h_start, h_action = st.columns(
                [3, 1.2, 1.5, 1.2, 2]
            )
            h_name.markdown("**Name**")
            h_dur.markdown("**Duration**")
            h_pri.markdown("**Priority**")
            h_start.markdown("**Start**")
            h_action.markdown("")

            for i, task in enumerate(result.scheduled_tasks):
                pet = task_pet_map.get(id(task))
                c_name, c_dur, c_pri, c_start, c_action = st.columns(
                    [3, 1.2, 1.5, 1.2, 2]
                )
                req_flag = " 🔒" if task.is_required else ""
                c_name.write(f"{task.name}{req_flag}")
                c_dur.write(f"{task.duration} min")
                c_pri.write(_priority_badge(task.priority))
                c_start.write(task.start_time or "—")
                if pet is not None:
                    if c_action.button(
                        "Mark Complete", key=f"complete_{i}", use_container_width=True
                    ):
                        st.session_state.pending_complete = (pet.name, task.name)
                        st.rerun()

        # ── Skipped Tasks ──────────────────────────────────────────────────
        if result.skipped_tasks:
            with st.expander(
                f"⏭ {len(result.skipped_tasks)} task(s) skipped — exceeded time budget"
            ):
                st.dataframe(
                    [
                        {
                            "Name": t.name,
                            "Duration (min)": t.duration,
                            "Priority": _priority_badge(t.priority),
                        }
                        for t in result.skipped_tasks
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
