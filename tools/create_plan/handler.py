from typing import Any, Dict, List


def _phase_window(phase_index: int, total_days: int) -> str:
    chunk = max(1, total_days // 3)
    start = (phase_index - 1) * chunk + 1
    end = min(total_days, phase_index * chunk)
    if phase_index == 3:
        end = total_days
    return f"Day {start} to Day {end}"


def run(goal: str, days: int = 7) -> Dict[str, Any]:
    horizon = max(1, min(int(days), 30))
    goal_text = goal.strip() if goal else "Complete the target objective"

    phases: List[Dict[str, str]] = [
        {
            "phase": "Clarify scope and success criteria",
            "window": _phase_window(1, horizon),
            "deliverable": "Problem statement, constraints, and measurable success metrics.",
        },
        {
            "phase": "Execute core work",
            "window": _phase_window(2, horizon),
            "deliverable": "Primary artifacts or implementation draft aligned to the goal.",
        },
        {
            "phase": "Validate and finalize",
            "window": _phase_window(3, horizon),
            "deliverable": "Quality checks, final adjustments, and publication/delivery.",
        },
    ]

    milestones = [
        "Scope approved",
        "Core output produced",
        "Review completed",
        "Final delivery completed",
    ]

    next_actions = [
        "Define owner and deadline for each phase.",
        "Book focused work blocks on calendar.",
        "Set a mid-plan checkpoint to remove blockers early.",
    ]

    risks = [
        "Scope creep",
        "Dependency delays",
        "Insufficient validation time",
    ]

    return {
        "goal": goal_text,
        "horizon_days": horizon,
        "phases": phases,
        "milestones": milestones,
        "next_actions": next_actions,
        "key_risks": risks,
    }
