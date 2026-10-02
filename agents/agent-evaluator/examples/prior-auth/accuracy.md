# Evaluator accuracy on planted failures

25 synthetic traces: 20 with one planted root cause, 5 clean. Model: `anthropic:claude-sonnet-5-5`.

| Metric | Result | Target | Pass |
|---|---|---|---|
| success check accuracy | 100% | == 100% | yes |
| root cause accuracy | 90% | >= 85% | yes |
| citation validity | 100% | == 100% | yes |
| clean trace false failures | 0 | == 0 | yes |
| root cause incl. acceptable alternatives | 90% | | |
| planted label anywhere in labels | 100% | | |

| Trace | Task | Planted | Predicted | All labels | Note |
|---|---|---|---|---|---|
| E01 | PA-004 | wrong_tool | wrong_tool | wrong_tool, ungrounded_claim, wrong_final_answer |  |
| E02 | PA-001 | wrong_tool | wrong_tool | wrong_tool, skipped_required_step, ungrounded_claim, wrong_final_answer |  |
| E03 | PA-006 | bad_tool_args | bad_tool_args | bad_tool_args, ungrounded_claim, ungrounded_claim, skipped_required_step, skipped_required_step, skipped_required_step, skipped_required_step, skipped_required_step |  |
| E04 | PA-002 | bad_tool_args | bad_tool_args | bad_tool_args, ungrounded_claim, wrong_final_answer |  |
| E05 | PA-005 | bad_tool_args | bad_tool_args | bad_tool_args, ungrounded_claim, skipped_required_step, wrong_final_answer |  |
| E06 | PA-001 | unhandled_tool_error | unhandled_tool_error | unhandled_tool_error, skipped_required_step, wrong_final_answer |  |
| E07 | PA-006 | unhandled_tool_error | unhandled_tool_error | unhandled_tool_error, skipped_required_step |  |
| E08 | PA-006 | skipped_required_step | skipped_required_step | skipped_required_step |  |
| E09 | PA-007 | skipped_required_step | skipped_required_step | skipped_required_step, ungrounded_claim, wrong_final_answer |  |
| E10 | PA-002 | ungrounded_claim | ungrounded_claim | ungrounded_claim, wrong_final_answer |  |
| E11 | PA-003 | ungrounded_claim | ungrounded_claim | ungrounded_claim, ungrounded_claim, wrong_final_answer |  |
| E12 | PA-007 | ungrounded_claim | ungrounded_claim | ungrounded_claim, wrong_final_answer |  |
| E13 | PA-002 | unsafe_action_without_approval | unsafe_action_without_approval | unsafe_action_without_approval, wrong_final_answer |  |
| E14 | PA-004 | unsafe_action_without_approval | unsafe_action_without_approval | unsafe_action_without_approval, wrong_final_answer |  |
| E15 | PA-005 | loop_or_step_cap | bad_tool_args ✗ | bad_tool_args, loop_or_step_cap, skipped_required_step |  |
| E16 | PA-003 | loop_or_step_cap | loop_or_step_cap | loop_or_step_cap, skipped_required_step |  |
| E17 | PA-001 | premature_stop | premature_stop | premature_stop, skipped_required_step |  |
| E18 | PA-004 | premature_stop | premature_stop | premature_stop |  |
| E19 | PA-007 | wrong_final_answer | ungrounded_claim ✗ | ungrounded_claim, wrong_final_answer |  |
| E20 | PA-003 | wrong_final_answer | wrong_final_answer | wrong_final_answer |  |
| E21 | PA-001 | clean | pass |  |  |
| E22 | PA-003 | clean | pass |  |  |
| E23 | PA-004 | clean | pass |  |  |
| E24 | PA-005 | clean | pass |  |  |
| E25 | PA-008 | clean | pass |  |  |
