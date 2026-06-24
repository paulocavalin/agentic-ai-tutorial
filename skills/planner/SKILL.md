# planner

## Description
Use this skill to break down a goal into a practical execution plan.

## Tools
- create_plan

## Instructions
- Use this skill when the user asks for a plan, roadmap, checklist, or step-by-step execution.
- Call `create_plan(goal, days)` before responding.
- If the user provides a time horizon, pass it in `days`; otherwise use a reasonable default.
- Return a structured plan with phases, milestones, and clear next actions.
